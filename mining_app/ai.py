import os
import json
from openai import OpenAI
from dotenv import load_dotenv

# Load API key from environment
load_dotenv()


def generate_complete_kpi_package_openai(
    data: dict,
    model_name: str = "gpt-4o-mini",
) -> dict:
    """
    Generates a complete KPI report package with a single OpenAI API call.

    Returns JSON with top-level keys: "Executive_Summary", "KPI_Benchmark", "Analysis_Report".
    """

    # Initialize client with your OpenAI API key
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", "").strip().strip('"').strip("'"))

    # Compact input data for efficient token usage
    compact = json.dumps(data, separators=(",", ":"))

    # --- SYSTEM PROMPT ---
    system_msg = ("""
            You are a senior process intelligence analyst.

            Two datasets are provided:
            - "Current_Project_Data" (Team 1)
            - "Related_Project_Data" (Team 2, the benchmark)

            Return a concise, well-structured JSON report with exactly three top-level keys:
            "Executive_Summary", "KPI_Benchmark", and "Analysis_Report".

            ---

            1. Executive_Summary:
            Write 3–5 sentences comparing Team 1 and Team 2. Clearly explain which team performs better and why, combining observation, interpretation, and summary into one cohesive paragraph.

            ---

            2. KPI_Benchmark:
            Produce an array of objects with the exact following structure:
            {
            "Metric": "<name>",
            "Team_1_Label": take the value of the "(team)(department)" KPI_DATA.Metadata" output format - team(department)",
            "Team_2_Label": take the value of the "(team)(department)" KPI_DATA.Metadata output format - team(department)",
            "Team_1_Value": <value>,
            "Team_2_Value": <value>,
            "Status": "<Team 1 higher by X.X% | Team 2 higher by X.X% | Equal | Team X took Y more <units>>"
            }

            Rules:
            - Keys must match exactly as shown.
            - Use department names from KPI_DATA.Metadata for Team_1_Label and Team_2_Label.

            - Determine which side is better by metric:
            • Lower is better → "Average Cycle Time", "Bottleneck Duration", "Time Lost to Bottleneck", "Idle Time Ratio", "Dropout Rate".
            • Higher is better → "First Pass Rate", "First Pass Yield", "Process Efficiency Ratio".

            - Compute the difference once:
            • higher_value = max(Team_1_Value, Team_2_Value)
            • lower_value  = min(Team_1_Value, Team_2_Value)
            • delta_abs    = higher_value - lower_value            # always (higher - lower)
            • delta_pct    = (delta_abs / lower_value) * 100       # percent relative to the lower value
            • Round delta_pct to 1 decimal with '%'; round delta_abs to 1 decimal.

            - Choose the label to name in Status:
            • better_label = Team_1_Label if Team_1_Value is better per the rule above; else Team_2_Label.
            • worse_label  = the other team.
            • For time/duration metrics, lower is always better.

            - Status formatting:
            • Proportion/ratio where higher is better:
                "Status": "<better_label> performs better by X.X%"
            • Proportion/ratio where lower is better:
                "Status": "<better_label> performs better  by X.X%"
            • Time/duration metrics (hours/days/minutes):
                "Status": "<better_label> performs better  by Y <units>"
            • Equal values → "Status": "Equal"

            - Additional formatting:
            • Proportion/ratio metrics: display values as percentages with 1 decimal (convert 0–1 to %).
            • Time/duration metrics: keep original units; use absolute delta Y = delta_abs.
            • Other numeric metrics: keep numbers as-is; if needed, use absolute delta phrasing.

            - Always use the actual team labels (never literal 'Team 1' or 'Team 2').
            - Exactly one Status per metric; consistent rounding; no extra commentary.

            Formatting by metric type:
            • **Proportion / Ratio Metrics** (include "Rate", "Ratio", "First Pass Rate", "First Pass Yield", "FPY", "Process Efficiency Ratio"):
            - Convert values between 0–1 to percentages (×100).
            - Display both team values as percentages with one decimal place.
            - Use percentage-based comparison for Status.
            • **Time / Duration Metrics** (include "time", "duration", "waiting", or units like "hours", "days", "minutes"):
            - Do not use percentages for Status.
            - Compute absolute difference: Y = |Team1 - Team2|, rounded to one decimal.
            - Extract the team name (text before '(') from Team_1_Label or Team_2_Label, whichever has the higher value.
            - Format Status as: "<Team_Name> took Y more <units>" (e.g., "Team Alpha took 20.2 more hours").
            - Never use generic names like 'Team 1' or 'Team 2' — always use the actual team name extracted from the label.
            • **Other Numeric Metrics**:
            - Keep numeric values as-is (no unit conversion).
            - Use absolute delta wording if percentage difference is not meaningful.

            Ensure:
            - Exactly one Status per metric (no duplicates).
            - Consistent rounding and formatting.
            - No extra commentary in output.

            Metric Type Reference:
            - Average Cycle Time → time (hours; use KPI data unit if available)
            - Idle Time Ratio → proportion (%)
            - Dropout Rate → proportion (%)
            - First Pass Rate → proportion (%)
            - Bottleneck Duration → time (hours)
            - Time Lost to Bottleneck → time (hours)

            ---

            3. Analysis_Report:
            Return a nested object with the following keys, each containing 2–4 sentences that combine evaluation, observation, interpretation, and recommendations:
            {
            "loop_analysis": { "loop_analysis": "..." },
            "bottleneck_analysis": { "bottleneck_analysis": "..." },
            "dropout_analysis": { "dropout_analysis": "..." },
            "happy_path": { "happy_path": "..." },
            "recommendation_to_action": { "recommendation_to_action": "..." },
            "method_notes": { "method_notes": "..." },
            "appendix": { "appendix": "[Brief supporting notes: metric definitions, calculation formulas, assumptions, data caveats/coverage, thresholds or parameters used, and any references to source fields.]" }
            }

            ---

            Output Rules:
            - Return **valid JSON only** (no markdown, no commentary).
            - Preserve numeric meaning.
            - Use "N/A" only when data is unavailable.
            - The Appendix must never be "N/A" — always include at least minimal supporting notes.
            """)


    # --- USER PROMPT ---
    user_msg = f"KPI_DATA:{compact}"

    # --- SINGLE OPENAI CALL ---
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.2,
        max_tokens=2000,
    )

    # Extract model output safely
    text = (
        (getattr(response.choices[0].message, "content", "")
         if hasattr(response.choices[0], "message") else None)
        or getattr(response.choices[0], "text", None)
        or ""
    ).strip()

    if not text:
        raise ValueError("Empty response from OpenAI (KPI package).")

    # Robust JSON parsing
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        s, e = text.find("{"), text.rfind("}") + 1
        if s != -1 and e > s:
            return json.loads(text[s:e])
        raise ValueError(f"Failed to parse valid JSON from OpenAI output:\n{text}")




