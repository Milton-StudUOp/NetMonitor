# NetMonitor Premium

Network infrastructure monitoring platform with automatic discovery, persistent topology, redundancy analysis, multi-channel alerts, and an administrator-selectable database.

> The `main` branch represents the free edition. Advanced development is available on the `premium` branch.

## Features

- ICMP, TCP, HTTP/HTTPS, and SNMP monitoring.
- Discovery by IP address, range, or CIDR using SNMPv2c and SNMPv3.
- Hostname, SNMP description, manufacturer, model, and interface identification.
- Selective import of discovered devices.
- Associated gateway and automatic primary-link creation.
- Automatic or free-form topology with positions persisted in the backend.
- Built-in icon library and sanitized SVG/PNG uploads.
- Redundancy through links or directly between devices.
- Normal, degraded, and critical states with dependency diagnostics.
- SMTP email, Telegram, and WhatsApp through an official API/provider.
- Rules, deduplication, reminders, and recovery notifications.
- SQLite by default, with SQLite, PostgreSQL, MySQL, SQL Server, or Oracle promotion to the primary database.
- Validated migration before switching the primary database.
- Read-only external SQL data sources limited to 100 records.
- Inventory, topology, redundancy, rules, and preferences backup and restore.
- Local accounts, role-based access, first-access passwords, self-service password changes, and email recovery.
- Password hashing, encrypted integration secrets, session-token digests, and an audit trail.

## Local quick start

Requirements: Python 3.12+, Node.js 20+, and npm 10+.

```powershell
git clone https://github.com/Milton-StudUOp/NetMonitor.git
cd NetMonitor
git switch premium

cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 5555
```

In another terminal:

```powershell
cd frontend
npm ci
npm run dev -- --host 0.0.0.0
```

Open:

- Development interface: <http://localhost:3389>
- Docker interface: <http://localhost:3000>
- API: <http://localhost:5555>
- Swagger: <http://localhost:5555/docs>
- Health check: <http://localhost:5555/health>

### Linux without Docker

```bash
git clone https://github.com/Milton-StudUOp/NetMonitor.git
cd NetMonitor
git switch premium
cp .env.example .env

cd backend
python3.12 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 5555
```

In another terminal:

```bash
cd frontend
npm ci
npm run dev -- --host 0.0.0.0
```

The backend loads the project-level `.env` and optionally `backend/.env`; when both exist, the backend-specific file takes precedence. Keep one authoritative file whenever possible.

### First administrator and secure configuration

Authentication has no built-in username, password, API token, SNMP community, or fallback secret. Before starting the backend, set unique values in `.env` for `SECRET_KEY`, `BOOTSTRAP_TOKEN`, and `CORS_ALLOWED_ORIGINS`. Generate both secrets independently, for example:

```bash
python3.12 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Open the frontend, select **Create initial administrator**, and enter the one-time bootstrap token. After the account is created, remove `BOOTSTRAP_TOKEN` from `.env` and restart the backend. Keep `SECRET_KEY` stable because it protects encrypted integration credentials. Never enable `AUTH_DISABLED` outside isolated automated tests.

The available roles are Viewer (read-only), Operator (incident handling, approved discovery, and device management), and Administrator (users, integrations, databases, settings, and System Health). Device mutation controls are hidden from Viewer accounts and every permission is independently enforced by the backend. Sessions expire according to `AUTH_SESSION_MINUTES`; only token digests are stored in the database.

Administrators invite users with a username, full name, email, and role. NetMonitor generates a 10-character readable temporary password and requires its replacement on first access. Passwords contain at least 9 characters. **Forgot password?** sends a single-use six-character uppercase alphanumeric code, displayed as six individual input boxes, with expiration controlled by `PASSWORD_RESET_MINUTES`. Recovery requests are deliberately account-neutral and rate limited.

See [Authentication and access control](docs/AUTHENTICATION.md) for the complete permission and recovery model.

## Upgrade an existing installation

Before upgrading, stop NetMonitor and back up all persistent state:

```bash
cp .env .env.before-upgrade
cp backend/.active-database backend/.active-database.before-upgrade
cp backend/network_monitor.db backend/network_monitor.db.before-upgrade
```

Skip files that do not exist. For PostgreSQL, MySQL, SQL Server, or Oracle, also create a native database backup. Then update dependencies and validate the application:

```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt
python -m compileall -q app
python -m pytest -q

