import sqlite3
from config import DATABASE

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def create_tables():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS threads (
                user_id TEXT PRIMARY KEY,
                discord_thread_id INTEGER,
                openai_thread_id TEXT,
                guild_id INTEGER
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS servers (
                guild_id INTEGER PRIMARY KEY,
                support_channel_id INTEGER,
                unanswered_channel_id INTEGER,
                welcome_message TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reaction_stats (
                guild_id INTEGER PRIMARY KEY,
                helpful INTEGER DEFAULT 0,
                unclear INTEGER DEFAULT 0,
                bad INTEGER DEFAULT 0
            )
        """)
        conn.commit()

def increment_reaction(guild_id: int, emoji: str):
    """Erhöht den Zähler für die entsprechende Reaktion."""
    with get_db() as conn:
        # Falls der guild_id noch nicht existiert, einfügen
        conn.execute("""
            INSERT OR IGNORE INTO reaction_stats (guild_id, helpful, unclear, bad)
            VALUES (?, 0, 0, 0)
        """, (guild_id,))
        
        if emoji == "helpful":
            conn.execute("""
                UPDATE reaction_stats
                SET helpful = helpful + 1
                WHERE guild_id = ?
            """, (guild_id,))
        elif emoji == "unclear":
            conn.execute("""
                UPDATE reaction_stats
                SET unclear = unclear + 1
                WHERE guild_id = ?
            """, (guild_id,))
        elif emoji == "bad":
            conn.execute("""
                UPDATE reaction_stats
                SET bad = bad + 1
                WHERE guild_id = ?
            """, (guild_id,))
        conn.commit()

def get_reaction_stats(guild_id):
    with get_db() as conn:
        stats = conn.execute("""
            SELECT helpful, unclear, bad FROM reaction_stats WHERE guild_id = ?
        """, (guild_id,)).fetchone()
    if stats:
        return {
            "helpful": stats["helpful"],
            "unclear": stats["unclear"],
            "bad": stats["bad"]
        }
    else:
        return {"helpful": 0, "unclear": 0, "bad": 0}

def reset_reaction_stats(guild_id):
    with get_db() as conn:
        conn.execute("""
            UPDATE reaction_stats
            SET helpful = 0, unclear = 0, bad = 0
            WHERE guild_id = ?
        """, (guild_id,))
        conn.commit()
