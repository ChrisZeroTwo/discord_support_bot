import os
import openai
from dotenv import load_dotenv

load_dotenv()

# Umgebungsvariablen
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEFAULT_ASSISTANT_ID = os.getenv("DEFAULT_ASSISTANT_ID")

# Datenbank
DATABASE = 'threads.db'

# OpenAI Client
# Der API-Schlüssel wird aus der .env-Datei oder der Umgebungsvariable geladen.
# Wenn kein Schlüssel vorhanden ist, wird der Client nicht initialisiert.
OPENAI_CLIENT = None
if OPENAI_API_KEY:
    OPENAI_CLIENT = openai.OpenAI(api_key=OPENAI_API_KEY)
else:
    print("⚠️ WARNUNG: OPENAI_API_KEY nicht gefunden. OpenAI-Funktionen sind deaktiviert.")

# Farbschema
LIGHT_PINK = 0xFFB6C1
STRONG_PINK = 0xFF69B4
