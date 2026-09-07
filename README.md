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
- Password and token encryption with an audit trail.

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

- Interface: <http://localhost:3000>
- API: <http://localhost:5555>
- Swagger: <http://localhost:5555/docs>
- Health check: <http://localhost:5555/health>

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

The previous database is not deleted. If the promoted database fails during startup, the backend automatically returns to the previous one. See [Database migration](docs/DATABASES.md).

## Network discovery

In **Discovery**, enter one of the following formats:

```text
192.168.1.15
192.168.1.10-192.168.1.100
192.168.1.0/24
```

Only the target is required. Discovery first identifies active hosts through ICMP, the local ARP cache, and optional SNMP. It can then perform no TCP scan, scan the backend-managed Top 100 TCP ports, or scan up to 64 custom ports. Safe is the default profile; Normal increases concurrency, while Aggressive must be explicitly enabled by an administrator with `ALLOW_AGGRESSIVE_DISCOVERY=true`.

Scans expose live host/port counters, elapsed time, progress, and controlled cancellation. Each scan is limited to 1,024 hosts. TCP checks are performed only against hosts already identified as active, and discovery credentials are removed from memory when the job finishes. Run scans only on authorized networks.

## Topology and icons

- **Automatic** recalculates the hierarchy.
- **Free** allows devices to be dragged and persists their coordinates in the database.
- **Reorganize** recalculates and stores a new arrangement.
- **Save View** creates a named copy of the current positions, mode, zoom, and viewport.
- **Restore** restores a saved view if the topology becomes disorganized.
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

Use **Save & Test** before enabling production rules. Rules can filter events by type, severity, and source text; select one or more channels; add rule-specific recipients; send reminders; and notify on recovery. Secrets are encrypted at rest and are never returned by the API.

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
- [Databases and migration](docs/DATABASES.md)
- [Security](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
- [Premium specification status](improvement.md)

## License

The free edition published on the `main` branch is distributed under the [MIT License](LICENSE). Confirm the terms applicable to the premium branch before redistributing it.
