import discord
import asyncio
from config import LIGHT_PINK, OPENAI_CLIENT
from database import get_db
from retriever import find_relevant_chunks
from utils.message_formatter import split_text_into_chunks
from langdetect import detect
from handlers.error_report_handler import report_unanswered_question

def detect_language(text):
    try:
        return detect(text)
    except:
        return "unknown"

async def handle_new_message(bot, message):
    if message.author.bot:
        return

    with get_db() as conn:
        server = conn.execute(
            "SELECT * FROM servers WHERE guild_id = ?", (message.guild.id,)
        ).fetchone()

    if not server:
        with get_db() as conn:
            in_setup = conn.execute("SELECT 1 FROM setup_sessions WHERE user_id = ?", (message.author.id,)).fetchone()
        if not in_setup:
            await message.channel.send(
                "⚠️ Dieser Server ist noch nicht eingerichtet. Bitte führe zuerst `!setup` aus."
            )
        return

    support_channel_id = server["support_channel_id"]
    welcome_message = server["welcome_message"]

    if message.channel.id == support_channel_id:
        with get_db() as conn:
            row = conn.execute(
                "SELECT discord_thread_id FROM threads WHERE user_id = ? AND guild_id = ?",
                (str(message.author.id), message.guild.id)
            ).fetchone()

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
            thread = await message.create_thread(
                name=f"Support mit {message.author.display_name}",
                reason="Neuer Support-Thread"
            )
            with get_db() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO threads (user_id, guild_id, discord_thread_id) VALUES (?, ?, ?)",
                    (str(message.author.id), message.guild.id, thread.id)
                )
                conn.commit()

            welcome_embed = discord.Embed(title="👋 Willkommen!", description=welcome_message, color=LIGHT_PINK)
            await thread.send(embed=welcome_embed)

            frage_embed = discord.Embed(title="📝 Deine Frage war:", description=message.content, color=discord.Color.dark_blue())
            await thread.send(embed=frage_embed)

            await message.delete()
            confirmation_msg = await message.channel.send(
                f"✅ Ich habe einen neuen Support-Thread für dich erstellt: {thread.mention}"
            )
            await asyncio.sleep(10)
            await confirmation_msg.delete()

        await process_question(bot, message, thread)

    elif isinstance(message.channel, discord.Thread):
        with get_db() as conn:
            row = conn.execute(
                "SELECT 1 FROM threads WHERE discord_thread_id = ? AND guild_id = ?",
                (message.channel.id, message.guild.id)
            ).fetchone()
        if row:
            await process_question(bot, message, message.channel)

async def process_question(bot, message, thread):
    if not OPENAI_CLIENT:
        await thread.send("⚠️ Der OpenAI-Client ist nicht konfiguriert. Bitte den Bot-Administrator informieren.")
        return

    try:
        question = message.content
        language = detect_language(question)
        relevant_chunks = find_relevant_chunks(question)
        context = "\n\n".join(relevant_chunks)

        if language == "en":
            system_prompt = (
                "You are the official support assistant for the DayZ Standalone server 'Crazy World: Last Survivor'. "
                "Your task is to answer questions based *only* on the provided context information. "
                "The user's question will be inside <question> tags. "
                "If the provided context does not contain the answer, you MUST start your reply with the exact phrase "
                "'I don't have an answer for that.' and nothing else. "
                "Use simple, friendly English. Structure your answer clearly with bullet points (•, -) and paragraphs. "
                "Do not use tables or complex markdown."
            )
        else:
            system_prompt = (
                "Du bist der offizielle Support-Assistant für den DayZ-Standalone Server „Crazy World: Last Survivor“.\n"
                "Deine Aufgabe ist es, Fragen *ausschließlich* auf Basis der bereitgestellten Kontext-Informationen zu beantworten. "
                "Die Frage des Nutzers befindet sich in <question> Tags. "
                "Wenn der bereitgestellte Kontext die Antwort nicht enthält, MUSST du deine Antwort mit dem exakten Satz "
                "„Darauf habe ich keine Antwort.“ beginnen und sonst nichts. "
                "Antworte in einfacher, freundlicher Sprache. Strukturiere klar, verwende Absätze und Aufzählungen (•, -). "
                "Vermeide Tabellen und komplexes Markdown."
            )

        prompt = f"""Hier ist der relevante Kontext aus unserer Wissensdatenbank:
<context>
{context}
</context>

Bitte beantworte die folgende Frage. Antworte NUR auf Basis des oben genannten Kontexts.
<question>
{question}
</question>
"""

        async with thread.typing():
            response = await asyncio.to_thread(
                OPENAI_CLIENT.chat.completions.create,
                model="gpt-4.1-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )
            final_answer = response.choices[0].message.content.strip()

        chunks = split_text_into_chunks(final_answer)
        bot_message_ids = []
        for i, chunk in enumerate(chunks):
            embed = discord.Embed(description=chunk, color=LIGHT_PINK)
            bot_message = await thread.send(embed=embed)
            bot_message_ids.append(bot_message.id)

            if i == 0:
                await bot_message.add_reaction("❌")
                await bot_message.add_reaction("👍")

        with get_db() as conn:
            conn.execute(
                "INSERT INTO interactions (bot_message_id, user_id, thread_id, question, bot_response) VALUES (?, ?, ?, ?, ?)",
                (bot_message_ids[0], message.author.id, thread.id, question, final_answer)
            )
            conn.commit()

        if final_answer.startswith("Darauf habe ich keine Antwort") or final_answer.startswith("I don't have an answer"):
            await report_unanswered_question(bot, message.guild.id, message.author.id, question)

    except Exception as e:
        await thread.send("⚠️ Leider ist ein Fehler aufgetreten.")
        print(f"Fehler beim Verarbeiten einer Frage: {e}")
