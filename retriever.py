import os
import json
import numpy as np
from config import OPENAI_CLIENT

# --- Konfiguration ---
DATA_DIR = "data"
EMBEDDINGS_PATH = os.path.join(DATA_DIR, "embeddings.npy")
CHUNKS_PATH = os.path.join(DATA_DIR, "chunks.json")
EMBEDDING_MODEL = "text-embedding-ada-002"
TOP_K = 5

# --- Globale Variablen für den Index ---
knowledge_embeddings = None
knowledge_chunks = []

def load_knowledge_base():
    """Lädt die Wissensdatenbank aus den Index-Dateien."""
    global knowledge_embeddings, knowledge_chunks
    try:
        if os.path.exists(EMBEDDINGS_PATH) and os.path.exists(CHUNKS_PATH):
            knowledge_embeddings = np.load(EMBEDDINGS_PATH)
            with open(CHUNKS_PATH, 'r', encoding='utf-8') as f:
                knowledge_chunks = json.load(f)
            print(f"✅ Wissensdatenbank geladen: {len(knowledge_chunks)} Chunks.")
        else:
            print("⚠️ Warnung: Index-Dateien nicht gefunden. Die Wissenssuche ist deaktiviert.")
            knowledge_chunks = []
            knowledge_embeddings = None
    except Exception as e:
        print(f"❌ Fehler beim Laden der Wissensdatenbank: {e}")
        knowledge_chunks = []
        knowledge_embeddings = None

def embed_text(text):
    """Erstellt ein Embedding für einen einzelnen Text."""
    if not OPENAI_CLIENT:
        return None
    response = OPENAI_CLIENT.embeddings.create(model=EMBEDDING_MODEL, input=[text])
    return response.data[0].embedding

def cosine_similarity_vectorized(vec, matrix):
    """Berechnet die Kosinusähnlichkeit zwischen einem Vektor und jeder Zeile einer Matrix."""
    dot_product = np.dot(matrix, vec)
    matrix_norms = np.linalg.norm(matrix, axis=1)
    vec_norm = np.linalg.norm(vec)

    if vec_norm == 0 or np.any(matrix_norms == 0):
        return np.zeros(matrix.shape[0])

    return dot_product / (matrix_norms * vec_norm)

def find_relevant_chunks(question):
    """Findet die relevantesten Chunks mithilfe des In-Memory-Vektor-Index."""
    if knowledge_embeddings is None or not knowledge_chunks or not OPENAI_CLIENT:
        return []

    question_embedding = embed_text(question)
    if question_embedding is None:
        return []

    similarities = cosine_similarity_vectorized(question_embedding, knowledge_embeddings)

    top_k_indices = np.argpartition(similarities, -TOP_K)[-TOP_K:]
    top_k_indices_sorted = top_k_indices[np.argsort(similarities[top_k_indices])][::-1]

    relevant_chunks = [knowledge_chunks[i] for i in top_k_indices_sorted]

    return relevant_chunks

# Lade die Wissensdatenbank beim ersten Import des Moduls
load_knowledge_base()
