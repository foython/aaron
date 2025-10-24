import os
import json
from openai import OpenAI
from dotenv import load_dotenv

# Load API key from environment
load_dotenv()

def generate_complete_kpi_package_openai(
    data: dict,
    model_name: str = "gpt-4o-mini"
) -> dict:
    """
    Generates a complete KPI report package with a single OpenAI API call.

    This function uses one optimized prompt to instruct the LLM to produce a fully
    structured JSON output with three top-level keys:

    {
        "Executive_Summary": "...",
        "KPI_Benchmark": [...],
        "Analysis_Report": {...}
    }

    - Executive_Summary: a 3–5 sentence overview of team performance, strengths, and improvements.
    - KPI_Benchmark: a list of metrics with fields "Metric", "Current Value", "Target Value", and "Status".
    - Analysis_Report: an object with analytical paragraphs (2–4 sentences) for each process category.
    """

    # Initialize client with your OpenAI API key
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "").strip().strip('"').strip("'"))

    # Compress input data to compact JSON for efficient token usage
    compact = json.dumps(data, separators=(",", ":"))

    # --- SYSTEM PROMPT: Guides LLM to output structured business insight JSON ---
    system_msg = (
        "You are a senior process intelligence analyst. "
        "Analyze the provided KPI data between two teams and respond ONLY with valid JSON. "
        "Return exactly three top-level keys:\n"
        "1. 'Executive_Summary' → a concise 3–5 sentence overview comparing the two teams' KPI performance, "
        "highlighting strengths, weaknesses, and improvement opportunities.\n"
        "2. 'KPI_Benchmark' → an array of rows with keys: 'Metric', 'Current Value', 'Target Value', 'Status'. "
        "Use clear, business-friendly formatting such as percentages, hours, or dollar values.\n"
        "3. 'Analysis_Report' → an object containing these keys: loop_analysis, bottleneck_analysis, dropout_analysis, "
        "top_5_process_variants, happy_path, recommendation_to_action, method_notes, appendix. "
        "Each should be a compact 2–4 sentence analytical paragraph merging observation, interpretation, and recommendation.\n\n"
        "Ensure the JSON is properly structured and parsable. "
        "Do not include markdown, explanations, or text outside of the JSON object."
        "Expected Output Format:\n"
    "{\n"
    "  \"loop_analysis\": {\n"
    "    \"loop_analysis\": \"[Compact paragraph with merged insights for loop analysis.]\"\n"
    "  },\n"
    "  \"bottleneck_analysis\": {\n"
    "    \"bottleneck_analysis\": \"[Compact paragraph with merged insights for bottleneck analysis.]\"\n"
    "  },\n"
    "  \"dropout_analysis\": {\n"
    "    \"dropout_analysis\": \"[Compact paragraph with merged insights for dropout analysis.]\"\n"
    "  },\n"
    "  \"happy_path\": {\n"
    "    \"happy_path\": \"[Compact paragraph with merged insights for happy path.]\"\n"
    "  },\n"
    "  \"recommendation_to_action\": {\n"
    "    \"recommendation_to_action\": \"[Compact paragraph with merged insights for recommendation.]\"\n"
    "  }\n"
    "  \"method_notes\": {\n"
    "    \"method_notes\": \"[Compact paragraph with merged insights for method notes.]\"\n"
    "  }\n"
    "  \"appendix\": {\n"
    "    \"appendix\": \"[Compact paragraph with merged insights for appendix.]\"\n"
    "  }\n"
    "}"
    f"KPI_DATA:{compact}"
    )

    # --- USER PROMPT: Includes KPI data context ---
    user_msg = f"KPI_DATA:{compact}"

    # --- SINGLE OPENAI CALL ---
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,     # Lower temperature for factual, consistent outputs
        max_tokens=2000,     # Enough room for large reports
    )

    # Extract model output safely
    text = (
        (getattr(response.choices[0].message, "content", "")
         if hasattr(response.choices[0], "message") else None)
        or getattr(response.choices[0], "text", None)
        or ""
    ).strip()

    # Check for empty output
    if not text:
        raise ValueError("Empty response from OpenAI (KPI package).")

    # --- Robust JSON parsing ---
    try:
        # Try direct parsing
        return json.loads(text)
    except json.JSONDecodeError:
        # If LLM adds stray text, trim to JSON boundaries
        s, e = text.find("{"), text.rfind("}") + 1
        if s != -1 and e > s:
            return json.loads(text[s:e])
        raise ValueError(f"❌ Failed to parse valid JSON from OpenAI output:\n{text}")