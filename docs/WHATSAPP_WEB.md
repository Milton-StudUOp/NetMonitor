# WhatsApp Web Integration

## Scope and warning

NetMonitor supports two WhatsApp delivery modes:

1. **Official/provider HTTP API**, recommended for production and business-critical alerts.
2. **Linked WhatsApp Web**, implemented by the isolated `whatsapp-web.js` bridge and authenticated with a QR code.

`whatsapp-web.js` is not an official WhatsApp product. WhatsApp Web changes can interrupt delivery and use of automation can lead to account restrictions. Do not use this channel as the only path for critical incidents; configure SMTP or an official provider as a parallel channel.

## Security model

- The Node.js bridge listens on localhost by default and has no Docker host port.
- Every session and message endpoint requires `WHATSAPP_WEB_SERVICE_TOKEN`; `/health` exposes only process availability.
- FastAPI is the only supported client. The browser never receives the bridge address or token.
- QR data is kept in memory, proxied through an Administrator-only API, marked `no-store`, and never written to a NetMonitor database.
- `LocalAuth` data is sensitive because it represents a linked WhatsApp device. Store it in a restricted directory or Docker volume and exclude it from source control and configuration exports.
- The bridge validates international recipient numbers and limits message/request size.

The notification integration record and recipient list remain in the currently selected primary database. The linked-device session remains in the dedicated filesystem volume, so changing the primary database does not copy or reset the WhatsApp session.

## Configuration

Generate a unique token that is different from `SECRET_KEY` and `BOOTSTRAP_TOKEN`:

```bash
python3.12 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set the same value for `WHATSAPP_WEB_SERVICE_TOKEN` in the backend and bridge environments. For a local installation without Docker:

```text
WHATSAPP_WEB_SERVICE_URL=http://127.0.0.1:3010
WHATSAPP_WEB_SERVICE_TOKEN=<unique-internal-token>
```

For Docker Compose, keep `WHATSAPP_WEB_SERVICE_URL=http://whatsapp-web:3010`; Compose injects the shared token and persists `/data/auth` in the `whatsappauth` volume.

## Run without Docker

Install Node.js 20 or newer. On distributions where `chromium` is unavailable (including some Ubuntu Server installations), use the browser version managed by Puppeteer:

```bash
cd /var/www/cln/NetMonitor/whatsapp-web
PUPPETEER_SKIP_DOWNLOAD=true npm ci
npm run install-browser
```

The last command downloads Chrome for Testing into the Puppeteer cache. Puppeteer documents this as the compatible alternative to a system Chrome/Chromium installation. If Chrome or Chromium is already installed, the bridge automatically checks common Linux paths and no download is required.

### Recommended local startup

When the project `.env` contains `WHATSAPP_WEB_SERVICE_URL` and `WHATSAPP_WEB_SERVICE_TOKEN`, start with:

```bash
cd /var/www/cln/NetMonitor/whatsapp-web
npm run start:qr
```

Keep this process running. Successful startup progresses through `INITIALIZING`, `QR_REQUIRED`, `AUTHENTICATED`, and `READY`. No message can be sent before `READY`.

Create a protected persistent directory and start the service with the same token configured for FastAPI:

```bash
sudo install -d -m 700 -o "$USER" -g "$USER" /var/lib/netmonitor-whatsapp
export WHATSAPP_WEB_SERVICE_TOKEN='<unique-internal-token>'
export WHATSAPP_AUTH_PATH=/var/lib/netmonitor-whatsapp
npm start
```

When the project-level `.env` already contains the URL and token, the shorter local command is:

```bash
npm run start:local
```

Do not set `PUPPETEER_EXECUTABLE_PATH` when using `npm run install-browser`; the bridge locates the managed browser automatically. When using a system browser at a non-standard path, set the variable explicitly.

To also display each QR code in the private service terminal:

```bash
export WHATSAPP_PRINT_QR_TERMINAL=true
npm start
```

Or load the project `.env` and enable terminal output for this execution only:

```bash
npm run start:qr
```

The local scripts deliberately discard any previously exported bridge token before loading the project `.env`. This prevents an old shell value from causing an invisible `401 Unauthorized` mismatch between FastAPI and the bridge.

