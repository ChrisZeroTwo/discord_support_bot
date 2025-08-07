from config import DISCORD_TOKEN
from database import create_tables, get_db
from handlers.thread_handler import handle_new_message, process_question
from handlers.setup_handler import start_setup
from handlers.closethread_handler import close_user_thread
from handlers.purgethreads_handler import purge_archived_threads
from handlers.error_report_handler import report_bad_response, last_messages, reported_messages
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
users_in_setup = set()

@bot.event
async def on_ready():
    print(f"✅ {bot.user} ist online!")
    create_tables()
    cleanup_support_channels.start()

@tasks.loop(seconds=60)
async def cleanup_support_channels():
    """Bulk‐löscht alle Nicht-gepinnten Nachrichten älter als 60 Sekunden."""
    now = datetime.datetime.now(datetime.timezone.utc)

    with get_db() as conn:
        rows = conn.execute("SELECT support_channel_id FROM servers").fetchall()

    for row in rows:
        channel = bot.get_channel(row["support_channel_id"])
        if not isinstance(channel, discord.TextChannel):
            continue

        def stale_and_unpinned(msg: discord.Message):
            age = (now - msg.created_at).total_seconds()
            return age > 60 and not msg.pinned

        try:
            await channel.purge(limit=100, check=stale_and_unpinned)
        except Exception as e:
            print(f"Cleanup fehlgeschlagen in {channel.id}: {e}")

@bot.command(name="setup")
@commands.has_permissions(administrator=True)
async def setup(ctx):
    user_id = ctx.author.id
    users_in_setup.add(user_id)
    try:
        await start_setup(ctx, bot)
    finally:
        users_in_setup.remove(user_id)

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

    if message.author.id in users_in_setup:
        return

    await handle_new_message(bot, message)

@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return

    message = reaction.message
    channel = message.channel

    # Nur Reaktionen in registrierten Support-Threads verarbeiten
    if not isinstance(channel, discord.Thread):
        return
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM threads WHERE discord_thread_id = ? AND guild_id = ?",
            (channel.id, message.guild.id)
        ).fetchone()
    if not row:
        return

    # Jetzt zählen und Feedback geben
    record_reaction(message.guild.id, str(reaction.emoji))

    # ❌ → schlechte Antwort melden
    if reaction.emoji == "❌":
        if message.id in reported_messages:
            return
        for user_id, data in last_messages.items():
            if message.id in data['bot_message_ids']:
                ctx = await bot.get_context(message)
                await report_bad_response(ctx, bot, user_id)
                reported_messages.add(message.id)
                await message.channel.send(
                    f"✅ Danke für dein Feedback, <@{user.id}>! Wir kümmern uns darum.",
                    reference=message
                )
                break

    # 👍 → Dankes-Feedback
    elif reaction.emoji == "👍":
        await message.channel.send(
            f"👍 Danke für dein positives Feedback, <@{user.id}>!",
            reference=message
        )

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(embed=discord.Embed(
            description="❌ Du hast keine Berechtigung, diesen Befehl auszuführen.",
            color=discord.Color.red()
        ))
    else:
        raise error

bot.run(DISCORD_TOKEN)