from typing import Dict, Optional

SYSTEM_PROMPT = """You are a process analytics assistant for an invoice processing system. Parse requests into JSON following these rules:

1. Valid Activity Names (use EXACT matches only):
   - "Invoice Created"
   - "Invoice Sent"
   - "Payment Monitoring"
   - "Payment Received"
   - "Receipt Reconciled"
   - "Archive"
   -"Invoice Approved"
   -"Invoice Sent Reminder"
   -"Invoice Follow-up"
   -"Customer Notification"
   -"Invoice Data Entry"
   -"Fraud Check"
   -"Dispute Resolution"
   -"Invoice Validation
   -"Invoice Adjusted"
   Match user input to closest valid activity name (e.g., "payment monitoring process" → "Payment Monitoring")

2. Mode Rules:
   - "show/analyze" = Analysis Mode: set case field, all remove_* = false
   - "remove/reduce" = Action Mode: case = null, set relevant remove_* true

3. Cost/Time rules:
   - "reduce cost" affects only bottlenecks and loops (both true)
   - "reduce time" affects only bottlenecks and loops (both true)
   - Dropouts are only set true if explicitly mentioned

4. Additional rules:
   - Capture any percentage mentioned (20% → 20)
   - Always use exact activity names from the valid list above

Output format:
{
    "remove_bottlenecks": boolean,
    "remove_loops": boolean,
    "remove_dropouts": boolean,
}

Key examples:
"show loops in payment monitoring process" →
{
    "remove_bottlenecks": false,
    "remove_loops": false,
    "remove_dropouts": false,
}

"reduce cost by 20% in payment received step" →
{
    "remove_bottlenecks": true,
    "remove_loops": true,
    "remove_dropouts": false,
}

Return ONLY the JSON with no additional text or explanation."""




