import sqlite3
from config import DATABASE

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def create_tables():
    with get_db() as conn:
        # Threads-Tabelle: user_id und guild_id als Primärschlüssel
        conn.execute("""
            CREATE TABLE IF NOT EXISTS threads (
                user_id TEXT NOT NULL,
                guild_id INTEGER NOT NULL,
                discord_thread_id INTEGER,
                openai_thread_id TEXT,
                PRIMARY KEY (user_id, guild_id)
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
        # Neue Tabelle für den Konversationsverlauf (ersetzt 'interactions')
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversation_history (
                message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id INTEGER NOT NULL,
                discord_message_id INTEGER UNIQUE,
                role TEXT NOT NULL, -- 'user' oder 'assistant'
                content TEXT NOT NULL,
                token_count INTEGER,
                reported INTEGER DEFAULT 0, -- 0 for false, 1 for true
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Neue Tabelle für das Tracking von Setup-Prozessen
        conn.execute("""
            CREATE TABLE IF NOT EXISTS setup_sessions (
                user_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                current_step TEXT,
                started_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
