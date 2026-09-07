# Architecture and Persistence

## Components

```text
React/Vite
   │ REST + WebSocket
FastAPI
   ├── administrative APIs
   ├── monitoring engine
   ├── redundancy and alerts
   ├── notifications
   └── asynchronous SQLAlchemy
          └── selected primary database
```

The frontend considers a change persisted only after a successful API response. The primary database is the source of truth for devices, links, positions, rules, integrations, and preferences.

## Initialization

1. `config.py` loads the environment and `.env`.
2. `db_bootstrap.py` checks the encrypted primary-database selection.
3. `database.py` creates the asynchronous engine.
4. The application lifespan creates tables and applies schema compatibility updates.
5. Persisted preferences are loaded into the engine.
6. Periodic monitoring starts.
7. The frontend loads the dashboard, topology, and settings through the APIs.

If schema creation or validation fails on the selected database, startup authenticates against the recorded previous database, switches the engine, and reconfigures the same `async_session_factory`. Already imported services then use the recovered binding.

## Persistence

The system persists:

- Devices, interfaces, and monitoring results.
- Gateways and automatic or manual links.
- Redundancy groups.
- Topology layout.
- Named topology views, including positions and viewport.
- Built-in and custom icons.
- Database connections and SQL sources.
- Notification integrations and rules.
- Deduplication and reminder controls.
- General preferences and audit logs.

The frontend does not use `localStorage` as the topology configuration source.

## Monitoring

The engine reads interval, retention, and thresholds from `system_settings/general`. Changes made in the interface are reloaded without restarting. The state machine requires the configured number of consecutive failures or successes.

An hourly cleanup removes old monitoring results and resolved alerts beyond the retention period. Active alerts are retained.

## Notifications

The alert engine deduplicates by target while an alert remains active. Rules define the event, severity, channels, recipients, reminder, and recovery behavior. `notification_deliveries` records the latest delivery and count to prevent continuous repetition.

## Backup

The current format is `netmonitor-config`, version 1. File IDs are remapped during restoration to preserve relationships even when the destination already contains records. Secrets are excluded.

## Deliberate limits

- Discovery: 1,024 hosts; 64 custom ports or the backend-managed Top 100 list per scan. Host discovery always precedes optional TCP checks.
- SNMP: up to 128 interfaces per discovered device.
- SQL source: one `SELECT` statement, up to 10,000 characters and 100 returned rows.
- Custom icon: 512 KB, SVG or PNG.
