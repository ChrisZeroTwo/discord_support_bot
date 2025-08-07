from database import get_db

async def close_user_thread(ctx, bot):
    user_id = str(ctx.author.id)
    guild_id = ctx.guild.id

    with get_db() as conn:
        thread_data = conn.execute("""
            SELECT * FROM threads WHERE user_id = ? AND guild_id = ?
        """, (user_id, guild_id)).fetchone()

        if not thread_data:
            await ctx.send("❗ Du hast aktuell keinen offenen Thread.")
            return

        discord_thread_id = thread_data['discord_thread_id']
        discord_thread = bot.get_channel(discord_thread_id)

        if discord_thread:
            try:
                await discord_thread.edit(archived=True, locked=True)
                await discord_thread.send("🔒 Dieser Thread wurde geschlossen.")
            except Exception as e:
                await ctx.send(f"⚠️ Fehler beim Schließen des Threads: {e}")

        # Eintrag aus der Datenbank löschen
        conn.execute("DELETE FROM threads WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
        conn.commit()

    await ctx.send("✅ Dein Support-Thread wurde erfolgreich geschlossen.")
