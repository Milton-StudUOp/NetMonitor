# Operations and Upgrades

## Start and stop

Run the backend from the repository installation:

```bash
cd /var/www/cln/NetMonitor/backend
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 5555
```

Use `--reload` only during development. For an internet-facing deployment, place the frontend and API behind HTTPS, restrict firewall access, and use a supervised production ASGI process.

The development frontend listens on port 3389 and proxies `/api` and `/ws` to `127.0.0.1:5555`. If Vite reports `ECONNREFUSED 127.0.0.1:5555`, verify that the backend is listening on port 5555. If a hot-reload module unexpectedly returns an empty response, restart Vite once with `npm run dev -- --host 0.0.0.0 --port 3389 --force`.

Basic availability:

```bash
curl http://127.0.0.1:5555/health
```

The public health endpoint reports process availability only. Authenticated administrators should use **System Health** for database latency, monitoring-cycle status, storage, counters, discovery activity, sessions, notifications, and WebSocket connections.

## Alert severity and delivery checks

A device outage is always `CRITICAL` after the configured consecutive-failure threshold is reached. `WARNING` represents degraded operation, such as an upstream/partial-link condition or degraded redundancy; total redundancy loss is `CRITICAL`. The device's optional importance setting does not downgrade an outage.

Notification-rule severity is a minimum threshold. For example, a rule configured as `WARNING` accepts both warning and critical incidents. If a confirmed outage does not produce an email:

1. Confirm that an active `CRITICAL` incident exists in **Alerts**.
2. Confirm that the rule is enabled, includes the event type, and has minimum severity `WARNING` or `CRITICAL`.
3. Confirm that the EMAIL channel is enabled and that **Save & Test** succeeds.
4. Inspect **System Health** for the latest notification-delivery status and sanitized error category.
5. Verify SMTP network access, recipient addresses, and TLS mode: STARTTLS on port 587 or implicit TLS on port 465.

Do not lower TLS verification or print credentials while diagnosing delivery.

Production defaults suppress SQL statement logging, SQL parameters, per-device probe noise, and Uvicorn access lines. Do not add tokens, SMTP credentials, SNMP secrets, full exception strings, or inventory addresses to terminal logs. Security-relevant outcomes belong in the database audit trail using non-secret summaries.

For SMTP on Python compiled under `/opt` or another custom prefix, NetMonitor uses the `certifi` CA bundle explicitly. Never work around certificate errors with an unverified TLS context. Port 587 conventionally uses STARTTLS; port 465 uses implicit TLS.

For a local WhatsApp Web bridge, run `npm run start:local` as a supervised service or `npm run start:qr` during initial linking. The bridge binds to `127.0.0.1:3010`, loads its token from the project `.env`, and must remain running for delivery. Confirm status `READY` in **Settings → Notifications → WhatsApp** after restarting the host. Back up the restricted session directory separately only if the deployment's security policy permits linked-device session backups.

When testing a channel with multiple recipients, separate destinations with commas, semicolons, or line breaks, save the integration, and verify delivery to every destination. WhatsApp Web numbers use country code plus subscriber number as 8–15 digits only. A successful test to one destination does not prove that the remaining addresses, Chat IDs, or numbers are valid.

## Persistent state

Back up all applicable items:

- `.env` without committing or transmitting it insecurely.
- `backend/.active-database` when an administrative database selection is active.
- `backend/network_monitor.db` when SQLite is the primary database.
- A native backup of the selected PostgreSQL, MySQL, SQL Server, or Oracle database.
- Certificates, reverse-proxy configuration, and service definitions maintained outside this repository.

The JSON configuration export excludes passwords, tokens, and SNMP communities and is not a replacement for a database backup.

## Upgrade procedure

1. Record the running revision and stop the backend.
2. Back up persistent state and the primary database.
3. Preserve the current `SECRET_KEY`.
4. Update the source code.
5. Activate the Python 3.12 virtual environment and install `backend/requirements.txt`.
6. Run backend tests and compile checks.
7. Run `npm ci` and `npm run build` in `frontend`.
8. Start the backend and inspect startup logs.
9. Verify `/health`, login, **System Health**, inventory counts, topology, and one monitoring cycle.
10. Retain the backups until operational validation is complete.

Startup creates missing tables and applies the portable compatibility migrations in `schema_migrations.py`. It does not intentionally clear existing tables.

## Phase A data lifecycle

Raw monitoring samples are retained according to the administrator setting. An independent hourly maintenance task:

1. Selects expired raw records in bounded batches.
2. Merges them into hourly and daily aggregates.
3. Deletes only the raw records included in the completed batch.
4. Removes aggregates beyond aggregate retention.
5. Removes old resolved alerts while preserving active alerts.

Compound indexes support target/time and status/time history queries. Reports include aggregate sample counts when the corresponding raw samples no longer exist.

## “My inventory disappeared” checklist

Do not initialize or overwrite databases immediately. Check in this order:

1. Confirm that the intended `.env` is loaded. The project `.env` is read first and `backend/.env`, if present, overrides it.
2. Confirm that `backend/.active-database` exists when a database was promoted through the UI.
3. Read the startup error. A `SECRET_KEY cannot decrypt` message means the selected database is still recorded but the key changed.
4. Restore the exact previous `SECRET_KEY`; do not delete the activation file.
5. Verify the selected database using read-only counts before performing migrations or imports.

An empty local SQLite file does not prove data loss when the installation previously used a remote database. The remote records remain independent of the encrypted local connection selector.

## Recovery principles

- Never remove `backend/.active-database` without first copying it to a safe location.
- Never point recovery tests at a writable production database unless the operation is explicitly designed to be read-only.
- Never replace `SECRET_KEY` merely to resolve a startup error.
- Prefer restoring the previous key or a verified backup.
- If credentials must be re-entered, preserve the activation file until the remote database has been identified and validated.

## Validation commands

```bash
cd backend
source venv/bin/activate
python -m pytest -q
python -m compileall -q app
python -c "from sqlalchemy.orm import configure_mappers; import app.models; configure_mappers()"

cd ../frontend
npm ci
npm run build
```

Real multidatabase tests require explicitly configured disposable database URLs as described in [Databases](DATABASES.md).
