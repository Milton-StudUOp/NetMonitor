# Premium Implementation Status

This document replaces the initial specification and records the effective state of the `premium` branch.

## Acceptance criteria

| Requirement | Status | Implementation |
|---|---|---|
| Discover IP addresses, ranges, and CIDR blocks | Complete | `/api/discovery/scan` |
| Configurable ICMP and TCP ports | Complete | Safety limits applied |
| SNMPv2c and SNMPv3 | Complete | SysName, SysDescr, and up to 128 interfaces |
| Select and edit before import | Complete | Discovery screen |
| Do not persist discovery credentials | Complete | Credentials exist only in the request |
| Icon library | Complete | Built-in and custom SVG/PNG |
| Icons reflected in every view | Complete | Central `devices.icon_id` field |
| Persistent layout | Complete | `topology_positions`, independent of localStorage |
| Multiple database connections | Complete | SQLite/PostgreSQL/MySQL/MSSQL/Oracle |
| Select a primary database | Complete | Migration, validation, and activation after restart |
| Multi-database identities/sequences | Complete | PostgreSQL/MySQL/MSSQL/Oracle adapters |
| Database rollback | Complete | Validated manual rollback and automatic startup fallback |
| External SQL sources | Complete | Parameterized and limited SELECT |
| Email, Telegram, and WhatsApp | Complete | Encrypted credentials and individual tests |
| Notification rules | Complete | Events, severity, channels, recovery, and reminders |
| Deduplication | Complete | Active alert + `notification_deliveries` |
| Persistence after restart | Complete | Database as source of truth with automatic loading |
| Operational retention and thresholds | Complete | Reloaded by the monitoring engine |
| Export and import | Complete | Inventory, topology, redundancy, rules, and preferences |
| Secrets excluded from backups and APIs | Complete | Masked responses and credential-free exports |
| Audit log | Complete | Relevant administrative operations |

## Architectural decisions

- SQLite remains the local fallback.
- Database promotion never deletes the source.
- The destination must be empty to prevent destructive merging.
- Switching engines requires a backend restart.
- `SECRET_KEY` protects tokens, passwords, and the primary-database selection.
- WhatsApp depends on an official API or configurable provider; WhatsApp Web is not used.
- The frontend confirms changes only after backend success.

## Automated validation

`backend/tests/test_platform.py` covers:

- Absence of secrets in responses.
- Blocking destructive SQL.
- Read-only source execution.
- Backup and restoration with gateway, link, and layout.
- Complete migration to a new primary database.
- Activation-file encryption.

Run:

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest -q

cd ..\frontend
npm run build
```

## Recommended operation

Before production, configure authentication or a reverse proxy, HTTPS, a unique `SECRET_KEY`, PostgreSQL with TLS, native backups, and least-privilege users. See [SECURITY.md](SECURITY.md), [architecture](docs/ARCHITECTURE.md), and [databases](docs/DATABASES.md).
