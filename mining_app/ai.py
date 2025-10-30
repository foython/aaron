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
        "You are provided KPI data for two teams:\n"
        " - 'Current_Project_Data' represents the team being analyzed.\n"
        " - 'Related_Project_Data' represents the benchmark or target team.\n\n"
        "Generate a comprehensive yet concise comparative process intelligence report "
        "between these two datasets. The report must contain exactly three top-level keys:\n\n"
        "1. 'Executive_Summary': A 4–6 sentence overview summarizing performance trends, "
        "strengths, weaknesses, and actionable takeaways comparing both teams.\n\n"
        "2. 'KPI_Benchmark': An array comparing critical KPIs side by side with the following fields:\n"
        "   - 'Metric': Name of the KPI metric\n"
        "   - 'Current Value': Value from Current_Project_Data\n"
        "   - 'Target Value': Value from Related_Project_Data\n"
        "   - 'Status': One of 'Above Target', 'Below Target', or 'On Target'.\n"
        "   Interpret percentages, durations, and ratios appropriately.\n\n"
        "3. 'Analysis_Report': A nested JSON object that contains deeper analytical sections.\n"
        "   Each section must be structured exactly as shown below:\n\n"
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
        "  },\n"
        "  \"method_notes\": {\n"
        "    \"method_notes\": \"[Compact paragraph with merged insights for method notes.]\"\n"
        "  },\n"
        "  \"appendix\": {\n"
        "    \"appendix\": \"[Compact paragraph with merged insights for appendix.]\"\n"
        "  }\n"
        "}\n\n"
        "Each paragraph (2–4 sentences) should combine observation, interpretation, and recommendation concisely.\n\n"
        "Rules:\n"
        "- Output must be **valid JSON only** (no markdown or text outside JSON).\n"
        "- Ensure analytical meaning and numeric comparisons are preserved.\n"
        "- No extra commentary or formatting.\n"
        "- Include 'N/A' only when data is unavailable.\n\n"
        f"KPI_DATA: {compact}"
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


from typing import Dict, Optional

SYSTEM_PROMPT = """You are a process analytics assistant. Parse requests into JSON following these rules:

1. "show/analyze" = Analysis Mode: set case field, all remove_* = false
2. "remove/reduce" = Action Mode: case = null, set relevant remove_* true
3. Detect process name for target_activity
4. Capture any percentage mentioned (20% → 20)
5. "reduce cost/time" sets all remove_* true

Output format:
{
    "remove_bottlenecks": boolean,
    "remove_loops": boolean,
    "remove_dropouts": boolean,
    "target_activity": string | null,
    "case": string | null,
    "target_percentage": number | null
}

Key examples:
"show loops in Invoice" →
{
    "remove_bottlenecks": false,
    "remove_loops": false,
    "remove_dropouts": false,
    "target_activity": "Invoice",
    "case": "Loop",
    "target_percentage": null
}

"remove 20% bottlenecks from Payment" →
{
    "remove_bottlenecks": true,
    "remove_loops": false,
    "remove_dropouts": false,
    "target_activity": "Payment",
    "case": null,
    "target_percentage": 20
}

Return ONLY the JSON with no additional text or explanation."""

def parse_process_intent(user_input: str) -> Dict[str, object]:
    # Load OpenAI API key from environment
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")
    
    # Initialize OpenAI client
    client = OpenAI(api_key=api_key)
    
    try:
        # Get LLM's interpretation of the user's intent
        response = client.chat.completions.create(
            model="gpt-4",  # Can be changed to gpt-3.5-turbo for lower latency
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_input}
            ],
            temperature=0.0,  # Use 0 for consistent, deterministic outputs
            max_tokens=150
        )
        
        # Parse the JSON response
        result = json.loads(response.choices[0].message.content.strip())
        
        # Ensure we have the exact structure we want
        return {
            "remove_bottlenecks": bool(result.get("remove_bottlenecks", False)),
            "remove_loops": bool(result.get("remove_loops", False)),
            "remove_dropouts": bool(result.get("remove_dropouts", False)),
            "target_activity": str(result["target_activity"]) if result.get("target_activity") else None,
            "case": str(result["case"]) if result.get("case") else None,
            "target_percentage": float(result["target_percentage"]) if result.get("target_percentage") else None
        }
    except Exception as e:
        # If anything fails, return a safe default
        print(f"Error processing input: {str(e)}")
        return {
            "remove_bottlenecks": False,
            "remove_loops": False,
            "remove_dropouts": False,
            "target_activity": None,
            "case": None,
            "target_percentage": None,
        }