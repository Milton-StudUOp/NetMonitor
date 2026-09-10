# Security Policy

## Secrets

Database and SMTP passwords, Telegram/WhatsApp tokens, and other persisted credentials are protected with Fernet using a key derived from `SECRET_KEY`.

NetMonitor does not ship with a default administrator, password, session token, bootstrap token, or SNMP community. The initial administrator can only be created with the deployment-specific `BOOTSTRAP_TOKEN`; remove that variable after bootstrap. Passwords are stored as salted scrypt hashes and bearer sessions are stored only as SHA-256 digests with a configured expiry.

Authorization is enforced by the backend with Viewer, Operator, and Administrator roles. Hiding controls in the frontend is only a usability measure and is not the security boundary.

Invitation passwords and six-character uppercase alphanumeric recovery codes are generated with the operating system cryptographic random source. Only password hashes or token digests are persisted. Recovery responses do not reveal whether an email address belongs to an account, codes are single-use and time-limited, delivery is throttled, submissions are rate limited, and password recovery invalidates active sessions.

- Use a long, random, and stable `SECRET_KEY`.
- Changing the key invalidates previously encrypted secrets.
- A mismatched key now stops startup instead of silently selecting an empty fallback database.
- Never publish `.env`, `.active-database`, local databases, certificates, or real inventories.
- APIs return only indicators such as `password_configured` and `secrets_configured`.
- WebSocket session tokens are transmitted in the first private protocol message and never in a query string.
- SQL parameters, per-device probe details, and HTTP access lines are disabled in normal terminal logging.
- Backups exclude passwords, tokens, and SNMP communities.

Generate a key with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Generate a different value for `BOOTSTRAP_TOKEN`. After creating the first administrator, remove the bootstrap token from the runtime environment and restart. Back up the stable `SECRET_KEY` through the deployment's approved secret-management process; do not include it in Git or configuration exports.

See [Authentication](docs/AUTHENTICATION.md) for session and role behavior and [Operations](docs/OPERATIONS.md) before upgrades or key rotation.

## Discovery and monitoring

Use ICMP, TCP, and SNMP only on networks where you have authorization. Restrict administrative access to NetMonitor and place the interface behind HTTPS and authentication before exposing it outside a trusted network.

## Custom SVG files

Uploads accept SVG and PNG files up to 512 KB. SVG files containing `script`, a `javascript:` URI, or an entity declaration are rejected. Visually review custom assets before use.

## SQL and databases

- Data sources accept one statement beginning with `SELECT`.
- Results are limited to 100 rows.
- Use least-privilege database users.
- Primary database promotion requires an empty destination and per-table validation.
- SQL Server also requires Microsoft ODBC Driver 18 on the operating system.

## External communication

Telegram and WhatsApp send data to external services. Do not include unnecessary sensitive data in messages. The official/provider WhatsApp API is recommended for contractual and business-critical delivery. The optional `whatsapp-web.js` bridge is unofficial, can violate applicable platform terms, and cannot guarantee that the linked account will not be restricted. It must remain isolated on localhost or the private container network, protected by a unique internal token, run as a non-root user, and store its session volume as sensitive runtime data. QR payloads and the bridge token must never be logged, committed, backed up through the configuration export, or exposed through a public reverse proxy.

## Reporting vulnerabilities

Do not publish exploitable details in an issue. Use private GitHub Security Advisories or the private channel defined by the maintainer. Include the version, impact, minimal reproduction steps, and a proposed mitigation.
