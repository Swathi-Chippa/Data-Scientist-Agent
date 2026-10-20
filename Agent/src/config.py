"""
Data Scientist Agent - Core Configuration
Enforces boundaries, thresholds, budgets, and file paths as defined in DESIGN_DETAIL.md.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Base Paths
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(WORKSPACE_ROOT / ".env")
DB_PATH = os.getenv("DB_PATH", str(WORKSPACE_ROOT / "brazil_ecommerce.db"))
TRACES_DIR = WORKSPACE_ROOT / "traces"
PROMPTS_DIR = WORKSPACE_ROOT / "prompts"
EVAL_RESULTS_DIR = WORKSPACE_ROOT / "eval" / "results" / "v1.0"
CACHE_DIR = WORKSPACE_ROOT / ".cache"

# Traces and caches are strictly in-memory during runtime to prevent disk pollution
ENABLE_DISK_TRACING = False
ENABLE_DISK_CACHE = False
os.makedirs(EVAL_RESULTS_DIR, exist_ok=True)

# Guard & Security
BLOCKED_KEYWORDS = [
    "DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "TRUNCATE", "REPLACE",
    "CREATE", "GRANT", "REVOKE", "EXEC", "EXECUTE", "ATTACH", "DETACH",
    "COPY", "EXPORT", "IMPORT", "PRAGMA_WRITE", "INSTALL", "LOAD", "WRITE_CSV",
    "READ_CSV", "READ_PARQUET", "READ_JSON", "SYSTEM", "SHUTDOWN"
]

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"system\s*prompt",
    r"you\s+are\s+now\s+in\s+developer\s+mode",
    r"act\s+as\s+a\s+sql\s+administrator",
    r"bypass\s+(all\s+)?safeguards",
    r"disregard\s+(the\s+)?rules"
]

# Execution Budgets & Gates
MAX_QUERY_TIMEOUT_SECONDS = 20
MAX_ROW_CAP = 1000
MAX_REPAIR_ATTEMPTS = 2
MAX_PLAN_DEPTH = 3
COST_GATE_MAX_ESTIMATED_ROWS = 2_000_000

# Analyst Thresholds
MIN_SERIES_POINTS_SEASONAL = 12
MIN_VOLUME_FOR_ANOMALY = 25
ANOMALY_Z_SCORE_THRESHOLD = 2.5
FDR_Q_VALUE = 0.05
BOOTSTRAP_SAMPLES = 400
CHURN_INACTIVITY_DAYS = 90

# Evidence Grading Levels (§B11)
EVIDENCE_GRADES = {
    0: "Fact from a query",
    1: "Concentration",
    2: "Co-movement",
    3: "Specific to affected unit vs comparison group",
    4: "Consistent with a cause, not proven"
}

# §E5: Mandatory Causal Boundary Note
CAUSAL_BOUNDARY_NOTE = (
    "Observed covariation indicates association, not proven causation. "
    "Unmeasured factors such as local events, competitor actions or data issues "
    "may also explain the pattern. The evidence grade shows how strongly the data supports "
    "each statement, and what additional data would be needed to go further."
)

# LLM / Model Simulation Configuration
DEFAULT_MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
FAST_ROUTER_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

