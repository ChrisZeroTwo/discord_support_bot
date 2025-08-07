import datetime

async def purge_archived_threads(ctx, days_old: int):
    guild = ctx.guild
    now = datetime.datetime.utcnow()

    deleted_count = 0
    deleted_threads = []

    # Alle aktiven und archivierten Threads abrufen
    threads = await guild.active_threads()

    for thread in threads:
        if thread.archived:
            thread_age = now - thread.created_at

            if thread_age.days >= days_old:
                try:
                    deleted_threads.append(f"{thread.name} (Alter: {thread_age.days} Tage)")
                    await thread.delete()
                    deleted_count += 1
                except Exception as e:
                    await ctx.send(f"⚠️ Fehler beim Löschen eines Threads: {e}")

    if deleted_threads:
        thread_list = "\n".join(deleted_threads)
        await ctx.send(
            f"✅ Es wurden {deleted_count} archivierte Threads gelöscht, die älter als {days_old} Tage sind.\n"
            f"**Gelöschte Threads:**\n{thread_list}"
        )
    else:
        await ctx.send(f"✅ Keine archivierten Threads gefunden, die älter als {days_old} Tage sind.")
