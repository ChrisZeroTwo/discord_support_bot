import openai
from config import OPENAI_API_KEY
from database import get_db, get_server_settings

openai.api_key = OPENAI_API_KEY

def get_openai_thread_id(user_id):
    with get_db() as conn:
        thread_data = conn.execute("""
            SELECT openai_thread_id FROM threads WHERE user_id = ?
        """, (user_id,)).fetchone()
        return thread_data['openai_thread_id'] if thread_data else None

def update_openai_thread_id(user_id, thread_id):
    with get_db() as conn:
        conn.execute("""
            UPDATE threads SET openai_thread_id = ? WHERE user_id = ?
        """, (thread_id, user_id))
        conn.commit()

async def send_message_to_openai(message, user_id, guild_id):
    thread_id = get_openai_thread_id(user_id)

    # Assistant-ID holen
    server_settings = get_server_settings(guild_id)
    assistant_id = server_settings['assistant_id'] if server_settings else None

    if not assistant_id:
        return "⚠️ Kein Assistant-ID für diesen Server konfiguriert."

    if not thread_id or thread_id == "pending":
        # ➡️ Neuen OpenAI-Thread erstellen
        thread = openai.beta.threads.create()
        thread_id = thread.id
        update_openai_thread_id(user_id, thread_id)

    # Nachricht an Thread anhängen
    openai.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=message
    )

    # Assistant aufrufen
    run = openai.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id
    )

    # Auf Antwort warten
    while True:
        run_status = openai.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run.id
        )
        if run_status.status == "completed":
            break

    # Antwort auslesen
    messages = openai.beta.threads.messages.list(thread_id=thread_id)
    ai_message = None

    # Die neueste Antwort des Assistenten suchen
    for msg in messages.data:
        if msg.role == "assistant":
            ai_message = msg.content[0].text.value
            break

    return ai_message or "⚠️ Konnte keine Antwort generieren."
