import discord
import asyncio

import openai
from config import LIGHT_PINK, OPENAI_API_KEY
from database import get_db
from retriever import find_relevant_chunks
from utils.message_formatter import split_text_into_chunks
from langdetect import detect

# Modul-Import für das Tracking
from handlers import error_report_handler
from handlers.error_report_handler import save_last_interaction

# Setze deinen OpenAI-Schlüssel
openai.api_key = OPENAI_API_KEY

# Anti-Doppelpost-Schutz
processed_message_ids = set()

def detect_language(text):
    try:
        return detect(text)  # 'de', 'en', etc.
    except:
        return "unknown"

async def handle_new_message(bot, message):
    if message.author.bot:
        return

    # Doppelpost-Schutz
    if message.id in processed_message_ids:
        return
    processed_message_ids.add(message.id)
    asyncio.get_event_loop().call_later(300, processed_message_ids.remove, message.id)

    # Servereinstellungen laden
    with get_db() as conn:
        server = conn.execute(
            "SELECT * FROM servers WHERE guild_id = ?", (message.guild.id,)
        ).fetchone()

    if not server:
        await message.channel.send(
            "⚠️ Dieser Server ist noch nicht eingerichtet. Bitte führe zuerst `!setup` aus."
        )
        return

    support_channel_id = server["support_channel_id"]
    error_channel_id   = server["unanswered_channel_id"]
    welcome_message    = server["welcome_message"]

    # Nachricht im Support-Channel ➔ Thread prüfen/erstellen
    if message.channel.id == support_channel_id:
        # Existierenden Thread in der DB nachsehen
        with get_db() as conn:
            row = conn.execute(
                "SELECT discord_thread_id FROM threads WHERE user_id = ? AND guild_id = ?",
                (str(message.author.id), message.guild.id)
            ).fetchone()

        thread = None
        if row:
            thread = bot.get_channel(row["discord_thread_id"])
            # Prüfe, ob Thread noch offen ist
            if thread and not thread.archived:
                await message.channel.send(
                    f"Es existiert bereits ein Support-Thread für dich: {thread.mention} – bitte dort weiterschreiben."
                )
                await thread.send(f"Neue Frage von {message.author.mention}: {message.content}")
            else:
                thread = None

        # Neuen Thread anlegen, wenn keiner existiert
        if not thread:
            thread = await message.create_thread(
                name=f"Support mit {message.author.display_name}",
                reason="Neuer Support-Thread"
            )
            # In der DB speichern
            with get_db() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO threads
                    (user_id, discord_thread_id, openai_thread_id, guild_id)
                    VALUES (?, ?, ?, ?)
                """, (str(message.author.id), thread.id, None, message.guild.id))
                conn.commit()

            # 1. Begrüßungs-Embed
            welcome_embed = discord.Embed(
                title="👋 Willkommen!",
                description=welcome_message,
                color=LIGHT_PINK
            )
            await thread.send(embed=welcome_embed)

            # 2. Nutzerfrage als eigenes Embed
            frage_embed = discord.Embed(
                title="📝 Deine Frage war:",
                description=message.content,
                color=discord.Color.dark_blue()
            )
            await thread.send(embed=frage_embed)

            # 3. Hinweis im Support-Channel
            await message.channel.send(
                f"Ich habe einen neuen Support-Thread für dich erstellt: {thread.mention}"
            )

        # Jetzt die eigentliche Frage im (neuen oder bestehenden) Thread verarbeiten
        await process_question(bot, message, thread, error_channel_id)

    # Nachricht direkt im Thread ➔ verarbeiten
    elif isinstance(message.channel, discord.Thread):
        # Nur weitermachen, wenn dieser Thread in unserer DB als Support-Thread registriert ist
        with get_db() as conn:
            row = conn.execute(
                "SELECT 1 FROM threads WHERE discord_thread_id = ? AND guild_id = ?",
                (message.channel.id, message.guild.id)
            ).fetchone()

        if row:
            # Der Thread gehört uns – Frage verarbeiten
            await process_question(bot, message, message.channel, error_channel_id)
        else:
            # Fremder Thread, ignorieren
            return


async def process_question(bot, message, thread, error_channel_id):
    try:
        question = message.content
        language = detect_language(question)
        relevant_chunks = find_relevant_chunks(question)
        context = "\n\n".join(relevant_chunks)

        # System-Prompt je nach Sprache
        if language == "en":
            system_prompt = (
                "You are the official support assistant for the DayZ Standalone server 'Crazy World: Last Survivor'. "
                "Answer only questions about this server and DayZ, using the provided documents (both English and German). "
                "Use simple, friendly English and direct address ('you'). Bullet points (•, -) and paragraphs are allowed. "
                "Avoid tables and markdown formatting. If you cannot answer, start with 'I don't have an answer.'"
            )
        else:
            system_prompt = (
                "Du bist der offizielle Support-Assistant für den DayZ-Standalone Server „Crazy World: Last Survivor“.\n"
                "Antworte nur zu Server- oder DayZ-Themen. Nutze bereitgestellte Dokumente oder ergänzendes Wissen. "
                "Strukturiere klar, verwende Absätze und Aufzählungen (•, -). Sorge dafür, dass die Ausgabe ansprechend ist. Deine Antwort wird im Discord gepostet. "
                "Vermeide Tabellen und Markdown. "
                "Wenn keine Antwort möglich, beginne mit „Darauf habe ich keine Antwort.“"
            )

        prompt = f"""Hier sind die verfügbaren Informationen:

{context}

Frage:
{question}

Antwort:"""

        # ── Wichtige Änderung: OpenAI-Call in separatem Thread ──
        async with thread.typing():
            response = await asyncio.to_thread(
                openai.chat.completions.create,
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": prompt}
                ],
                temperature=0.2
            )
            final_answer = response.choices[0].message.content.strip()

        chunks = split_text_into_chunks(final_answer)

        # Letzte Interaktion speichern
        save_last_interaction(message.author.id, question, final_answer, thread.id)

        for i, chunk in enumerate(chunks):
            embed = discord.Embed(description=chunk, color=LIGHT_PINK)
            bot_message = await thread.send(embed=embed)

            # Reaktionen nur auf das erste Embed
            if i == 0:
                await bot_message.add_reaction("❌")
                await bot_message.add_reaction("👍")

            # Für das ❌-Reporting die Message-ID merken
            data = error_report_handler.last_messages.get(message.author.id)
            if data:
                data['bot_message_ids'].append(bot_message.id)
            else:
                error_report_handler.last_messages[message.author.id] = {
                    'user_message_id': message.id,
                    'bot_message_ids': [bot_message.id],
                    'question': question,
                    'bot_response': final_answer
                }

        # Unbeantwortete Fragen in den Fehler-Channel
        if final_answer.startswith("Darauf habe ich keine Antwort") or final_answer.startswith("I don't have an answer"):
            error_ch = bot.get_channel(error_channel_id)
            if error_ch:
                await error_ch.send(embed=discord.Embed(
                    title="📌 Unbeantwortete Frage",
                    description=question,
                    color=LIGHT_PINK
                ))

    except Exception as e:
        await thread.send("⚠️ Leider ist ein Fehler aufgetreten.")
        print(f"Fehler beim Verarbeiten einer Frage: {e}")
