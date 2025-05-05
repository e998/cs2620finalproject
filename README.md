# CS2620 Final Project
## Esther An and Sammi Zhu

## Setup

1. **Clone the repository and navigate to the project root.**

2. **Install dependencies:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements.txt
```

3. **Configure environment variables:**
  - `SECRET_KEY` (for Flask session)
  - `DATABASE_URL` (PostgreSQL connection string)
  - `LEADER_NODE_URL` (for leader election)
  - `HOST` and `PORT` (for app/health server binding, optional)
  - `PEER_NODES` (for peer discovery)
  - `MY_IP` (personal IP address) 

- Separately, export `FLASK_APP=app:create_app`
---

## Running the Sales App

The main sales web app is started from the project root:
```bash
python3 run.py
```
- By default, it runs on the host/port specified in your `.env` (or `10.250.244.76:5001`).
- Access the app in your browser at `http://<HOST>:<PORT>`.

---

## Running the Health Dashboard

The health dashboard is a separate Flask app:
```bash
python3 health/healthapp.py
```
- By default, it runs on the host/port specified in your `.env` (or fallback values).
- Access the dashboard in your browser at `http://<HEALTH_NODE_URL>:<HEALTH_PORT>`.

---

## Running Tests

All tests are located in the `tests/` directory and use `pytest`:
```bash
pytest
```
- This runs both sales app and health app tests.
- Make sure your test database and environment variables are properly configured for testing.

---

## Troubleshooting
- Ensure PostgreSQL and Redis are running and accessible.
- If migrations are needed, use Flask-Migrate:
  ```bash
  flask db upgrade
  ```
- If you encounter issues with environment variables, double-check your `.env` file and restart your shell/app.

---

For further details, see code comments and docstrings throughout the codebase.
