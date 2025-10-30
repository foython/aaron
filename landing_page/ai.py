"""
Landing Page Chatbot - OpenAI + FAISS
Dynamic | Prompt-based | Memory-enabled | No separate greeting function
"""

import os
import json
import numpy as np
import random
import threading
import time
import re
from pathlib import Path
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
EMBED_CACHE = Path(".kb_embeddings.npy")


def init_config(kb_path="Knowledge_Base.json", model=DEFAULT_MODEL, threshold=0.7):
    """Initialize configuration dynamically."""
    print(f"🔧 Initializing chatbot config with model={model}, threshold={threshold}, kb_path={kb_path}")
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


def load_embeddings_cache(kb_len):
    """Load cached embeddings if present and matching KB length."""
    try:
        if EMBED_CACHE.exists():
            arr = np.load(EMBED_CACHE)
            if arr.shape[0] == kb_len:
                return arr
    except Exception:
        pass
    return None


def save_embeddings_cache(arr):
    try:
        np.save(EMBED_CACHE, arr)
    except Exception:
        pass


# ===================== FAISS INDEX =====================
def build_faiss_index(kb):
    """Build FAISS index for semantic search."""
    print("🔄 Building FAISS index (may take a moment)...")

    # Try load cached embeddings to avoid repeated API calls
    cached = load_embeddings_cache(len(kb))
    if cached is not None:
        vectors = cached
    else:
        embeddings = [get_embedding(e["question"]) for e in kb]
        vectors = np.array(embeddings, dtype="float32")
        save_embeddings_cache(vectors)

    # normalize and build
    faiss.normalize_L2(vectors)
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    print(f"✅ Hey, How can i help you? ")
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
BASE_PROMPT ="""
You are an intelligent and friendly KPI & Process Analysis Assistant.
You specialize in analyzing KPI data, business metrics, and process performance insights.

Behavior and personality rules:
- Greet the user warmly only at the start of a new conversation or when the user explicitly greets (e.g., hello, hi, hey).
- Do not repeat greetings or say phrases like "Hello again" or "Hi again" in follow-up replies.
- When the user asks a question, respond clearly and accurately using the provided knowledge base context if relevant.
- If the context does not provide enough information, politely suggest related KPI, process, or analytics topics instead of guessing.
- Maintain conversation memory and refer to prior exchanges naturally when appropriate.
- Keep responses concise (2–5 sentences), factual, and conversational.
- Maintain a professional yet approachable tone throughout the dialogue.
- Do not use markdown, emojis, or bullet points.
- Avoid unnecessary repetition, self-introductions, or filler text.
- End each response with a natural follow-up question when it makes sense.

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

        # Index is built in background to make initial interactions fast
        self.faiss_index = None
        self.index_ready = False
        self._index_thread = threading.Thread(target=self._build_index_bg, daemon=True)
        self._index_thread.start()

        self.history = []  # memory
        print("✅ Chat session created — warming up knowledge base in background.\n")

    def _build_index_bg(self):
        try:
            idx = build_faiss_index(self.kb)
            self.faiss_index = idx
            self.index_ready = True
        except Exception as e:
            print(f"⚠️ Failed to build FAISS index in background: {e}")

    def generate_response(self, query):
        """Generate response from LLM based on query + memory + KB.

        Fast behavior summary:
        - If the user greets, reply instantly without waiting for index.
        - If the index is still warming, provide a short fallback reply (LLM-based) and continue building.
        - Once index is ready, use semantic search and the KB. If relevance is low, politely ask for KPI/process-related questions.
        """

        q_lower = query.strip().lower()

        # Quick greeting detection
        if re.match(r"^(hi|hello|hey|good morning|good afternoon|good evening)\b", q_lower):
            # Only greet at start of conversation
            if not any(h.startswith("Bot:") for h in self.history):
                reply = "Hello! I'm ready to help with KPI and process-mining questions — how can I assist you today?"
                self.history.append(f"User: {query}")
                self.history.append(f"Bot: {reply}")
                return reply

        # If index not ready, provide a short fallback reply but keep building index in background
        if not self.index_ready or self.faiss_index is None:
            # Simple heuristic: if query doesn't mention KPI/process keywords, ask user to keep it relevant
            keywords = ["kpi", "process", "process mining", "throughput", "cycle time", "lead time", "bottleneck", "sla", "performance"]
            if not any(kw in q_lower for kw in keywords):
                reply = (
                    "I can best help with KPI and process-mining questions. "
                    "Could you please ask something related to KPIs or process performance?"
                )
                self.history.append(f"User: {query}")
                self.history.append(f"Bot: {reply}")
                return reply

            # Otherwise, give a short best-effort response while index warms up
            prompt = (
                "You are a concise KPI & Process assistant. The knowledge base is still loading, "
                "so answer briefly and clearly about the user's question, and indicate you'll provide a fuller answer shortly.\n\n"
                f"User Query: {query}\n\nAnswer:" 
            )

            resp = client.chat.completions.create(
                model=self.config["model"],
                messages=[
                    {"role": "system", "content": "You are a concise KPI & process assistant."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=120,
            )

            reply = resp.choices[0].message.content.strip()
            # store short reply and continue; once index ready the next query will get KB-powered answer
            self.history.append(f"User: {query}")
            self.history.append(f"Bot: {reply}")
            return reply

        # Index is ready: do semantic search and respond with KB context
        try:
            best_entry, score = search_similar(query, self.faiss_index, self.kb)
        except Exception as e:
            # If search fails for some reason, fallback to short LLM reply
            print(f"⚠️ search_similar error: {e}")
            resp = client.chat.completions.create(
                model=self.config["model"],
                messages=[
                    {"role": "system", "content": "You are a concise KPI & process assistant."},
                    {"role": "user", "content": f"User Query: {query}\n\nAnswer briefly:"},
                ],
                temperature=0.2,
                max_tokens=120,
            )
            reply = resp.choices[0].message.content.strip()
            self.history.append(f"User: {query}")
            self.history.append(f"Bot: {reply}")
            return reply

        context_q = best_entry["question"] if best_entry else "N/A"
        context_a = best_entry["answer"] if best_entry else "No relevant data available."

        # If relevance is low, ask politely to keep question relevant
        if score < float(self.config.get("threshold", 0.7)):
            reply = (
                "I couldn't find a close match in my KPI/process knowledge base. "
                "Please ask a question related to KPIs, process mining, or process performance and I'll help."
            )
            self.history.append(f"User: {query}")
            self.history.append(f"Bot: {reply}")
            return reply

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
            temperature=0.25,
            max_tokens=300,
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
