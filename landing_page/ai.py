"""
Landing Page Chatbot - Complete FAISS + Gemini Integration
Workflow: JSON → FAISS → Cosine Similarity → Gemini Retrieval → Response
Features: Keyword detection, Question recommendations, Context-aware, No hallucination
"""
 
import os
import json
import numpy as np
import google.generativeai as genai
from dotenv import load_dotenv
import random
 
try:
    import faiss
except ImportError:
    raise ImportError("Install FAISS: pip install faiss-cpu")
 
# ===================== CONFIGURATION =====================
 
def init_config(api_key=None, kb_path="landing.json", model="gemini-2.0-flash-exp", threshold=0.7):
    """
    Initialize configuration.
   
    Args:
        api_key: Google API key
        kb_path: Path to JSON knowledge base
        model: Gemini model name
        threshold: Cosine similarity threshold (0-1)
    """
    load_dotenv()
    api_key = api_key or os.getenv("GOOGLE_API_KEY")
   
    if not api_key:
        raise ValueError("Missing GOOGLE_API_KEY in environment")
   
    genai.configure(api_key=api_key)
   
    return {
        "kb_path": kb_path,
        "model": model,
        "threshold": threshold,
        "embedding_model": "models/text-embedding-004"
    }
 
 
# ===================== KNOWLEDGE BASE (JSON) =====================
 
def load_json_kb(kb_path):
    """
    Load knowledge base from JSON file.
   
    Returns:
        List of {"question": str, "answer": str} dicts
    """
    with open(kb_path, "r", encoding="utf-8") as f:
        data = json.load(f)
   
    # Handle different JSON formats
    entries = data["data"] if isinstance(data, dict) and "data" in data else data
   
    # Normalize entries
    kb = []
    for entry in entries:
        if isinstance(entry, dict) and entry.get("question"):
            kb.append({
                "question": entry["question"].strip(),
                "answer": entry.get("answer", "").strip()
            })
   
    return kb
 
 