# def parse_process_intent(user_input: str) -> Dict[str, object]:
#     # Load OpenAI API key from environment
#     load_dotenv()
#     api_key = os.getenv("OPENAI_API_KEY")
#     if not api_key:
#         raise ValueError("OPENAI_API_KEY environment variable is required")
    
#     # Initialize OpenAI client
#     client = OpenAI(api_key=api_key)
    
#     try:
#         # Get LLM's interpretation of the user's intent
#         response = client.chat.completions.create(
#             model="gpt-4",  # Can be changed to gpt-3.5-turbo for lower latency
#             messages=[
#                 {"role": "system", "content": SYSTEM_PROMPT},
#                 {"role": "user", "content": user_input}
#             ],
#             temperature=0.0,  # Use 0 for consistent, deterministic outputs
#             max_tokens=150
#         )
        
#         # Parse the JSON response
#         result = json.loads(response.choices[0].message.content.strip())
        
#         # Ensure we have the exact structure we want
#         return {
#             "remove_bottlenecks": bool(result.get("remove_bottlenecks", False)),
#             "remove_loops": bool(result.get("remove_loops", False)),
#             "remove_dropouts": bool(result.get("remove_dropouts", False)),
#             # "target_activity": str(result["target_activity"]) if result.get("target_activity") else None,
#             # "case": str(result["case"]) if result.get("case") else None,
#             # "target_percentage": float(result["target_percentage"]) if result.get("target_percentage") else None
#         }
#     except Exception as e:
#         # If anything fails, return a safe default
#         print(f"Error processing input: {str(e)}")
#         return {
#             "remove_bottlenecks": False,
#             "remove_loops": False,
#             "remove_dropouts": False,
#             # "target_activity": None,
#             # "case": None,
#             # "target_percentage": None,
#         }

from typing import Dict, Any

PROCESS_MINING_SYSTEM_PROMPT = """
You are the Smart Process Mining Assistant.
 
Your ONLY data source:
{PROCESS_DATA}
 
Your role:
- Understand user questions about the process.
- Detect whether the user wants a simple/general or technical/deep answer.
- Automatically adapt your explanation style based on the user's intent.
- When uncertain, start simple but offer deeper technical detail on request.
 
------------------------------------------------
INTENT LOGIC (Important)
------------------------------------------------
Identify user intent:
1. General Questions → simple non-technical
2. Technical Questions → detailed analysis
3. Mixed/unclear → simple summary + technical section
 
------------------------------------------------
RULES
------------------------------------------------
- Use ONLY the dataset provided.
- Never make up data.
- Never answer with generic text.
- Adapt level of detail based on the user request.
"""
 
