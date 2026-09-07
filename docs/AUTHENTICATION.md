# Authentication and Access Control

## Security model

NetMonitor uses local accounts and expiring bearer sessions. There is no built-in administrator, password, bootstrap token, API token, or SNMP community. Passwords are stored as salted scrypt hashes. A random session token is returned only to the client; the database stores its SHA-256 digest.

REST authorization is enforced by FastAPI middleware. WebSocket clients authenticate in the first message after connection acceptance; session tokens are never placed in WebSocket URLs or access logs. Frontend visibility rules improve usability but are not the security boundary.

## Required environment

Set these values before the first startup:

```text
SECRET_KEY=<unique stable random value>
BOOTSTRAP_TOKEN=<different one-time random value>
AUTH_SESSION_MINUTES=<session lifetime>
PASSWORD_SCRYPT_N=<approved scrypt cost>
PASSWORD_SCRYPT_R=<approved scrypt block size>
PASSWORD_SCRYPT_P=<approved scrypt parallelization>
CORS_ALLOWED_ORIGINS=<comma-separated exact frontend origins>
```

Generate `SECRET_KEY` and `BOOTSTRAP_TOKEN` independently:

```bash
python3.12 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Do not copy values from `.env.example` unchanged. Do not use `AUTH_DISABLED` in a deployed instance; it exists only for isolated automated tests.

## Initial administrator

1. Start the backend and frontend.
2. Open the login screen and select **Initial administrator setup**.
3. Enter a unique username, full name, password of at least 9 characters, and the configured bootstrap token.
4. Confirm that login works.
5. Remove `BOOTSTRAP_TOKEN` from `.env` and restart the backend.

Bootstrap is rejected after the first user exists, even if the environment variable remains configured.

## Invitations and first access

Administrators create users with a unique username, full name, email address, and role. The full name is used in the `Hello Full Name` email greeting; the username appears only in the credential section. NetMonitor generates a cryptographically random, readable 10-character temporary password, stores only its scrypt hash, and sends the credential through SMTP. The administrator never sees or chooses the temporary password.

Before inviting users, configure and successfully test **Settings → Notifications → SMTP Email**. If no EMAIL record exists in the active database, the screen automatically loads the non-secret SMTP fields from `.env` and indicates whether a password is configured without returning it. Persisted database configuration takes precedence over the environment fallback. Account messages are delivered only to the account email, not to the operational alert recipient list.

On first login, all APIs except session and password self-service are blocked until the user replaces the temporary password. The invitation email includes a responsive HTML layout and plain-text alternative. Account creation is rolled back if SMTP is not configured or delivery fails.

Existing accounts created before this feature may have no email. An administrator must add one under **Settings → Users** before email recovery is available.

## Self-service and recovery

- The key button beside the signed-in user opens voluntary password change.
- The current password is required, and the new password must contain at least 9 characters and differ from the current one.
- Other active sessions for the account are invalidated after a password change.
- **Forgot password?** always returns the same response whether an account exists, preventing account discovery.
- Recovery codes contain exactly six uppercase letters or digits. They are random, stored only as SHA-256 digests, single-use, and expire according to `PASSWORD_RESET_MINUTES`.
- Requesting a new successfully delivered code invalidates previous unused codes and is throttled to one delivery per account per minute. A failed SMTP delivery removes the unusable token instead of activating the cooldown.
- Code submission is limited to 10 attempts per client origin within 10 minutes.
- A successful recovery invalidates every existing session for that user.

## Roles

| Role | Access |
|---|---|
| Viewer | Read dashboards, topology, inventory, metrics, history, alerts, and reports. |
| Operator | Viewer access plus resolving incidents, running approved discovery, and creating, editing, importing, or deleting devices. |
| Administrator | Full management of users, integrations, databases, settings, configuration, audit records, and System Health. |

Permissions are checked on every request. An active administrator cannot disable or demote their own account.

## Session behavior

- The frontend keeps the bearer token in `sessionStorage`, so it is scoped to the browser tab session.
- API requests attach the token through the Axios client.
- WebSocket connections send the same token in the first application message after the URL connection is established; query strings never contain it.
- A successful interactive login replaces any previous frontend route with `/`, so the user enters the Dashboard.
- An expired, disabled, deleted, or unknown session returns HTTP 401 and is removed from the frontend.
- Logout deletes the server-side session using the same database transaction that authenticated it.
- If the backend cannot be reached, the login gate times out and offers **Try again** rather than waiting indefinitely.

## `SECRET_KEY` changes

Keep `SECRET_KEY` stable across upgrades and restarts. It protects the selected primary-database URL and persisted integration secrets. Changing it does not erase the remote database, but NetMonitor can no longer decrypt how to reach it.

When `backend/.active-database` exists and the key is incompatible, startup fails explicitly. NetMonitor intentionally does not fall back to SQLite because that could make an intact installation look empty.

Before any planned rotation, back up `.env`, `backend/.active-database`, the primary database, and integration configuration. A rotation must decrypt every protected value with the old key and encrypt it with the new key as one controlled maintenance operation.

## Future identity providers

The local user/session model is designed so LDAP, Active Directory, or OIDC can be added later. External identity integration is not currently implemented.
