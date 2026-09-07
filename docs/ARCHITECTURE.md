# Architecture and Persistence

## Components

```text
React/Vite
   │ authenticated REST + WebSocket
FastAPI
   ├── authentication and backend RBAC
   ├── administrative APIs
   ├── monitoring engine
   ├── redundancy and alerts
   ├── notifications
   └── asynchronous SQLAlchemy
          └── selected primary database
```

The frontend considers a change persisted only after a successful API response. The primary database is the source of truth for devices, links, positions, rules, integrations, and preferences.

## Initialization

1. `config.py` loads the project `.env`, then optional `backend/.env` overrides.
2. `db_bootstrap.py` checks the encrypted primary-database selection.
3. `database.py` creates the asynchronous engine.
4. The application lifespan creates tables and applies schema compatibility updates.
5. Persisted preferences are loaded into the engine.
6. Periodic monitoring starts.
7. The frontend validates its expiring session before loading protected APIs.

If schema creation or validation fails on the selected database, startup authenticates against the recorded previous database, switches the engine, and reconfigures the same `async_session_factory`. Already imported services then use the recovered binding.

If `SECRET_KEY` cannot decrypt the database-selection file, initialization stops before creating a fallback schema. This fail-closed behavior prevents an intact remote inventory from appearing to have been reset.

## Persistence

The system persists:

- Devices, interfaces, and monitoring results.
- Gateways and automatic or manual links.
- Redundancy groups.
- Topology layout.
- Private topology views owned by a user, including positions and viewport. Listing and every mutation are scoped by `user_id`; ownership is preserved during multi-database migration, and restoring a view does not overwrite global topology positions.
- Built-in and custom icons.
- Database connections and SQL sources.
- Notification integrations and rules.
- Deduplication and reminder controls.
- General preferences and audit logs.
- User accounts, expiring session digests, single-use password-reset digests, and metric aggregates.

The frontend does not use `localStorage` as the topology configuration source.

## Monitoring

The engine reads interval, retention, and thresholds from `system_settings/general`. Changes made in the interface are reloaded without restarting. The state machine requires the configured number of consecutive failures or successes.

An independent hourly maintenance task converts expiring raw samples into hourly and daily portable aggregates in bounded batches, then removes raw samples and old resolved alerts according to the configured retention. Compound indexes support historical target/status queries, and active alerts are retained. Reports combine raw and aggregated samples so availability remains available after raw data expires.

All non-public HTTP and WebSocket operations use expiring bearer sessions. REST sends the bearer token in its authorization header; WebSocket sends it in the first private message rather than the URL. Passwords use salted scrypt hashes, only session and recovery-code digests are persisted, and backend middleware enforces Viewer, Operator, and Administrator permissions. The first account is created through a deployment-specific, one-time bootstrap token; there is no built-in administrative identity.

The monitoring probe loop and retention maintenance run as separate asynchronous tasks. Retention reads bounded batches so cleanup does not load the complete historical table into memory or delay a monitoring cycle.

## Notifications

The alert engine deduplicates by target while an alert remains active. Rules define the event, severity, channels, recipients, reminder, and recovery behavior. `notification_deliveries` records the latest delivery and count to prevent continuous repetition.

Severity is based on operational impact, not on the optional device importance flag. After the state machine confirms the configured number of failed probes, every device transition to `OFFLINE` creates a `CRITICAL` incident. A dependency-affected or otherwise degraded state creates a `WARNING`; degraded redundancy is also `WARNING`, while complete redundancy loss is `CRITICAL`. Recovery is informational and resolves the active incident.

Rule severity is a minimum threshold: `INFORMATION` matches all severities, `WARNING` matches warning and critical events, and `CRITICAL` matches critical events only. This permits one escalation rule to cover failures without duplicating channel configuration.

Notification integrations normally live in the active primary database. When EMAIL has not yet been persisted, the API exposes a password-masked SMTP view derived from `.env`; invitation and recovery delivery use the same fallback. TLS contexts use the packaged CA bundle so a Python installation under a custom prefix does not silently lose certificate verification.

## Backup

The current format is `netmonitor-config`, version 1. File IDs are remapped during restoration to preserve relationships even when the destination already contains records. Secrets are excluded.

## Deliberate limits

- Discovery: 1,024 hosts; 64 custom ports or the backend-managed Top 100 list per scan. Host discovery always precedes optional TCP checks.
- Device analytics: portable ordered reads from `monitoring_results`; time bucketing, availability, and outage reconstruction run in the application layer without dialect-specific SQL.
- Alerts, history, and reports share portable date/target/status filters. Report CSV exports reuse the same filter pipeline as the on-screen metrics.
- SNMP: up to 128 interfaces per discovered device.
- SQL source: one `SELECT` statement, up to 10,000 characters and 100 returned rows.
- Custom icon: 512 KB, SVG or PNG.
