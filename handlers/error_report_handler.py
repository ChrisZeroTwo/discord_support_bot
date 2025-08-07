import discord
from database import get_db
from config import LIGHT_PINK

# Speicher für letzte Antworten
last_messages = {}         # user_id -> { 'user_message': ..., 'bot_response': ..., 'bot_message_ids': [...] }
reported_messages = set()  # IDs der Bot-Antworten, die schon gemeldet wurden

def save_last_interaction(user_id, user_message, bot_response, bot_message_id):
    """Speichert die letzte Interaktion eines Users (Frage, Antwort, Bot-Nachricht-ID)."""
    if user_id not in last_messages:
        last_messages[user_id] = {
            "user_message": user_message,
            "bot_response": bot_response,
            "bot_message_ids": [bot_message_id]
        }
    else:
        last_messages[user_id]["user_message"] = user_message
        last_messages[user_id]["bot_response"] = bot_response
        last_messages[user_id]["bot_message_ids"].append(bot_message_id)

async def report_bad_response(ctx, bot, user_id):
    """Meldet eine schlechte Bot-Antwort durch ❌-Reaktion und teilt lange Antworten auf."""
    if user_id not in last_messages:
        return

    interaction = last_messages[user_id]
    guild_id = ctx.guild.id

    # Fehler-Channel auslesen
    with get_db() as conn:
        server = conn.execute("""
            SELECT unanswered_channel_id FROM servers WHERE guild_id = ?
        """, (guild_id,)).fetchone()

    if not server or not server["unanswered_channel_id"]:
        return

    error_channel = bot.get_channel(server["unanswered_channel_id"])
    if not error_channel:
        return

    user = await bot.fetch_user(user_id)

    # 1️⃣ Erstes Embed mit Titel und Nutzerfrage
    header = discord.Embed(
        title="🚨 Schlechte Antwort gemeldet",
        color=LIGHT_PINK
    )
    header.add_field(name="Frage des Nutzers:", value=interaction['user_message'], inline=False)
    header.set_footer(text=f"Gemeldet von: {user.name}#{user.discriminator}")
    await error_channel.send(embed=header)

    # 2️⃣ Bot-Antwort aufteilen und in mehreren Embeds senden
    bot_response = interaction['bot_response']
    # Chunk-Größe etwas unterhalb des Limits von 1024
    max_len = 1000
    chunks = [bot_response[i:i+max_len] for i in range(0, len(bot_response), max_len)]

    for idx, chunk in enumerate(chunks, start=1):
        title = "Antwort des Bots:" if idx == 1 else f"Antwort des Bots (Fortsetzung {idx})"
        embed = discord.Embed(
            title=title,
            description=chunk,
            color=LIGHT_PINK
        )
        await error_channel.send(embed=embed)

async def report_openai_failure(bot, guild_id, user_id, user_message):
    """Meldet, wenn OpenAI keine Antwort liefern konnte."""
    with get_db() as conn:
        server = conn.execute("""
            SELECT unanswered_channel_id FROM servers WHERE guild_id = ?
        """, (guild_id,)).fetchone()

    if not server or not server["unanswered_channel_id"]:
        return

    error_channel = bot.get_channel(server["unanswered_channel_id"])
    if not error_channel:
        return

    user = await bot.fetch_user(user_id)

    embed = discord.Embed(
        title="🚨 OpenAI konnte keine Antwort liefern",
        color=LIGHT_PINK
    )
    embed.add_field(name="Frage des Nutzers:", value=user_message, inline=False)
    embed.set_footer(text=f"User: {user.name}#{user.discriminator}")

    await error_channel.send(embed=embed)

async def report_auto_bad_response(bot, guild_id, user_id, user_message, ai_response):
    """Meldet automatisch erkannte schlechte Antworten."""
    with get_db() as conn:
        server = conn.execute("""
            SELECT unanswered_channel_id FROM servers WHERE guild_id = ?
        """, (guild_id,)).fetchone()

    if not server or not server["unanswered_channel_id"]:
        return

    error_channel = bot.get_channel(server["unanswered_channel_id"])
    if not error_channel:
        return

    user = await bot.fetch_user(user_id)

    # Erstes Embed
    header = discord.Embed(
        title="🚨 Automatisch erkannte schlechte Antwort",
        color=LIGHT_PINK
    )
    header.add_field(name="Frage des Nutzers:", value=user_message, inline=False)
    header.set_footer(text=f"User: {user.name}#{user.discriminator}")
    await error_channel.send(embed=header)

    # Antwort in mehreren Embeds
    response = ai_response
    max_len = 1000
    chunks = [response[i:i+max_len] for i in range(0, len(response), max_len)]
    for idx, chunk in enumerate(chunks, start=1):
        title = "Antwort des Bots:" if idx == 1 else f"Antwort des Bots (Fortsetzung {idx})"
        embed = discord.Embed(
            title=title,
            description=chunk,
            color=LIGHT_PINK
        )
        await error_channel.send(embed=embed)
