from config import DISCORD_TOKEN, STRONG_PINK
from database import create_tables, get_db
from handlers.thread_handler import handle_new_message
from handlers.setup_handler import start_setup
from handlers.closethread_handler import close_user_thread
from handlers.purgethreads_handler import purge_archived_threads
from handlers.error_report_handler import report_bad_response
from handlers.stats_handler import get_stats
from handlers.reaction_stats_handler import record_reaction, reset_reaction_stats
import discord
from discord.ext import commands, tasks
import asyncio
import datetime

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ {bot.user} ist online!")
    # Datenbank-Setup beim Start
    with get_db() as conn:
        # Führe eine einfache Abfrage aus, um zu prüfen, ob die Tabellen existieren.
        # Dies ist ein einfacher Weg, um festzustellen, ob die DB neu ist.
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT 1 FROM servers LIMIT 1")
        except sqlite3.OperationalError:
            # Tabelle existiert nicht, also erstellen wir sie
            print("Datenbank nicht gefunden, erstelle Tabellen...")
            create_tables()
            print("Tabellen erfolgreich erstellt.")

    cleanup_support_channels.start()

@tasks.loop(seconds=3600)
async def cleanup_support_channels():
    now = datetime.datetime.now(datetime.timezone.utc)
    delta = datetime.timedelta(hours=1)

    with get_db() as conn:
        rows = conn.execute("SELECT support_channel_id FROM servers").fetchall()

    for row in rows:
        channel = bot.get_channel(row["support_channel_id"])
        if not isinstance(channel, discord.TextChannel):
            continue

        def is_stale_and_unpinned(msg: discord.Message):
            return (now - msg.created_at) > delta and not msg.pinned

        try:
            await channel.purge(limit=100, check=is_stale_and_unpinned)
        except Exception as e:
            print(f"Cleanup fehlgeschlagen in {channel.id}: {e}")

@bot.command(name="setup")
@commands.has_permissions(administrator=True)
async def setup(ctx):
    user_id = ctx.author.id
    guild_id = ctx.guild.id
    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO setup_sessions (user_id, guild_id) VALUES (?, ?)", (user_id, guild_id))
        conn.commit()
    try:
        await start_setup(ctx, bot)
    finally:
        with get_db() as conn:
            conn.execute("DELETE FROM setup_sessions WHERE user_id = ?", (user_id,))
            conn.commit()

@bot.command(name="closethread")
async def closethread(ctx):
    await close_user_thread(ctx, bot)

@bot.command(name="purgethreads")
@commands.has_permissions(administrator=True)
async def purge_threads(ctx, days_old: int = 7):
    await purge_archived_threads(ctx, days_old)

@bot.command(name="stats")
@commands.has_permissions(administrator=True)
async def stats(ctx):
    await get_stats(ctx)

@bot.command(name="shutdown")
@commands.has_permissions(administrator=True)
async def shutdown(ctx):
    await ctx.send("🔌 Bot wird heruntergefahren…")
    await bot.close()

@bot.command(name="resetstats")
@commands.has_permissions(administrator=True)
async def reset_stats(ctx):
    reset_reaction_stats(ctx.guild.id)
    await ctx.send(embed=discord.Embed(
        description="✅ Die Reaktionsstatistiken wurden erfolgreich für diesen Server zurückgesetzt!",
        color=discord.Color.green()
    ))

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    await bot.process_commands(message)
    if message.content.startswith(bot.command_prefix):
        return

    with get_db() as conn:
        is_in_setup = conn.execute("SELECT 1 FROM setup_sessions WHERE user_id = ?", (message.author.id,)).fetchone()
    if is_in_setup:
        return

    await handle_new_message(bot, message)

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return

    message = reaction.message
    channel = message.channel

    if not isinstance(channel, discord.Thread):
        return

    with get_db() as conn:
        bot_message_data = conn.execute(
            "SELECT message_id, thread_id, content, reported FROM conversation_history WHERE discord_message_id = ?",
            (message.id,)
        ).fetchone()

    if not bot_message_data:
        return

    emoji_map = {"👍": "helpful", "👎": "bad", "❌": "bad"}
    if str(reaction.emoji) in emoji_map:
        record_reaction(message.guild.id, emoji_map[str(reaction.emoji)])

    if reaction.emoji == "❌":
        if bot_message_data['reported']:
            await message.channel.send(f"Diese Antwort wurde bereits gemeldet.", delete_after=10)
            return

        with get_db() as conn:
            # Finde die letzte User-Frage im selben Thread vor der Bot-Antwort
            user_question_data = conn.execute(
                """
                SELECT content, role, timestamp FROM conversation_history
                WHERE thread_id = ? AND role = 'user' AND timestamp < (
                    SELECT timestamp FROM conversation_history WHERE message_id = ?
                )
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                (bot_message_data['thread_id'], bot_message_data['message_id'])
            ).fetchone()

            # Finde die ursprüngliche User-ID aus der Thread-Tabelle
            thread_owner_data = conn.execute(
                "SELECT user_id FROM threads WHERE discord_thread_id = ?", (bot_message_data['thread_id'],)
            ).fetchone()

        if not user_question_data or not thread_owner_data:
            await message.channel.send("Fehler: Konnte den ursprünglichen Kontext nicht finden.", delete_after=10)
            return

        ctx = await bot.get_context(message)
        await report_bad_response(
            ctx,
            bot,
            question=user_question_data['content'],
            response=bot_message_data['content'],
            original_user_id=thread_owner_data['user_id'],
            reporting_user_id=user.id
        )

        with get_db() as conn:
            conn.execute("UPDATE conversation_history SET reported = 1 WHERE message_id = ?", (bot_message_data['message_id'],))
            conn.commit()

        await message.channel.send(f"✅ Danke für dein Feedback, {user.mention}! Wir kümmern uns darum.", reference=message)

    elif reaction.emoji == "👍":
        await message.channel.send(f"👍 Danke für dein positives Feedback, {user.mention}!", reference=message, delete_after=10)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(embed=discord.Embed(description="❌ Du hast keine Berechtigung, diesen Befehl auszuführen.", color=STRONG_PINK))
    else:
        print(f"Ein Fehler ist im Befehl '{ctx.command}' aufgetreten: {error}")
        await ctx.send(embed=discord.Embed(title="Fehler", description="Es ist ein unerwarteter Fehler aufgetreten.", color=STRONG_PINK))

bot.run(DISCORD_TOKEN)
