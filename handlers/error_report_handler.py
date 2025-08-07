import discord
from database import get_db
from config import LIGHT_PINK

async def report_bad_response(ctx, bot, bot_message_id: int, reporting_user_id: int):
    """Meldet eine schlechte Bot-Antwort anhand der bot_message_id aus der Datenbank."""
    guild_id = ctx.guild.id

    with get_db() as conn:
        # Interaktion aus der Datenbank abrufen
        interaction = conn.execute(
            "SELECT user_id, question, bot_response FROM interactions WHERE bot_message_id = ?",
            (bot_message_id,)
        ).fetchone()

        # Fehler-Channel des Servers abrufen
        server = conn.execute(
            "SELECT unanswered_channel_id FROM servers WHERE guild_id = ?",
            (guild_id,)
        ).fetchone()

    if not interaction or not server or not server["unanswered_channel_id"]:
        # Wenn keine Daten gefunden werden, kann kein Bericht erstellt werden.
        return

    error_channel = bot.get_channel(server["unanswered_channel_id"])
    if not error_channel:
        return

    try:
        original_user = await bot.fetch_user(interaction["user_id"])
        original_user_name = original_user.name
    except discord.NotFound:
        original_user_name = "Unbekannter User"

    try:
        reporting_user = await bot.fetch_user(reporting_user_id)
        reporting_user_name = reporting_user.name
    except discord.NotFound:
        reporting_user_name = "Unbekannter User"


    # 1️⃣ Erstes Embed mit Titel und Nutzerfrage
    header = discord.Embed(
        title="🚨 Schlechte Antwort gemeldet",
        color=LIGHT_PINK
    )
    header.add_field(name="Frage des Nutzers:", value=interaction['question'], inline=False)
    header.set_footer(text=f"Ursprünglicher Fragesteller: {original_user_name}\nGemeldet von: {reporting_user_name}")
    await error_channel.send(embed=header)

    # 2️⃣ Bot-Antwort aufteilen und in mehreren Embeds senden
    bot_response = interaction['bot_response']
    max_len = 1000  # Chunk-Größe etwas unterhalb des Limits von 1024
    chunks = [bot_response[i:i+max_len] for i in range(0, len(bot_response), max_len)]

    for idx, chunk in enumerate(chunks, start=1):
        title = "Antwort des Bots:" if idx == 1 else f"Antwort des Bots (Fortsetzung {idx})"
        embed = discord.Embed(
            title=title,
            description=chunk,
            color=LIGHT_PINK
        )
        await error_channel.send(embed=embed)

async def report_unanswered_question(bot, guild_id: int, user_id: int, question: str):
    """Meldet eine Frage, die der Bot nicht beantworten konnte."""
    with get_db() as conn:
        server = conn.execute(
            "SELECT unanswered_channel_id FROM servers WHERE guild_id = ?",
            (guild_id,)
        ).fetchone()

    if not server or not server["unanswered_channel_id"]:
        return

    error_channel = bot.get_channel(server["unanswered_channel_id"])
    if not error_channel:
        return

    try:
        user = await bot.fetch_user(user_id)
        user_name = user.name
    except discord.NotFound:
        user_name = "Unbekannter User"

    embed = discord.Embed(
        title="📌 Unbeantwortete Frage",
        description=f"**Frage:**\n{question}",
        color=LIGHT_PINK
    )
    embed.set_footer(text=f"Frage von: {user_name}")
    await error_channel.send(embed=embed)
