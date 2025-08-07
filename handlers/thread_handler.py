import discord
import asyncio
import tiktoken
from config import LIGHT_PINK, OPENAI_CLIENT, CONVERSATION_MEMORY_MAX_TOKENS
from database import get_db
from retriever import find_relevant_chunks
from utils.message_formatter import split_text_into_chunks
from langdetect import detect
from handlers.error_report_handler import report_unanswered_question

def get_token_count(text, model="gpt-4.1-mini"):
    """Zählt die Tokens eines Textes für ein bestimmtes Modell."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))

async def build_messages_with_history(thread_id, system_prompt_text):
    """Baut die Nachrichtenliste für die API unter Berücksichtigung des Token-Limits."""
    messages = [{"role": "system", "content": system_prompt_text}]

    system_prompt_tokens = get_token_count(system_prompt_text)
    remaining_tokens = CONVERSATION_MEMORY_MAX_TOKENS - system_prompt_tokens

    with get_db() as conn:
        history = conn.execute(
            "SELECT role, content FROM conversation_history WHERE thread_id = ? ORDER BY timestamp DESC",
            (thread_id,)
        ).fetchall()

    for message in history:
        message_tokens = get_token_count(message['content'])
        if remaining_tokens - message_tokens >= 0:
            messages.insert(1, {"role": message['role'], "content": message['content']})
            remaining_tokens -= message_tokens
        else:
            break

    return messages

async def handle_new_message(bot, message):
    if message.author.bot:
        return

    with get_db() as conn:
        server = conn.execute("SELECT * FROM servers WHERE guild_id = ?", (message.guild.id,)).fetchone()

    if not server:
        with get_db() as conn:
            in_setup = conn.execute("SELECT 1 FROM setup_sessions WHERE user_id = ?", (message.author.id,)).fetchone()
        if not in_setup:
            await message.channel.send("⚠️ Dieser Server ist noch nicht eingerichtet. Bitte führe zuerst `!setup` aus.")
        return

    support_channel_id = server["support_channel_id"]
    welcome_message = server["welcome_message"]

    if message.channel.id == support_channel_id:
        with get_db() as conn:
            row = conn.execute("SELECT discord_thread_id FROM threads WHERE user_id = ? AND guild_id = ?", (str(message.author.id), message.guild.id)).fetchone()

        thread = None
        if row and row["discord_thread_id"]:
            thread = bot.get_channel(row["discord_thread_id"])
            if thread and not getattr(thread, 'archived', True):
                await message.delete()
                await thread.send(f"➡️ Neue Frage von {message.author.mention}:\n{message.content}")
                return
            else:
                thread = None

        if not thread:
            thread = await message.create_thread(name=f"Support mit {message.author.display_name}", reason="Neuer Support-Thread")
            with get_db() as conn:
                conn.execute("INSERT OR REPLACE INTO threads (user_id, guild_id, discord_thread_id) VALUES (?, ?, ?)", (str(message.author.id), message.guild.id, thread.id))
                conn.commit()

            welcome_embed = discord.Embed(title="👋 Willkommen!", description=welcome_message, color=LIGHT_PINK)
            await thread.send(embed=welcome_embed)
            frage_embed = discord.Embed(title="📝 Deine Frage war:", description=message.content, color=discord.Color.dark_blue())
            await thread.send(embed=frage_embed)

            await message.delete()
            confirmation_msg = await message.channel.send(f"✅ Ich habe einen neuen Support-Thread für dich erstellt: {thread.mention}")
            await asyncio.sleep(10)
            await confirmation_msg.delete()

        await process_question(bot, message, thread)

    elif isinstance(message.channel, discord.Thread):
        with get_db() as conn:
            row = conn.execute("SELECT 1 FROM threads WHERE discord_thread_id = ? AND guild_id = ?", (message.channel.id, message.guild.id)).fetchone()
        if row:
            await process_question(bot, message, message.channel)

async def process_question(bot, message, thread):
    if not OPENAI_CLIENT:
        await thread.send("⚠️ Der OpenAI-Client ist nicht konfiguriert. Bitte den Bot-Administrator informieren.")
        return

    try:
        question = message.content

        # 1. User-Frage in der DB speichern
        question_tokens = get_token_count(question)
        with get_db() as conn:
            conn.execute(
                "INSERT INTO conversation_history (thread_id, role, content, token_count) VALUES (?, ?, ?, ?)",
                (thread.id, 'user', question, question_tokens)
            )
            conn.commit()

        # 2. Kontext und System-Prompt erstellen
        language = detect_language(question)
        relevant_chunks = find_relevant_chunks(question)
        context = "\n\n".join(relevant_chunks)

        if language == "en":
            system_prompt_template = (
                "You are the official support assistant for the DayZ Standalone server 'Crazy World: Last Survivor'.\n"
                "You answer questions based on the provided context and the previous conversation. "
                "Always be friendly and helpful. Structure your answers clearly.\n"
                "If the context does not provide an answer, state that you cannot find the information.\n\n"
                "---CONTEXT---\n{context}\n---END CONTEXT---"
            )
        else:
            system_prompt_template = (
                "Du bist der offizielle Support-Assistant für den DayZ-Standalone Server „Crazy World: Last Survivor“.\n"
                "Beantworte Fragen basierend auf dem bereitgestellten Kontext und der bisherigen Konversation. "
                "Sei immer freundlich und hilfsbereit. Strukturiere deine Antworten klar.\n"
                "Wenn der Kontext keine Antwort liefert, gib an, dass du die Information nicht finden kannst.\n\n"
                "---KONTEXT---\n{context}\n---ENDE KONTEXT---"
            )

        final_system_prompt = system_prompt_template.format(context=context)

        # 3. Nachrichtenliste mit Verlauf erstellen
        messages_for_api = await build_messages_with_history(thread.id, final_system_prompt)

        # 4. OpenAI API aufrufen
        async with thread.typing():
            response = await asyncio.to_thread(
                OPENAI_CLIENT.chat.completions.create,
                model="gpt-4.1-mini",
                messages=messages_for_api,
                temperature=0.3
            )
            final_answer = response.choices[0].message.content.strip()

        # 5. Bot-Antwort in der DB speichern
        answer_tokens = get_token_count(final_answer)
        with get_db() as conn:
            cursor = conn.execute(
                "INSERT INTO conversation_history (thread_id, role, content, token_count) VALUES (?, ?, ?, ?)",
                (thread.id, 'assistant', final_answer, answer_tokens)
            )
            bot_db_message_id = cursor.lastrowid
            conn.commit()

        # 6. Antwort an Discord senden und erste Discord-Nachrichten-ID in DB aktualisieren
        chunks = split_text_into_chunks(final_answer)
        for i, chunk in enumerate(chunks):
            embed = discord.Embed(description=chunk, color=LIGHT_PINK)
            bot_message = await thread.send(embed=embed)

            if i == 0:
                await bot_message.add_reaction("❌")
                await bot_message.add_reaction("👍")
                with get_db() as conn:
                    conn.execute(
                        "UPDATE conversation_history SET discord_message_id = ? WHERE message_id = ?",
                        (bot_message.id, bot_db_message_id)
                    )
                    conn.commit()

        if final_answer.startswith("Darauf habe ich keine Antwort") or final_answer.startswith("I don't have an answer"):
            await report_unanswered_question(bot, message.guild.id, message.author.id, question)

    except Exception as e:
        await thread.send("⚠️ Leider ist ein Fehler aufgetreten.")
        print(f"Fehler beim Verarbeiten einer Frage: {e}")
