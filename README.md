# GridSense Asset Health

Enterprise predictive maintenance for **distribution transformers (DTRs)** and **feeders**.

Challenge 18 (Energy / Telangana): predict failure risk from loading patterns and historical repairs using **SAP Plant Maintenance–shaped** data.

## Product capabilities

| Capability | Detail |
| --- | --- |
| Auth & RBAC | JWT login · roles: `admin`, `analyst`, `planner`, `viewer` |
| Multi-org ready | Organization-scoped assets, scores, models, audit |
| SAP PM ingest | CSV import for equipment, notifications, work orders, load readings |
| Risk model | Forward-looking 90-day failure model (gradient boosting) |
| Operations | Retrain, rescore, import jobs, audit trail |
| Runtime | FastAPI · SQLAlchemy · SQLite (dev) / Postgres (prod) · Docker |

## Quick start (local)

```powershell
cd c:\Users\akhil\OneDrive\Documents\predictive-maintenance-asset-health
python -m pip install -r requirements.txt
python -m scripts.seed_cli
python -m uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Open http://localhost:8080/login

**Demo login**

- Email: `admin@gridsense.example`
- Password: `ChangeMeNow!23`

Also: `planner@`, `analyst@`, `viewer@` with the same password.

## Production (Docker + Postgres)

```powershell
$env:SECRET_KEY = "use-a-long-random-secret"
docker compose up --build -d
docker compose exec api python -m scripts.seed_cli
```

API docs: http://localhost:8080/api/docs  
Health: http://localhost:8080/api/health  
Readiness: http://localhost:8080/api/ready

## API surface (`/api/v1`)

- `POST /auth/token` — login
- `GET /assets/summary` — KPIs + circle risk
- `GET /assets` — paginated risk ranking
- `GET /assets/{equipment_id}` — drivers, load, SAP PM history
- `POST /ops/retrain` — admin/analyst
- `POST /ops/seed` — load synthetic Telangana fleet
- `POST /ops/import/sap-csv` — multipart SAP CSV upload
- `GET /audit` — admin audit trail

## SAP PM field mapping

| Product | SAP PM concept |
| --- | --- |
| `equipment_id` | Equipment (EQUNR) |
| `functional_location` | Functional location (TPLNR) |
| `notification_id` | Notification (QMNUM) |
| `order_id` | Order (AUFNR) |
| `load_readings` | Measuring point / measurement document |

## Security notes

- Change `SECRET_KEY` and `DEFAULT_ADMIN_PASSWORD` before any shared deploy
- Set `ALLOW_DEMO_LOGIN=false` in production
- All mutating ops are audited with user + organization
- Responses include security headers; HSTS enabled when `APP_ENV=production`

## Tests

```powershell
python -m pytest -q
```