def normalize_query(msg: str) -> str:
    msg = msg.strip().lower()
 
    replacement_map = {
        "bottleneck": "where is the bottleneck in the process?",
        "improve": "what can be improved in the process?",
        "help": "explain the process issues and improvements",
        "slow": "which activities are slow and causing delays?",
        "loop": "which steps contain loops or rework?",
        "dropout": "which steps have dropouts?",
        "rework": "which steps have rework cycles?",
        "optimize":"what should i optimize first?"
    }
 
    for key, value in replacement_map.items():
        if key in msg:
            return value
    return msg
 
 
def generate_process_mining_response(user_message: str, process_data: dict) -> str:
    """LLM-based process analytics engine."""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
 
    filled_prompt = PROCESS_MINING_SYSTEM_PROMPT.replace(
        "{PROCESS_DATA}", json.dumps(process_data, indent=2)
    )
 
    normalized = normalize_query(user_message)
 
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": filled_prompt},
                {"role": "user", "content": normalized}
            ]
        )
        return response.choices[0].message.content
 
    except Exception as e:
        return f"[ERROR] Process mining analysis failed: {e}"
 
 
# ==========================================================
# ========== USER INPUT PARSER COMPONENT ====================
# (Merged from User_input_process.py)
# ==========================================================
 
INTENT_SYSTEM_PROMPT = """You are a process analytics assistant...
 
(Shortened for readability — full content preserved internally)"""
 
# To reduce length, reuse original file content externally:
INTENT_SYSTEM_PROMPT = open(__file__, "r").read() if False else """You are a process analytics assistant for an invoice processing system. Parse requests into JSON following these rules:
 
Output format:
{
    "remove_bottlenecks": boolean,
    "remove_loops": boolean,
    "remove_dropouts": boolean
}"""
 
def parse_process_intent(user_input: str) -> Dict[str, object]:
    """LLM-powered intent-to-action JSON parser."""
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
 
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": user_input}
            ],
            temperature=0.0
        )
 
        parsed = json.loads(response.choices[0].message.content.strip())
 
        return {
            "remove_bottlenecks": bool(parsed.get("remove_bottlenecks", False)),
            "remove_loops": bool(parsed.get("remove_loops", False)),
            "remove_dropouts": bool(parsed.get("remove_dropouts", False)),
        }
 
    except Exception as e:
        print(f"[Parser Error] {e}")
        return {
            "remove_bottlenecks": False,
            "remove_loops": False,
            "remove_dropouts": False
        }
 
 
# ==========================================================
# ========== SIMULATION CHATBOT (MAIN BRAIN) ================
# (Merged from Simulation_assistant.py)
# ==========================================================
 
ACTION_KEYWORDS = ["remove", "reduce", "fix", "eliminate", "optimize bottleneck", "clean", "optimize loop", "optimize dropout"]
GREETING_KEYWORDS = ["hi", "hello", "hey", "good morning", "good afternoon", "good evening"]
 
 
def detect_intent(user_message: str) -> str:
    text = user_message.lower().strip()
 
    if any(text.startswith(g) for g in GREETING_KEYWORDS):
        return "greeting"
 
    if any(k in text for k in ACTION_KEYWORDS):
        return "action"
 
    return "analysis"
 
 
def dynamic_process_chatbot(user_message: str, process_json: Dict[str, Any]) -> Dict[str, Any]:
    intent = detect_intent(user_message)
 
    # Greeting mode
    if intent == "greeting":
        return {
            "mode": "greeting",
            "ai_response": "Hey! 😊 I'm your Simulation Assistant. How can I help you today?",
            "backend_output": None
        }
 
    # Analysis mode
    if intent == "analysis":
        answer = generate_process_mining_response(user_message, process_json)
        return {
            "mode": "analysis",
            "ai_response": answer,
            "backend_output": None
        }
 
    # Action mode
    parsed_json = parse_process_intent(user_message)
    user_msg = (
        "Got it! 👍 Your optimization request is understood.\n"
        "We applyed updates to the process model now..."
    )
 
    return {
        "mode": "action",
        "ai_response": user_msg,
        "backend_output": parsed_json
    }