from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
MODEL_DIR = DATA_DIR / "models"
DB_PATH = PROCESSED_DIR / "asset_health.db"
MODEL_PATH = MODEL_DIR / "risk_model.joblib"
METRICS_PATH = MODEL_DIR / "metrics.json"

CIRCLES = [
    "Hyderabad South",
    "Hyderabad Central",
    "Ranga Reddy",
    "Medchal",
    "Warangal",
    "Karimnagar",
    "Nizamabad",
    "Khammam",
    "Nalgonda",
    "Mahabubnagar",
]

RISK_BANDS = [
    (0.70, "Critical"),
    (0.45, "High"),
    (0.25, "Medium"),
    (0.0, "Low"),
]


def risk_band(score: float) -> str:
    for threshold, label in RISK_BANDS:
        if score >= threshold:
            return label
    return "Low"