cd ../frontend
npm ci
npm run build
```

Keep the existing `SECRET_KEY`. It encrypts the active multidatabase selection and integration credentials; replacing it does not delete records, but makes the encrypted connection information unreadable. On startup, NetMonitor now refuses to silently switch to an empty fallback database when the key is incompatible.

Phase A adds authentication tables and metric aggregates through the startup schema process. Existing devices, links, alerts, topology, rules, and metrics remain in place. After the first Phase A startup, use **Initial administrator setup** once, then remove `BOOTSTRAP_TOKEN` and restart.

## Docker

```bash
cp .env.example .env
docker compose up -d --build
```

Change `POSTGRES_PASSWORD` and `SECRET_KEY` before starting. With Docker, PostgreSQL is the initial primary database, and the `pgdata` and `redisdata` volumes provide persistence.

## Primary database

Without additional configuration, local development uses `backend/network_monitor.db` (SQLite). The **Settings → Databases** screen lets administrators register another connection and select **Use as Primary**.

The promotion process:

1. Tests the destination.
2. Requires an empty database.
3. Creates the schema.
4. Migrates all records in a transaction.
5. Validates counts for each table.
6. Stores the selection in an encrypted local file.
7. Requests a backend restart.

The previous database is not deleted. Failures never trigger a silent fallback: startup stops and an administrator must explicitly validate and select the previous database. Promotion uses FK-derived ordering, consistent snapshots, bounded batches, transactional validation, and UTC sessions. See [Database migration](docs/DATABASES.md).

Changing `SECRET_KEY` is different from a database outage: NetMonitor stops with an explicit decryption error and never opens an empty SQLite database in its place.

## Phase A operations

- Every non-public REST endpoint and WebSocket connection requires an expiring session. WebSocket credentials are sent in the first private protocol message, never in the connection URL.
- Alerts and History use server-side pagination.
- Expiring raw samples are processed in bounded batches into hourly and daily aggregates.
- Reports combine raw and daily aggregate data after raw retention expires.
- Retention maintenance runs separately from probe cycles.
- Administrators can inspect database latency, monitoring cycles, storage, sessions, alerts, notification deliveries, discovery jobs, and WebSocket clients under **System Health**.

See [Operations](docs/OPERATIONS.md) for startup, health checks, backups, and incident recovery.

## Network discovery

In **Discovery**, enter one of the following formats:

```text
192.168.1.15
192.168.1.10-192.168.1.100
192.168.1.0/24
```

Only the target is required. Discovery first identifies active hosts through ICMP, the local ARP cache, and optional SNMP. It can then perform no TCP scan, scan the backend-managed Top 100 TCP ports, or scan up to 64 custom ports. Safe is the default profile; Normal increases concurrency, while Aggressive must be explicitly enabled by an administrator with `ALLOW_AGGRESSIVE_DISCOVERY=true`.

Scans expose live host/port counters, elapsed time, progress, and controlled cancellation. Each scan is limited to 1,024 hosts. TCP checks are performed only against hosts already identified as active, and discovery credentials are removed from memory when the job finishes. Run scans only on authorized networks.

## Device analytics

Select a device name or **Metrics** under **Devices** to open its operational detail. The view provides availability, average and maximum latency, packet loss, downtime, a performance chart, an availability timeline, and exact outage/recovery periods. Available filters are 24 hours, 7 days, 30 days, and 90 days.

Analytics use portable SQLAlchemy filtering and aggregate records in the application layer, keeping the feature compatible with every supported database backend.

## Operational filters and exports

- **Alerts** can be filtered by text, severity, active/resolved state, source type and ID, date range, and result limit. Trigger and recovery timestamps are shown on every incident.
- **History** provides independent filters for probes and incidents, including target, state, date range, and search.
- **Reports** support preset or custom periods, target type/ID, alert severity, and probe state. The filtered result can be exported as a UTF-8 CSV containing summary metrics, incidents, and probe records.

All date and target filters use portable SQLAlchemy expressions and do not depend on a specific database dialect.

## Topology and icons

- **Automatic** recalculates the hierarchy.
- **Free** allows devices to be dragged and persists their coordinates in the database.
- **Reorganize** recalculates and stores a new arrangement.
- **Save View** creates a private, named copy of the current positions, mode, zoom, and viewport for the authenticated user.
- **My saved views** only lists views owned by the authenticated user. Users, including Viewers, can create, update, restore, and delete only their own views.
- **Restore** restores a private view in the current browser without overwriting another user's topology view.
- Choose an icon under **Devices → Edit → Device icon**.
- Upload custom icons under **Settings → Icons**.

## Backup

Under **Settings → System & Backup**:

- **Export Configuration** generates versioned JSON.
- **Import Backup** restores icons, devices, interfaces, links, redundancy, positions, rules, and preferences.

Passwords, tokens, and SNMP communities are never exported.

## Notifications

Configure channels under **Settings → Notifications**:

- **SMTP Email** supports unauthenticated or authenticated SMTP, STARTTLS, and implicit TLS. Do not enable STARTTLS and implicit TLS at the same time.
- **Telegram** requires a BotFather token and supports multiple destination Chat IDs, including groups and channels.
- **WhatsApp API** requires an HTTP(S) provider endpoint and bearer token, and supports multiple recipient numbers. The endpoint must accept `sender`, `recipient`, and `message` JSON fields.

Use **Save & Test** before enabling production rules. Rules can filter events by type, minimum severity, and source text; select one or more channels; add rule-specific recipients; send reminders; and notify on recovery. A `WARNING` rule therefore receives warning and critical events, while a `CRITICAL` rule receives only critical events. Secrets are encrypted at rest and are never returned by the API.

Operational severity is classified consistently:

- `CRITICAL`: any confirmed device outage, regardless of the device's optional importance flag, and a total redundancy-group outage.
- `WARNING`: degraded service, including an upstream dependency/partial-link condition and degraded redundancy. Performance-threshold warnings, such as excessive latency or packet loss, use this level when enabled.
- `INFORMATION`: recovery and non-failure lifecycle information.

The configured consecutive-failure threshold still applies before an outage is confirmed. This prevents a single transient probe failure from immediately creating a critical incident. Active incidents are deduplicated and recovery notifications are generated when the affected target returns to service.

When no EMAIL integration exists in the active database, the Settings screen loads SMTP host, port, username, sender, recipients, and encryption mode from `.env`. The password is represented only as **Configured**. Saving the imported configuration stores that password encrypted in the active database. Account invitation and recovery email also use this environment configuration as a secure fallback.

## Tests

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest -q
.\venv\Scripts\python.exe -m compileall app

cd ..\frontend
npm run build
```

## Documentation

- [Architecture and persistence](docs/ARCHITECTURE.md)
- [Authentication and access control](docs/AUTHENTICATION.md)
- [Databases and migration](docs/DATABASES.md)
- [Operations and upgrades](docs/OPERATIONS.md)
- [Security](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
- [Premium specification status](improvement.md)

## License

The free edition published on the `main` branch is distributed under the [MIT License](LICENSE). Confirm the terms applicable to the premium branch before redistributing it.