def save_json_kb(kb, kb_path):
    """Save knowledge base to JSON file (for backend updates)."""
    data = {"data": kb}
    with open(kb_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
 
 
# ===================== EMBEDDINGS =====================
 
def get_embedding(text, model_name):
    """
    Generate embedding vector for text using Gemini.
   
    Args:
        text: Input text
        model_name: Embedding model name
       
    Returns:
        Numpy array of embedding vector
    """
    try:
        result = genai.embed_content(
            model=model_name,
            content=text,
            task_type="retrieval_document"
        )
        return np.array(result['embedding'], dtype='float32')
    except Exception as e:
        print(f"Embedding error: {e}")
        # Fallback: return zero vector
        return np.zeros(768, dtype='float32')
 
 
def get_query_embedding(text, model_name):
    """Generate embedding for query (retrieval_query task type)."""
    try:
        result = genai.embed_content(
            model=model_name,
            content=text,
            task_type="retrieval_query"
        )
        return np.array(result['embedding'], dtype='float32')
    except Exception as e:
        print(f"Query embedding error: {e}")
        return np.zeros(768, dtype='float32')
 
 
# ===================== FAISS VECTOR STORE =====================
 
def build_faiss_index(kb, embedding_model):
    """
    Build FAISS index from knowledge base.
   
    Args:
        kb: List of Q&A dicts
        embedding_model: Embedding model name
       
    Returns:
        Tuple of (faiss_index, kb_entries)
    """
    print("🔄 Building FAISS index...")
   
    embeddings = []
    valid_entries = []
   
    for entry in kb:
        question = entry["question"]
        embedding = get_embedding(question, embedding_model)
        embeddings.append(embedding)
        valid_entries.append(entry)
   
    # Convert to numpy array
    embeddings_array = np.array(embeddings, dtype='float32')
   
    # Normalize vectors for cosine similarity
    faiss.normalize_L2(embeddings_array)
   
    # Create FAISS index
    dimension = embeddings_array.shape[1]
    index = faiss.IndexFlatIP(dimension)  # Inner Product = Cosine similarity on normalized vectors
    index.add(embeddings_array)
   
    print(f"✅ FAISS index built with {len(valid_entries)} entries")
   
    return index, valid_entries
 
 
# ===================== SIMILARITY SEARCH =====================
 
def search_similar(query, faiss_index, kb_entries, embedding_model, top_k=1):
    """
    Search for most similar entry using cosine similarity.
   
    Args:
        query: User query
        faiss_index: FAISS index
        kb_entries: Knowledge base entries
        embedding_model: Embedding model name
        top_k: Number of results to return
       
    Returns:
        Tuple of (best_entry, similarity_score)
    """
    # Get query embedding
    query_embedding = get_query_embedding(query, embedding_model)
    query_embedding = query_embedding.reshape(1, -1)
   
    # Normalize for cosine similarity
    faiss.normalize_L2(query_embedding)
   
    # Search
    distances, indices = faiss_index.search(query_embedding, top_k)
   
    if len(indices[0]) == 0:
        return None, 0.0
   
    best_idx = indices[0][0]
    similarity = float(distances[0][0])  # Cosine similarity (0-1)
   
    return kb_entries[best_idx], similarity
 
 
# ===================== KEYWORD DETECTION =====================
 
def is_incomplete_query(text):
    """
    Check if user input is just a keyword/phrase (not a complete question).
   
    Returns:
        True if incomplete (single word or short phrase without question words)
    """
    text_clean = text.strip().lower()
    words = text_clean.split()
   
    # Check if it's a short phrase (1-3 words)
    if len(words) <= 3:
        # Check if it lacks question indicators
        question_words = ["what", "how", "why", "when", "where", "who", "which", "is", "are", "can", "do", "does", "tell", "explain", "describe"]
        has_question_word = any(qw in text_clean for qw in question_words)
        has_question_mark = "?" in text_clean
       
        if not has_question_word and not has_question_mark:
            return True
   
    return False
 
 
def find_related_questions(keyword, kb_entries, embedding_model, top_k=3):
    """
    Find questions related to a keyword from knowledge base.
   
    Args:
        keyword: User's keyword/phrase
        kb_entries: Knowledge base entries
        embedding_model: Embedding model name
        top_k: Number of related questions to return
       
    Returns:
        List of related question strings
    """
    # Get keyword embedding
    keyword_embedding = get_query_embedding(keyword, embedding_model)
    keyword_embedding = keyword_embedding.reshape(1, -1)
    faiss.normalize_L2(keyword_embedding)
   
    # Build temporary index for questions
    question_embeddings = []
    for entry in kb_entries:
        emb = get_embedding(entry["question"], embedding_model)
        question_embeddings.append(emb)
   
    embeddings_array = np.array(question_embeddings, dtype='float32')
    faiss.normalize_L2(embeddings_array)
   
    temp_index = faiss.IndexFlatIP(embeddings_array.shape[1])
    temp_index.add(embeddings_array)
   
    # Search
    distances, indices = temp_index.search(keyword_embedding, min(top_k, len(kb_entries)))
   
    related = []
    for idx in indices[0]:
        if idx < len(kb_entries):
            related.append(kb_entries[idx]["question"])
   
    return related
 
 
def suggest_questions(keyword, related_questions):
    """
    Generate a helpful suggestion message with related questions.
   
    Args:
        keyword: User's keyword
        related_questions: List of related questions
       
    Returns:
        Suggestion message
    """
    if not related_questions:
        return f"Please complete your question about '{keyword}'. For example, you could ask 'What is {keyword}?' or 'How does {keyword} work?'"
   
    suggestions = "\n".join([f"  • {q}" for q in related_questions[:3]])
   
    message = (
        f"I see you mentioned '{keyword}'. Please complete your question so I can help you better.\n\n"
        f"Here are some related questions you might want to ask:\n{suggestions}"
    )
   
    return message
 
 
# ===================== GEMINI RESPONSE GENERATION =====================
 
def generate_response_with_context(query, retrieved_entry, similarity, model_name, prev_context=None):
    """
    Generate final response using Gemini with retrieved context.
   
    Args:
        query: User query
        retrieved_entry: Retrieved KB entry
        similarity: Similarity score
        model_name: Gemini model name
        prev_context: Previous conversation context (one turn)
       
    Returns:
        Generated response
    """
    model = genai.GenerativeModel(model_name)
   
    # Build context
    context_text = ""
    if prev_context:
        context_text = f"Previous question: {prev_context['question']}\nPrevious answer: {prev_context['answer']}\n\n"
   
    prompt = f"""You are a precise KPI and Process Analysis Assistant.
 
{context_text}Retrieved Information:
Question: {retrieved_entry['question']}
Answer: {retrieved_entry['answer']}
Similarity Score: {similarity:.2f}
 
Current User Query: {query}
 
INSTRUCTIONS:
- Use the retrieved answer to respond to the user's query
- Keep the response natural and conversational
- If the retrieved answer doesn't match the query well, say: "I don't have this answer right now. Please ask about KPIs, process mining, or business analytics."
- Add a helpful follow-up question at the end
 
Generate response:"""
 
    try:
        response = model.generate_content(prompt)
        return getattr(response, "text", "").strip() or "I don't have this answer right now. Please try again."
    except Exception as e:
        print(f"Generation error: {e}")
        return "I don't have this answer right now. Please try again."
 
 
# ===================== GREETING HANDLER =====================
 
def is_greeting(message):
    """Check if message is a greeting."""
    greetings = ["hi", "hello", "hey", "good morning", "good afternoon",
                 "good evening", "how are you", "help", "what can you do"]
    return any(g in message.lower() for g in greetings)
 
 
def get_greeting_response():
    """Get random greeting response."""
    responses = [
        "Hello! 👋 I'm your KPI and Process Analysis Assistant. How can I help?",
        "Good day! I specialize in KPIs, process mining, and performance insights.",
        "Hi there! 😊 I can help you explore KPI metrics and process analytics.",
        "Welcome! I assist with KPI-based process analysis and benchmarking.",
        "Hello! Let's talk about your business process performance."
    ]
    return random.choice(responses)
 
 
# ===================== MAIN CHAT FUNCTION =====================
 
def chat(user_input, faiss_index, kb_entries, config, prev_context=None):
    """
    Main chat function with FAISS + Gemini workflow.
   
    Workflow:
        1. Load JSON knowledge base
        2. Build FAISS index with embeddings
        3. Find best match using cosine similarity
        4. Retrieve context using Gemini
        5. Generate exact response using LLM
   
    Features:
        - Context-aware (remembers one previous turn)
        - Keyword detection with question suggestions
        - No hallucination (strict threshold)
   
    Args:
        user_input: User's message
        faiss_index: Pre-built FAISS index
        kb_entries: Knowledge base entries
        config: Configuration dict
        prev_context: Previous conversation (one turn only)
       
    Returns:
        Tuple of (response, new_context)
    """
    # Handle greetings
    if is_greeting(user_input):
        response = get_greeting_response()
        return response, None
   
    # Check if input is incomplete (just a keyword/phrase)
    if is_incomplete_query(user_input):
        # Find related questions
        related_questions = find_related_questions(
            user_input,
            kb_entries,
            config["embedding_model"],
            top_k=3
        )
        response = suggest_questions(user_input, related_questions)
        return response, None
   
    # Search for best match using cosine similarity
    best_match, similarity = search_similar(
        user_input,
        faiss_index,
        kb_entries,
        config["embedding_model"],
        top_k=1
    )
   
    # Check if match is good enough
    if best_match is None or similarity < config["threshold"]:
        response = "I don't have this answer right now. Please ask about KPIs, process mining, business analytics, or process improvement."
        return response, None
   
    # Generate response using Gemini with retrieved context
    response = generate_response_with_context(
        user_input,
        best_match,
        similarity,
        config["model"],
        prev_context
    )
   
    # Store context for next turn (one conversation only)
    new_context = {
        "question": user_input,
        "answer": response
    }
   
    return response, new_context
 
 
# ===================== SESSION MANAGER =====================
 
class ChatSession:
    """Manages a chat session with FAISS index and context."""
   
    def __init__(self, config=None):
        """Initialize chat session."""
        self.config = config or init_config()
        self.prev_context = None
       
        # Load JSON and build FAISS index
        print("🔄 Loading knowledge base...")
        self.kb_entries = load_json_kb(self.config["kb_path"])
        self.faiss_index, self.kb_entries = build_faiss_index(
            self.kb_entries,
            self.config["embedding_model"]
        )
        print("✅ Ready to chat!\n")
   
    def send_message(self, user_input):
        """Send message and get response."""
        response, self.prev_context = chat(
            user_input,
            self.faiss_index,
            self.kb_entries,
            self.config,
            self.prev_context
        )
        return response
   
    def reload_kb(self):
        """Reload knowledge base and rebuild FAISS index."""
        print("🔄 Reloading knowledge base...")
        self.kb_entries = load_json_kb(self.config["kb_path"])
        self.faiss_index, self.kb_entries = build_faiss_index(
            self.kb_entries,
            self.config["embedding_model"]
        )
        self.prev_context = None
        print("✅ Knowledge base reloaded!\n")
   
    def reset_context(self):
        """Reset conversation context."""
        self.prev_context = None
 
 
# ===================== SIMPLE WRAPPER =====================
 
_global_session = None
 
def chat_simple(user_input, kb_path="landing.json", model="gemini-2.0-flash-exp"):
    """Simple chat with global session (auto-initializes)."""
    global _global_session
   
    if _global_session is None:
        config = init_config(kb_path=kb_path, model=model)
        _global_session = ChatSession(config)
   
    return _global_session.send_message(user_input)
 
 
# ===================== CLI =====================
 
def main():
    """Run CLI chatbot."""
    print("🤖 Landing Page Chatbot (FAISS + Gemini)\n")
   
    try:
        session = ChatSession()
    except Exception as e:
        print(f"❌ Error initializing: {e}")
        return
   
    print("Commands: 'exit' to quit, 'reload' to refresh KB, 'reset' to clear context\n")
   
    while True:
        try:
            user_input = input("You: ").strip()
           
            if user_input.lower() in ["exit", "quit"]:
                print("Bot: Have a productive day! 👋")
                break
           
            if user_input.lower() == "reload":
                session.reload_kb()
                continue
           
            if user_input.lower() == "reset":
                session.reset_context()
                print("✅ Context reset!\n")
                continue
           
            if not user_input:
                continue
           
            response = session.send_message(user_input)
            print(f"Bot: {response}\n")
           
        except KeyboardInterrupt:
            print("\nBot: Have a productive day! 👋")
            break
        except Exception as e:
            print(f"Error: {e}\n")
 
