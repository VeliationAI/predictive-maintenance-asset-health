# Challenge 18 — Predictive Maintenance / Asset Health

| Field | Detail |
| --- | --- |
| Department | Energy |
| Assets | Distribution transformers (DTRs) and feeders |
| Geography | Telangana circles (Hyderabad, Warangal, Karimnagar, …) |
| Data source shape | SAP Plant Maintenance (equipment, notifications, work orders, measuring points) |

## Problem

DTR and feeder stress show up in loading patterns and in SAP PM repair history, but those records are rarely turned into a forward-looking risk list. Crews stay reactive.

## Solution built

1. **Ingest SAP PM–shaped data** — equipment master, notifications (M1/M2/M3), work orders (PM01/PM02), daily peak load readings.
2. **Engineer risk features** — peak/average load factor, overload days, oil temperature, breakdowns, preventive gaps, age, cost history.
3. **Train a forward-looking model** — gradient boosting trained as-of T−90d to predict breakdowns in the next 90 days (no label leakage).
4. **Score and intervene** — every asset gets a risk score, band (Critical/High/Medium/Low), top drivers, and a recommended maintenance action.
5. **Dashboard for planners** — circle overview, ranked table, asset detail with load trend and SAP PM history.

## Impact path

- Prioritize the Critical/High queue before summer peaks
- Convert repeated breakdowns into planned outages
- Use existing SAP PM data; no new field instrumentation required for the MVP
- Longer asset life through earlier insulation/oil/load interventions

## Run

```powershell
cd c:\Users\akhil\OneDrive\Documents\predictive-maintenance-asset-health
python -m pip install -r requirements.txt
python -m app.seed
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Dashboard: http://localhost:8080
