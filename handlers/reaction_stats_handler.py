# handlers/reaction_stats_handler.py

from database import increment_reaction, get_reaction_stats as db_get_stats, reset_reaction_stats as db_reset_stats

def record_reaction(guild_id: int, emoji: str):
    """Reaktion zählen und die passende Spalte in der Datenbank erhöhen."""
    
    # Hier wählen wir basierend auf dem Emoji die passende Spalte (helpful, unclear, bad)
    if emoji == "👍":
        increment_reaction(guild_id, "helpful")
    elif emoji == "❓":
        increment_reaction(guild_id, "unclear")
    elif emoji == "❌":
        increment_reaction(guild_id, "bad")

def get_reaction_stats(guild_id: int):
    return db_get_stats(guild_id)

def reset_reaction_stats(guild_id: int):
    db_reset_stats(guild_id)
