import discord
from database import get_db

async def get_stats(ctx):
    guild_id = ctx.guild.id

    with get_db() as conn:
        # Anzahl der aktiven Threads (nicht archiviert oder offen)
        total_threads = conn.execute("""
            SELECT COUNT(*) FROM threads WHERE guild_id = ?
        """, (guild_id,)).fetchone()[0]

        # Anzahl der gemeldeten Reaktionen (helfen, unklar, schlecht)
        reaction_stats = conn.execute("""
            SELECT helpful, unclear, bad FROM reaction_stats WHERE guild_id = ?
        """, (guild_id,)).fetchone()

    if reaction_stats:
        total_helpful = reaction_stats["helpful"]
        total_unclear = reaction_stats["unclear"]
        total_bad = reaction_stats["bad"]
    else:
        total_helpful = total_unclear = total_bad = 0

    embed = discord.Embed(
        title="📊 Support-Bot Statistik",
        color=discord.Color.blue()
    )
    embed.add_field(name="🧵 Aktive Support-Threads", value=f"{total_threads}", inline=False)
    embed.add_field(name="👍 Hilfreiche Antworten", value=f"{total_helpful}", inline=False)
    embed.add_field(name="❓ Unklare Antworten", value=f"{total_unclear}", inline=False)
    embed.add_field(name="❌ Gemeldete schlechte Antworten", value=f"{total_bad}", inline=False)
    embed.set_footer(text=f"Server: {ctx.guild.name}")

    await ctx.send(embed=embed)
