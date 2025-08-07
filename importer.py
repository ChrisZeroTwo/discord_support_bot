import os
import sqlite3
import json
import tiktoken
import openai
from config import OPENAI_API_KEY
import nltk
from nltk.tokenize import sent_tokenize

# WICHTIG: Falls nltk Punktsegmentierung noch fehlt:
nltk.download('punkt')

openai.api_key = OPENAI_API_KEY

DOCUMENTS_DIR = "dokumente"
DATA_DIR = "data"
DATABASE_PATH = os.path.join(DATA_DIR, "knowledge.db")

# Embedding-Modell
EMBEDDING_MODEL = "text-embedding-ada-002"
# Token-Limit pro Chunk (ca. 500–700 Tokens)
CHUNK_TOKEN_LIMIT = 600

def get_db():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def create_tables():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_name TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER,
                chunk_text TEXT,
                embedding TEXT,
                FOREIGN KEY (document_id) REFERENCES documents (id)
            )
        """)
        conn.commit()

def read_txt_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()

def read_json_file(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
        return json.dumps(data, ensure_ascii=False, indent=2)

def tokenize_text(text):
    encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
    return encoding.encode(text)

def split_into_chunks(text):
    sentences = sent_tokenize(text)
    chunks = []
    current_chunk = ""
    current_tokens = 0

    for sentence in sentences:
        sentence_tokens = len(tokenize_text(sentence))
        if current_tokens + sentence_tokens > CHUNK_TOKEN_LIMIT:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence
            current_tokens = sentence_tokens
        else:
            current_chunk += " " + sentence
            current_tokens += sentence_tokens

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks

def embed_text(text):
    response = openai.embeddings.create(
        model=EMBEDDING_MODEL,
        input=[text]
    )
    return response.data[0].embedding


def process_files():
    create_tables()

    with get_db() as conn:
        conn.execute("DELETE FROM documents")
        conn.execute("DELETE FROM chunks")
        conn.commit()

    file_list = os.listdir(DOCUMENTS_DIR)
    file_list = [f for f in file_list if f.lower().endswith(('.txt', '.json'))]

    for filename in file_list:
        filepath = os.path.join(DOCUMENTS_DIR, filename)

        try:
            if filename.endswith(".txt"):
                text = read_txt_file(filepath)
            elif filename.endswith(".json"):
                text = read_json_file(filepath)
            else:
                print(f"❌ Ignoriere unbekannten Dateityp: {filename}")
                continue

            chunks = split_into_chunks(text)

            with get_db() as conn:
                cursor = conn.execute("INSERT INTO documents (document_name) VALUES (?)", (filename,))
                document_id = cursor.lastrowid

                for chunk in chunks:
                    embedding = embed_text(chunk)
                    conn.execute(
                        "INSERT INTO chunks (document_id, chunk_text, embedding) VALUES (?, ?, ?)",
                        (document_id, chunk, json.dumps(embedding))
                    )
                conn.commit()

            print(f"✅ Verarbeitet: {filename} ({len(chunks)} Chunks)")

        except Exception as e:
            print(f"❌ Fehler beim Verarbeiten von {filename}: {e}")

if __name__ == "__main__":
    process_files()
