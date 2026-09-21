# Operations and Upgrades

`<INSTALL_DIR>` means the directory where this repository was cloned or
deployed. It is intentionally not a fixed server path; for example it might be
`/srv/netmonitor` on Linux, `/Users/name/NetMonitor` on macOS, or a directory
chosen by the operator on Windows.

## Start and stop

Run the backend from the repository installation:

```bash
cd <INSTALL_DIR>/backend
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 5555
```

Use `--reload` only during development. For an internet-facing deployment, place the frontend and API behind HTTPS, restrict firewall access, and use a supervised production ASGI process.

Do not run `--reload` on the production server. It starts a second watcher
process and makes recovery from transient socket failures less predictable. If
the log reports `Too many open files`, stop all Uvicorn instances, verify that
only one backend process remains, then restart without `--reload`:

```bash
pkill -f 'uvicorn app.main:app'
cd <INSTALL_DIR>/backend
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 5555
```

For a persistent deployment, use a systemd service with `LimitNOFILE=65536`.
The application also keeps MySQL connections, background discovery work, and
WebSocket sessions bounded; increasing OS limits must not substitute for
correct connection lifecycle management.

The development frontend listens on port 3389 and proxies `/api` and `/ws` to `127.0.0.1:5555`. If Vite reports `ECONNREFUSED 127.0.0.1:5555`, verify that the backend is listening on port 5555. If a hot-reload module unexpectedly returns an empty response, restart Vite once with `npm run dev -- --host 0.0.0.0 --port 3389 --force`.

Basic availability:

```bash
curl http://127.0.0.1:5555/health
```

The public health endpoint reports process availability only. Authenticated administrators should use **System Health** for database latency, monitoring-cycle status, storage, counters, discovery activity, sessions, notifications, and WebSocket connections.

## Capacity baseline: 1,000 devices

NetMonitor uses a bounded local collector. ICMP probes run concurrently only
up to **Probe concurrency**, and each cycle accepts only **Probe batch size**
devices. Both values are configurable in **Settings → General** and can be
seeded through `MONITORING_PROBE_CONCURRENCY` and
`MONITORING_PROBE_BATCH_SIZE` in `.env`. The scheduler persists each device's
last probe time, so restarting the backend does not deliberately re-probe the
whole inventory in one burst.

For a first 1,000-device deployment, set a per-device interval appropriate to
the network (30–60 seconds is a sensible initial range), keep batch size at or
above the inventory size, and begin with the configured concurrency of 100.
Increase it only after measuring collector CPU, open file descriptors, database
latency, cycle duration, and deferred probes in **System Health**. A non-zero
`deferred_device_probe_count` means the collector cannot service all due
devices within its current batch capacity.

This is a single-collector capacity baseline. For high availability, use the
separate API and collector topology described below; do not use multiple ASGI
workers in a collector process because each worker is an independent scheduler.

## High availability: two collectors and API replicas

The application now has durable, database-backed collector leases. To run
approximately 1,000 devices with collector failover, use at least two hosts or
VMs and a **shared highly available primary database** (not SQLite). Configure
the same `DATABASE_URL`, `SECRET_KEY`, notification configuration, and release
on every replica. Give each collector a unique stable name:

```ini
# collector-a/.env
COLLECTOR_ENABLED=true
COLLECTOR_ID=collector-a
COLLECTOR_LEASE_SECONDS=45
MONITORING_PROBE_CONCURRENCY=100
MONITORING_PROBE_BATCH_SIZE=1000
COLLECTOR_DEVICE_CLAIM_LIMIT=500
REMOTE_MONITORING_CONCURRENCY=25
REMOTE_MONITORING_BATCH_SIZE=500

# collector-b/.env
COLLECTOR_ENABLED=true
COLLECTOR_ID=collector-b
COLLECTOR_LEASE_SECONDS=45
COLLECTOR_DEVICE_CLAIM_LIMIT=500
REMOTE_MONITORING_CONCURRENCY=25
REMOTE_MONITORING_BATCH_SIZE=500
```

The claim/batch values divide the first 1,000 due devices between two
collectors instead of letting the first-started replica reserve the complete
inventory. Keep the sum of all collector limits at least as large as the
expected simultaneous due set. Increase remote concurrency only after testing
the target protocols and the collector's descriptor/CPU limits.

Reusable systemd unit templates are in
[`deploy/systemd`](../deploy/systemd). These are Linux-only templates; replace
`@INSTALL_DIR@`, `@SERVICE_USER@`, and `@SERVICE_GROUP@` before installing one
on each applicable host. Place the corresponding restricted environment file
under `/etc/netmonitor/`. For example, from the repository root on Linux:

```bash
sed -e "s|@INSTALL_DIR@|$(pwd)|g" -e "s|@SERVICE_USER@|$USER|g" -e "s|@SERVICE_GROUP@|$(id -gn)|g" \
  deploy/systemd/netmonitor-collector.service.template | sudo tee /etc/systemd/system/netmonitor-collector.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now netmonitor-collector
sudo systemctl status netmonitor-collector
```

The templates set `Restart=always` and `LimitNOFILE=65536`; they deliberately
do not use `--reload` or multi-worker Uvicorn. Put only API replicas behind the
load balancer. If collectors should not accept user traffic, restrict their
port 5555 access to the private administration/load-balancer network with the
host firewall.

On macOS, use a `launchd` service or an approved supervisor to start the same
portable command from `<INSTALL_DIR>/backend`; on Windows, use the Service
Control Manager or an approved service wrapper. Those platforms do not consume
the Linux systemd templates. In every case, set the working directory to the
local installation directory and invoke the virtual environment's Python/Uvicorn
binary from that installation, rather than copying a path from another host.

Run the API tier separately with `COLLECTOR_ENABLED=false`, distinct
`COLLECTOR_ID` values, and at least two replicas behind a TLS-capable load
balancer. Do not use `uvicorn --workers` for collector replicas: every worker
would be an independent scheduler. One Uvicorn process per collector is the
supported topology. A failed collector's outstanding device/service lease
becomes available after the configured lease duration; verify the takeover in
**System Health → active collector IDs**.

The database itself remains a dependency: use its vendor-supported replication,
automatic failover, backups, and monitoring. Redis may be used by surrounding
infrastructure, but NetMonitor's probe ownership is stored in the primary
database to retain SQLite/PostgreSQL/MySQL/SQL Server/Oracle portability. Never
place a SQLite file on a shared network filesystem for HA.

Before declaring the service production-ready, run a representative load test
with at least 1,000 devices or safe simulators, then deliberately stop one
collector. Confirm that no device receives duplicate checks during normal
operation, that work is taken over within the lease window, and that database
latency, descriptor count, deferred probes, and alert delivery remain within
your operational thresholds.

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

## Data lifecycle

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
