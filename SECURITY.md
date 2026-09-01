# Security Policy

## Secrets

Database and SMTP passwords, Telegram/WhatsApp tokens, and other persisted credentials are protected with Fernet using a key derived from `SECRET_KEY`.

- Use a long, random, and stable `SECRET_KEY`.
- Changing the key invalidates previously encrypted secrets.
- Never publish `.env`, `.active-database`, local databases, certificates, or real inventories.
- APIs return only indicators such as `password_configured` and `secrets_configured`.
- Backups exclude passwords, tokens, and SNMP communities.

Generate a key with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

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

Telegram and WhatsApp send data to the configured provider. Do not include unnecessary sensitive data in messages. For WhatsApp, use only an official API or a contractually authorized provider; WhatsApp Web automation is not supported.

## Reporting vulnerabilities

Do not publish exploitable details in an issue. Use private GitHub Security Advisories or the private channel defined by the maintainer. Include the version, impact, minimal reproduction steps, and a proposed mitigation.
