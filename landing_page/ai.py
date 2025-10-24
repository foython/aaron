"""
Landing Page Chatbot - OpenAI + FAISS
Dynamic | Prompt-based | Memory-enabled | No separate greeting function
"""

import os
import json
import numpy as np
import random
from openai import OpenAI
from dotenv import load_dotenv

try:
    import faiss
except ImportError:
    raise ImportError("Please install FAISS using: pip install faiss-cpu")

# ===================== CONFIG =====================
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip().strip('"').strip("'")
if not OPENAI_API_KEY:
    raise ValueError("❌ Missing OPENAI_API_KEY in environment.")

client = OpenAI(api_key=OPENAI_API_KEY)

DEFAULT_MODEL = "gpt-4o-mini"
EMBED_MODEL = "text-embedding-3-small"


def init_config(kb_path="landing.json", model=DEFAULT_MODEL, threshold=0.7):
    """Initialize configuration dynamically."""
    return {
        "kb_path": kb_path,
        "model": model,
        "threshold": threshold,
        "embedding_model": EMBED_MODEL,
    }


# ===================== KNOWLEDGE BASE =====================
def load_json_kb(kb_path):
    """Load and normalize JSON knowledge base."""
    with open(kb_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    entries = data["data"] if isinstance(data, dict) and "data" in data else data
    return [{"question": e["question"].strip(), "answer": e.get("answer", "").strip()} for e in entries if e.get("question")]


# ===================== EMBEDDINGS =====================
def get_embedding(text):
    """Generate OpenAI embedding."""
    emb = client.embeddings.create(model=EMBED_MODEL, input=text)
    return np.array(emb.data[0].embedding, dtype="float32")


# ===================== FAISS INDEX =====================
def build_faiss_index(kb):
    """Build FAISS index for semantic search."""
    print("🔄 Building FAISS index...")
    embeddings = [get_embedding(e["question"]) for e in kb]
    vectors = np.array(embeddings, dtype="float32")
    faiss.normalize_L2(vectors)
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    print(f"✅ FAISS index ready with {len(kb)} entries")
    return index


# ===================== SEARCH =====================
def search_similar(query, faiss_index, kb, top_k=1):
    """Find best KB match for query."""
    query_emb = get_embedding(query).reshape(1, -1)
    faiss.normalize_L2(query_emb)
    distances, indices = faiss_index.search(query_emb, top_k)
    if len(indices[0]) == 0:
        return None, 0.0
    return kb[indices[0][0]], float(distances[0][0])


# ===================== PROMPT TEMPLATE =====================
BASE_PROMPT = """
You are an intelligent and friendly KPI & Process Analysis Assistant.
You analyze KPI data, business metrics, and process performance insights.

Your behavior and personality guidelines:
- Start with a warm, natural greeting if the user says hello, hi, or similar.
- If the user asks a question, respond accurately using the provided knowledge base context.
- If the context does not contain enough information, politely recommend relevant KPI or process-related questions.
- You remember previous parts of this chat session and maintain context for continuity.
- Always be professional, concise, and human-like in tone.
- Never use markdown or bullet points.
- End responses with a conversational prompt or follow-up question when appropriate.

Knowledge Base Context:
Question: {context_q}
Answer: {context_a}
Relevance Score: {score:.2f}

User Query: {query}
Chat History (if any): {history}

Respond appropriately below:
"""


# ===================== CHAT MEMORY + RESPONSE =====================
class ChatSession:
    """Handles memory, FAISS context search, and OpenAI responses."""

    def __init__(self, config=None):
        self.config = config or init_config()
        self.kb = load_json_kb(self.config["kb_path"])
        self.faiss_index = build_faiss_index(self.kb)
        self.history = []  # memory
        print("✅ Chat session ready!\n")

    def generate_response(self, query):
        """Generate response from LLM based on query + memory + KB."""
        best_entry, score = search_similar(query, self.faiss_index, self.kb)
        context_q = best_entry["question"] if best_entry else "N/A"
        context_a = best_entry["answer"] if best_entry else "No relevant data available."

        prompt = BASE_PROMPT.format(
            query=query,
            context_q=context_q,
            context_a=context_a,
            score=score,
            history=" | ".join(self.history[-5:])  # last 5 exchanges
        )

        response = client.chat.completions.create(
            model=self.config["model"],
            messages=[
                {"role": "system", "content": "You are an expert process analyst and conversational assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=500,
        )

        reply = response.choices[0].message.content.strip()
        self.history.append(f"User: {query}")
        self.history.append(f"Bot: {reply}")
        return reply

# ===================== WRAPPER FOR BACKEND =====================
_global_session = None

def get_chatbot_response(user_input: str) -> str:
    """
    Unified wrapper for backend or API integration.
    - Keeps a global ChatSession alive across calls.
    - Handles one user input and returns the chatbot response.
    """
    global _global_session

    # Create global persistent session if not already loaded
    if _global_session is None:
        _global_session = ChatSession()

    # Generate response via persistent session
    response = _global_session.generate_response(user_input)

    return response