import sqlite3
import json
import numpy as np
import openai
from config import OPENAI_API_KEY

openai.api_key = OPENAI_API_KEY

DATABASE_PATH = "data/knowledge.db"
EMBEDDING_MODEL = "text-embedding-ada-002"
TOP_K = 5  # Anzahl der besten Treffer

def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def embed_text(text):
    response = openai.embeddings.create(
        model=EMBEDDING_MODEL,
        input=[text]
    )
    return response.data[0].embedding

def cosine_similarity(a, b):
    a = np.array(a)
    b = np.array(b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def find_relevant_chunks(question):
    question_embedding = embed_text(question)

    with get_db() as conn:
        chunks = conn.execute("SELECT chunk_text, embedding FROM chunks").fetchall()

    scored_chunks = []

    for chunk in chunks:
        chunk_text = chunk["chunk_text"]
        chunk_embedding = json.loads(chunk["embedding"])
        similarity = cosine_similarity(question_embedding, chunk_embedding)
        scored_chunks.append((similarity, chunk_text))

    # Sortiere nach Ähnlichkeit, absteigend
    scored_chunks.sort(key=lambda x: x[0], reverse=True)

    # Hole die Top K Treffer
    top_chunks = [chunk_text for _, chunk_text in scored_chunks[:TOP_K]]

    return top_chunks
