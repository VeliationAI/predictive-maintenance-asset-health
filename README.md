# Challenge 18 — Predictive Maintenance / Asset Health

**Department:** Energy  
**Scope:** Distribution transformers (DTRs) and feeders across Telangana

Predict failure risk from loading patterns and historical repair/maintenance data shaped like SAP Plant Maintenance (SAP PM). Maintenance teams get a ranked risk list, risk drivers, and recommended interventions before interruptions occur.

## Expected impact

- Fewer unplanned DTR and feeder failures
- Longer asset life through earlier, targeted work
- Better use of SAP PM history that already exists

## Quick start

```powershell
cd c:\Users\akhil\OneDrive\Documents\predictive-maintenance-asset-health
python -m pip install -r requirements.txt
python -m app.seed
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Open http://localhost:8080

## What you get

| Piece | Purpose |
| --- | --- |
| Synthetic SAP PM–style data | Equipment, functional locations (circles/divisions), notifications, work orders, load readings |
| Risk model | Gradient boosting on load stress + maintenance history |
| Dashboard | Circle overview, ranked risk table, asset detail with drivers and interventions |
| API | `/api/assets`, `/api/assets/{id}`, `/api/summary`, `/api/retrain` |

## SAP PM mapping

| App field | Typical SAP PM concept |
| --- | --- |
| `equipment_id` | Equipment (EQUNR) |
| `functional_location` | Functional location (TPLNR) — circle / division / feeder |
| `notification` | Maintenance notification (QMNUM) |
| `work_order` | Order (AUFNR) |
| `load_reading` | Measuring point / measurement document |

Replace synthetic CSVs under `data/raw/` with exports from SAP, then run:

```powershell
python -m app.seed --from-csv
python -m app.train
```

## Architecture

```
app/
  main.py          FastAPI + dashboard routes
  models.py        SQLite schema
  features.py      Feature engineering from load + PM history
  train.py         Train / persist risk model
  score.py         Score all assets
  seed.py          Generate or import Telangana-like data
  static/          Dashboard UI
data/
  raw/             CSV landing zone (SAP-shaped)
  processed/       SQLite database
  models/          Trained model + metrics
```

Bind to `0.0.0.0:$PORT` for cloud hosts such as Render.
