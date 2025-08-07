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
    create_tables()
    cleanup_support_channels.start()

@tasks.loop(seconds=3600) # Geändert von 60s auf 1h
async def cleanup_support_channels():
    now = datetime.datetime.now(datetime.timezone.utc)
    delta = datetime.timedelta(hours=1) # Nachrichten älter als 1h löschen

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

    # Befehle vor der Setup-Prüfung verarbeiten
    await bot.process_commands(message)
    if message.content.startswith(bot.command_prefix):
        return

    # Prüfen, ob der User im Setup ist
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
        # Prüfen, ob es ein registrierter Support-Thread ist
        is_support_thread = conn.execute(
            "SELECT 1 FROM threads WHERE discord_thread_id = ? AND guild_id = ?",
            (channel.id, message.guild.id)
        ).fetchone()
        if not is_support_thread:
            return

        # Prüfen, ob die Nachricht vom Bot ist und eine Interaktion hat
        interaction = conn.execute(
            "SELECT 1 FROM interactions WHERE bot_message_id = ?", (message.id,)
        ).fetchone()
        if not interaction:
            return

    # Reaktion in Statistiken aufzeichnen
    emoji_map = {"👍": "helpful", "👎": "bad", "❌": "bad"}
    if str(reaction.emoji) in emoji_map:
        record_reaction(message.guild.id, emoji_map[str(reaction.emoji)])

    if reaction.emoji == "❌":
        with get_db() as conn:
            already_reported = conn.execute(
                "SELECT 1 FROM reported_interactions WHERE bot_message_id = ?", (message.id,)
            ).fetchone()

        if already_reported:
            await message.channel.send(f"Diese Antwort wurde bereits gemeldet.", delete_after=10)
            return

        ctx = await bot.get_context(message)
        await report_bad_response(ctx, bot, message.id, user.id)

        with get_db() as conn:
            conn.execute(
                "INSERT INTO reported_interactions (bot_message_id, reported_by_user_id) VALUES (?, ?)",
                (message.id, user.id)
            )
            conn.commit()

        await message.channel.send(
            f"✅ Danke für dein Feedback, {user.mention}! Wir kümmern uns darum.",
            reference=message
        )

    elif reaction.emoji == "👍":
        await message.channel.send(
            f"👍 Danke für dein positives Feedback, {user.mention}!",
            reference=message,
            delete_after=10
        )

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(embed=discord.Embed(
            description="❌ Du hast keine Berechtigung, diesen Befehl auszuführen.",
            color=STRONG_PINK
        ))
    else:
        # Log other errors to console for debugging
        print(f"Ein Fehler ist im Befehl '{ctx.command}' aufgetreten: {error}")
        await ctx.send(embed=discord.Embed(
            title="Fehler",
            description="Es ist ein unerwarteter Fehler aufgetreten.",
            color=STRONG_PINK
        ))

bot.run(DISCORD_TOKEN)
