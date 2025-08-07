import discord
from database import get_db
from config import LIGHT_PINK, STRONG_PINK

async def report_bad_response(ctx, bot, question: str, response: str, original_user_id: int, reporting_user_id: int):
    """Baut und sendet einen standardisierten Bericht für eine schlechte Antwort."""
    guild_id = ctx.guild.id
    with get_db() as conn:
        server = conn.execute("SELECT unanswered_channel_id FROM servers WHERE guild_id = ?", (guild_id,)).fetchone()

    if not server or not server["unanswered_channel_id"]:
        return

    error_channel = bot.get_channel(server["unanswered_channel_id"])
    if not error_channel:
        return

    try:
        original_user = await bot.fetch_user(original_user_id)
        original_user_name = original_user.name
    except discord.NotFound:
        original_user_name = f"ID: {original_user_id}"

    try:
        reporting_user = await bot.fetch_user(reporting_user_id)
        reporting_user_name = reporting_user.name
    except discord.NotFound:
        reporting_user_name = f"ID: {reporting_user_id}"

    header = discord.Embed(
        title="🚨 Schlechte Antwort gemeldet",
        color=STRONG_PINK
    )
    header.add_field(name="Frage des Nutzers", value=f"```{question}```", inline=False)
    header.set_footer(text=f"Ursprünglicher Fragesteller: {original_user_name}\nGemeldet von: {reporting_user_name}")
    await error_channel.send(embed=header)

    max_len = 4000  # Embed-Beschreibungslimit
    chunks = [response[i:i+max_len] for i in range(0, len(response), max_len)]

    for idx, chunk in enumerate(chunks):
        title = "Antwort des Bots" if idx == 0 else f"Antwort des Bots (Fortsetzung {idx+1})"
        embed = discord.Embed(
            title=title,
            description=chunk,
            color=LIGHT_PINK
        )
        await error_channel.send(embed=embed)

async def report_unanswered_question(bot, guild_id: int, user_id: int, question: str):
    """Meldet eine Frage, die der Bot nicht beantworten konnte."""
    with get_db() as conn:
        server = conn.execute("SELECT unanswered_channel_id FROM servers WHERE guild_id = ?", (guild_id,)).fetchone()

    if not server or not server["unanswered_channel_id"]:
        return

    error_channel = bot.get_channel(server["unanswered_channel_id"])
    if not error_channel:
        return

    try:
        user = await bot.fetch_user(user_id)
        user_name = user.name
    except discord.NotFound:
        user_name = f"ID: {user_id}"

    embed = discord.Embed(
        title="📌 Unbeantwortete Frage",
        description=f"**Frage:**\n```{question}```",
        color=LIGHT_PINK
    )
    embed.set_footer(text=f"Frage von: {user_name}")
    await error_channel.send(embed=embed)
