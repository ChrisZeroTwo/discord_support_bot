import os
import sqlite3
import json
import tiktoken
import numpy as np
from config import OPENAI_CLIENT

# Embedding-Modell
EMBEDDING_MODEL = "text-embedding-ada-002"
# Token-Limit pro Chunk
CHUNK_TOKEN_LIMIT = 500
# Überlappung der Chunks in Tokens
CHUNK_OVERLAP = 50

DOCUMENTS_DIR = "dokumente"
DATA_DIR = "data"
DATABASE_PATH = os.path.join(DATA_DIR, "knowledge.db")
EMBEDDINGS_PATH = os.path.join(DATA_DIR, "embeddings.npy")
CHUNKS_PATH = os.path.join(DATA_DIR, "chunks.json")

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
    with open(filepath, "r", encoding="utf-8", errors='ignore') as f:
        return f.read()

def read_json_file(filepath):
    with open(filepath, "r", encoding="utf-8", errors='ignore') as f:
        data = json.load(f)
        return json.dumps(data, ensure_ascii=False, indent=2)

def split_into_chunks(text):
    encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
    tokens = encoding.encode(text)

    if not tokens:
        return []

    chunks = []
    start = 0
    while start < len(tokens):
        end = start + CHUNK_TOKEN_LIMIT
        chunk_tokens = tokens[start:end]
        chunk_text = encoding.decode(chunk_tokens)
        chunks.append(chunk_text.strip())

        start += CHUNK_TOKEN_LIMIT - CHUNK_OVERLAP

    return chunks

def embed_text_batch(texts):
    if not OPENAI_CLIENT:
        raise Exception("OpenAI Client ist nicht initialisiert. Bitte setze den OPENAI_API_KEY.")

    batch_size = 1000
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        response = OPENAI_CLIENT.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch
        )
        all_embeddings.extend([item.embedding for item in response.data])
    return all_embeddings


def process_files():
    if not OPENAI_CLIENT:
        print("❌ OpenAI Client nicht initialisiert. Der Import wird übersprungen.")
        return

    create_tables()

    with get_db() as conn:
        conn.execute("DELETE FROM documents")
        conn.execute("DELETE FROM chunks")
        conn.commit()

    file_list = os.listdir(DOCUMENTS_DIR)
    file_list = [f for f in file_list if f.lower().endswith(('.txt', '.json'))]

    all_chunks_text = []

    for filename in file_list:
        filepath = os.path.join(DOCUMENTS_DIR, filename)
        print(f"🔄 Verarbeite: {filename}...")
        try:
            if filename.endswith(".txt"):
                text = read_txt_file(filepath)
            elif filename.endswith(".json"):
                text = read_json_file(filepath)
            else:
                continue

            chunks = split_into_chunks(text)
            if chunks:
                all_chunks_text.extend(chunks)
            print(f"✅ Verarbeitet: {filename} ({len(chunks)} Chunks)")

        except Exception as e:
            print(f"❌ Fehler beim Verarbeiten von {filename}: {e}")

    if all_chunks_text:
        print(f"\n🧠 Erstelle Embeddings für {len(all_chunks_text)} Chunks...")
        all_embeddings = embed_text_batch(all_chunks_text)

        print("\n💾 Speichere Vektor-Index-Dateien...")
        embeddings_array = np.array(all_embeddings, dtype=np.float32)

        np.save(EMBEDDINGS_PATH, embeddings_array)

        with open(CHUNKS_PATH, 'w', encoding='utf-8') as f:
            json.dump(all_chunks_text, f, ensure_ascii=False, indent=2)

        print(f"✅ Vektor-Index gespeichert unter {EMBEDDINGS_PATH} und {CHUNKS_PATH}")
    else:
        print("\n⚠️ Keine Chunks zum Erstellen von Embeddings gefunden.")


if __name__ == "__main__":
    process_files()