They also discard an old `PUPPETEER_EXECUTABLE_PATH` exported by the shell. If an explicitly configured browser path does not exist, the bridge falls back to system-path detection and then to the Puppeteer-managed Chrome instead of failing immediately.

Terminal QR output is opt-in because the QR grants a linked-device session to whoever scans it. Clear the terminal scrollback after linking and never capture it in centralized logs. The same QR remains available in **Settings → Notifications → WhatsApp** through the protected backend API.

The default bind address is `127.0.0.1:3010`. Use a system service for production and keep its environment file readable only by the service account.

If `WHATSAPP_AUTH_PATH` is omitted during local development, the bridge uses the ignored `whatsapp-web/.wwebjs_auth` directory. Docker continues to use the persistent `/data/auth` volume.

If a configured local path exists but is not writable by the service user, the bridge reports `whatsapp_auth_path_not_writable` and falls back to `whatsapp-web/.wwebjs_auth`. For a production service, prefer fixing directory ownership instead of relying on the fallback:

```bash
sudo install -d -m 700 -o "$USER" -g "$USER" /var/lib/netmonitor-whatsapp
```

## Link and test

1. Start the bridge and restart FastAPI after setting its environment variables.
2. Open **Settings → Notifications → WhatsApp**.
3. Select **Linked WhatsApp Web (QR code)** and enter recipients as digits with country code. Separate multiple numbers with commas, semicolons, or line breaks; for example, `258841234567, 258851234567`.
4. Save the integration, then select **Connect WhatsApp**.
5. In the phone app, open **Linked devices → Link a device** and scan the QR code.
6. Wait for status `READY`, enable the integration, and use **Save & Test**.

The bridge automatically attempts to restore a saved session after restart. **Disconnect** logs out the linked device and removes the corresponding `LocalAuth` session.

Recipient input is normalized only when the integration is saved, so separators remain visible and editable while typing. Empty entries and duplicates are removed. Each WhatsApp Web destination must contain 8–15 digits including the country code, without a leading `+`, spaces, or punctuation. Email and Telegram recipient fields use the same multi-value separators, with validation appropriate to their own channel.

## Message format

WhatsApp uses a compact operational layout instead of the longer email body:

```text
🚨 CRITICAL ALERT
Device unavailable: Core Router
Target: Core Router (192.0.2.1)
Time: 07 Sep 2026 · 19:45 UTC
Incident: NM-000042

The device did not respond to ICMP probes.

Cause: No ICMP response.
```

Recovery messages begin with `✅ RECOVERED` and omit the probable cause. Dynamic values are normalized so device names and diagnostic text cannot break WhatsApp bold formatting.

## Troubleshooting

- `UNAVAILABLE`: verify that the bridge is running and that URL/token values match.
- `401 Unauthorized`: stop the old bridge and restart with `npm run start:qr`; the local script discards a stale token exported by the shell before loading `.env`.
- `INITIALIZING` for more than 60 seconds: verify outbound HTTPS access to `web.whatsapp.com`. The bridge changes to `FAILED` with an actionable message instead of waiting indefinitely.
- `FAILED` with “No Chrome/Chromium executable”: run `npm run install-browser`, then restart the bridge.
- `EACCES` for `/var/lib/netmonitor-whatsapp`: correct ownership with `sudo install -d -m 700 -o "$USER" -g "$USER" /var/lib/netmonitor-whatsapp`. The bridge can fall back to the ignored local `.wwebjs_auth` directory.
- `QR_REQUIRED`: scan the current QR; expired QR codes are regenerated automatically.
- A recipient is rejected: remove `+`, spaces, parentheses, and hyphens; keep only 8–15 digits including the country code. For several recipients, use commas, semicolons, or one value per line.
- `AUTH_FAILURE`: disconnect, remove the invalid session through the UI, and link again.
- `DISCONNECTED`: confirm phone/network availability and reconnect.
- Request body validation error while saving: update/restart FastAPI; the WhatsApp `mode` field must be accepted by the current backend schema.
- Test delivery rejected: confirm status `READY` and use 8–15 digits including the country code, without `+`, spaces, or punctuation.

Never publish port 3010, bypass bridge authentication, disable Chromium isolation beyond the documented container flags, or copy session data into Git.
