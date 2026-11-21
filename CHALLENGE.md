# Challenge 18 — Predictive Maintenance / Asset Health

| Field | Detail |
| --- | --- |
| Product | **GridSense Asset Health** (enterprise) |
| Department | Energy |
| Assets | Distribution transformers (DTRs) and feeders |
| Geography | Telangana circles |
| Data | SAP Plant Maintenance–shaped exports |

## Enterprise delivery

- JWT authentication with RBAC (`admin`, `analyst`, `planner`, `viewer`)
- Organization-scoped data, models, and audit logs
- Forward-looking failure risk model from load + PM history
- Docker Compose + Postgres production path
- SAP CSV import API and demo fleet seeder
- Ops dashboard with interventions for maintenance crews

## Run

```powershell
python -m pip install -r requirements.txt
python -m scripts.seed_cli
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Login: `admin@gridsense.example` / `ChangeMeNow!23`
