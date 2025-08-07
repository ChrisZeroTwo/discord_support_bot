import os
from dotenv import load_dotenv

load_dotenv()

# Bestehende Umgebungsvariablen
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEFAULT_ASSISTANT_ID = os.getenv("DEFAULT_ASSISTANT_ID")
DATABASE = 'threads.db'

# 🎨 Farbschema (neu hinzugefügt)
LIGHT_PINK = 0xFFB6C1  # Leichtes Pink für normale Nachrichten
STRONG_PINK = 0xFF69B4  # Kräftiges Pink für Fehler, Warnungen
