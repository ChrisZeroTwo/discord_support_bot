# handlers/setup_handler.py

import discord
from config import LIGHT_PINK, DEFAULT_ASSISTANT_ID
from database import get_db

async def start_setup(ctx, bot):
    guild_id = ctx.guild.id
    author = ctx.author

    def check(m):
        return m.author == author and m.channel == ctx.channel

    await ctx.send(embed=discord.Embed(
        title="🔧 Setup gestartet!",
        description="Bitte beantworte die folgenden Fragen.\nGib `-` ein, um den aktuellen Wert zu übernehmen.",
        color=LIGHT_PINK
    ))

    with get_db() as conn:
        existing = conn.execute("""
            SELECT support_channel_id, unanswered_channel_id, welcome_message
            FROM servers
            WHERE guild_id = ?
        """, (guild_id,)).fetchone()

    # 1. Support-Channel-ID
    current_support_id = existing["support_channel_id"] if existing else "(noch keiner)"
    await ctx.send(embed=discord.Embed(
        title="1️⃣ Support-Channel-ID",
        description=f"Aktueller Wert: `{current_support_id}`\nBitte neue Support-Channel-ID eingeben (`-` = behalten):",
        color=LIGHT_PINK
    ))
    support_channel_msg = await bot.wait_for('message', check=check)
    support_channel_input = support_channel_msg.content.strip()
    support_channel_id = int(support_channel_input) if support_channel_input != "-" else current_support_id

    # 2. Fehler-Channel-ID
    current_error_id = existing["unanswered_channel_id"] if existing else "(noch keiner)"
    await ctx.send(embed=discord.Embed(
        title="2️⃣ Fehler-Channel-ID",
        description=f"Aktueller Wert: `{current_error_id}`\nBitte neue Fehler-Channel-ID eingeben (`-` = behalten):",
        color=LIGHT_PINK
    ))
    error_channel_msg = await bot.wait_for('message', check=check)
    error_channel_input = error_channel_msg.content.strip()
    error_channel_id = int(error_channel_input) if error_channel_input != "-" else current_error_id

    # 3. Begrüßungstext
    current_welcome = existing["welcome_message"] if existing else "Willkommen im Support!"
    await ctx.send(embed=discord.Embed(
        title="3️⃣ Begrüßungstext",
        description=f"Aktueller Text:\n```{current_welcome}```\nBitte neuen Begrüßungstext eingeben (`-` = behalten):",
        color=LIGHT_PINK
    ))
    welcome_msg = await bot.wait_for('message', check=check)
    welcome_input = welcome_msg.content.strip()
    welcome_message = welcome_input if welcome_input != "-" else current_welcome

    # Update in der Datenbank
    with get_db() as conn:
        conn.execute("""
            INSERT INTO servers (guild_id, support_channel_id, unanswered_channel_id, welcome_message)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                support_channel_id = excluded.support_channel_id,
                unanswered_channel_id = excluded.unanswered_channel_id,
                welcome_message = excluded.welcome_message
        """, (guild_id, support_channel_id, error_channel_id, welcome_message))
        conn.commit()

    await ctx.send(embed=discord.Embed(
        title="✅ Setup abgeschlossen!",
        description="Die neuen Einstellungen wurden gespeichert.",
        color=discord.Color.green()
    ))
