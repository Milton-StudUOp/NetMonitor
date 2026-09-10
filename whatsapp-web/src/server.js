'use strict';

const crypto = require('crypto');
const express = require('express');
const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer');
const QRCode = require('qrcode');
const terminalQr = require('qrcode-terminal');
const { Client, LocalAuth } = require('whatsapp-web.js');

const port = Number(process.env.PORT || 3010);
const host = process.env.HOST || '127.0.0.1';
const apiToken = process.env.WHATSAPP_WEB_SERVICE_TOKEN || '';
const printQrInTerminal = /^(1|true|yes|on)$/i.test(process.env.WHATSAPP_PRINT_QR_TERMINAL || 'false');
const localAuthPath = path.resolve(__dirname, '..', '.wwebjs_auth');

function writableAuthPath() {
  const configured = process.env.WHATSAPP_AUTH_PATH || localAuthPath;
  try {
    fs.mkdirSync(configured, { recursive: true, mode: 0o700 });
    fs.accessSync(configured, fs.constants.R_OK | fs.constants.W_OK | fs.constants.X_OK);
    return configured;
  } catch (_error) {
    if (configured === localAuthPath) throw _error;
    console.warn('whatsapp_auth_path_not_writable', { fallback: localAuthPath });
    fs.mkdirSync(localAuthPath, { recursive: true, mode: 0o700 });
    fs.accessSync(localAuthPath, fs.constants.R_OK | fs.constants.W_OK | fs.constants.X_OK);
    return localAuthPath;
  }
}

const authPath = writableAuthPath();

if (apiToken.length < 32 || apiToken.includes('replace-with')) {
  throw new Error('WHATSAPP_WEB_SERVICE_TOKEN must be a unique value of at least 32 characters');
}

const state = {
  status: 'STOPPED',
  qrDataUrl: null,
  qrUpdatedAt: null,
  connectedAccount: null,
  lastError: null,
};
let client = null;
let initialization = null;
let initializationWatchdog = null;

function setStatus(status, lastError = null) {
  state.status = status;
  state.lastError = lastError;
  console.log('whatsapp_status_changed', { status });
}

function resolveBrowserExecutable() {
  const configured = process.env.PUPPETEER_EXECUTABLE_PATH;
  if (configured) {
    if (fs.existsSync(configured)) return configured;
    console.warn('whatsapp_configured_browser_not_found', { fallback: 'automatic_detection' });
  }
  const systemCandidates = [
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/usr/bin/google-chrome',
    '/usr/bin/google-chrome-stable',
    '/snap/bin/chromium',
  ];
  const systemBrowser = systemCandidates.find(candidate => fs.existsSync(candidate));
  if (systemBrowser) return systemBrowser;
  try {
    const managedBrowser = puppeteer.executablePath();
    if (managedBrowser && fs.existsSync(managedBrowser)) return managedBrowser;
  } catch (_error) {
    // The actionable error below covers an absent Puppeteer-managed browser.
  }
  throw new Error('No Chrome/Chromium executable was found. Run: npm run install-browser');
}

function safeEqual(left, right) {
  const a = Buffer.from(left || '');
  const b = Buffer.from(right || '');
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

function authorize(req, res, next) {
  const supplied = (req.get('authorization') || '').replace(/^Bearer\s+/i, '');
  if (!safeEqual(supplied, apiToken)) return res.status(401).json({ detail: 'Unauthorized' });
  next();
}

function publicState() {
  return {
    status: state.status,
    qr_data_url: state.qrDataUrl,
    qr_updated_at: state.qrUpdatedAt,
    connected_account: state.connectedAccount,
    last_error: state.lastError,
  };
}

function bindEvents(instance) {
  instance.on('qr', async qr => {
    clearTimeout(initializationWatchdog);
    setStatus('QR_REQUIRED');
    if (printQrInTerminal) {
      console.log('whatsapp_qr_required');
      terminalQr.generate(qr, { small: true });
    }
    try {
      state.qrDataUrl = await QRCode.toDataURL(qr, { errorCorrectionLevel: 'M', margin: 2, width: 320 });
      state.qrUpdatedAt = new Date().toISOString();
    } catch (_error) {
      state.lastError = 'The QR was generated but could not be rendered for the web interface. Use terminal QR mode.';
    }
  });
  instance.on('loading_screen', percent => console.log('whatsapp_loading', { percent }));
  instance.on('change_state', status => console.log('whatsapp_browser_state', { status }));
  instance.on('authenticated', () => {
    clearTimeout(initializationWatchdog);
    setStatus('AUTHENTICATED');
    state.qrDataUrl = null;
  });
  instance.on('ready', () => {
    clearTimeout(initializationWatchdog);
    setStatus('READY');
    state.qrDataUrl = null;
    state.lastError = null;
    state.connectedAccount = instance.info?.wid?.user || null;
  });
  instance.on('auth_failure', () => {
    clearTimeout(initializationWatchdog);
    setStatus('AUTH_FAILURE', 'WhatsApp rejected the stored session. Disconnect and scan a new QR code.');
  });
  instance.on('disconnected', () => {
    clearTimeout(initializationWatchdog);
    setStatus('DISCONNECTED');
    state.qrDataUrl = null;
    state.connectedAccount = null;
  });
}

async function startClient() {
  if (initialization) return publicState();
  if (client && ['QR_REQUIRED', 'AUTHENTICATED', 'READY', 'INITIALIZING'].includes(state.status)) return publicState();
  setStatus('INITIALIZING');
  let browserExecutable;
  try {
    browserExecutable = resolveBrowserExecutable();
  } catch (error) {
    state.status = 'FAILED';
    state.lastError = error.message;
    return publicState();
  }
  console.log('whatsapp_browser_selected', { executable: browserExecutable });
  client = new Client({
    authStrategy: new LocalAuth({ clientId: 'netmonitor', dataPath: authPath }),
    authTimeoutMs: 30000,
    qrMaxRetries: 8,
    puppeteer: {
      executablePath: browserExecutable,
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
    },
  });
  bindEvents(client);
  initializationWatchdog = setTimeout(async () => {
    if (state.status !== 'INITIALIZING') return;
    setStatus(
      'FAILED',
      'WhatsApp Web did not produce a QR code within 60 seconds. Verify outbound HTTPS access to web.whatsapp.com and restart the bridge.',
    );
    await client?.destroy().catch(() => undefined);
    client = null;
  }, 60000);
  initialization = client.initialize()
    .catch(error => {
      clearTimeout(initializationWatchdog);
      setStatus('FAILED', `Client initialization failed: ${error?.message || error?.name || 'Unknown error'}`);
      console.error('whatsapp_client_initialization_failed', { message: state.lastError });
    })
    .finally(() => { initialization = null; });
  return publicState();
}

async function stopClient(logout) {
  clearTimeout(initializationWatchdog);
  const active = client;
  client = null;
  initialization = null;
  if (active) {
    try {
      if (logout) await active.logout();
    } finally {
      await active.destroy().catch(() => undefined);
    }
  }
  Object.assign(state, { status: 'STOPPED', qrDataUrl: null, qrUpdatedAt: null, connectedAccount: null, lastError: null });
  return publicState();
}

const app = express();
app.disable('x-powered-by');
app.use(express.json({ limit: '64kb' }));
app.get('/health', (_req, res) => res.json({ status: 'ok' }));
app.use(authorize);

app.get('/session', (_req, res) => res.json(publicState()));
app.post('/session/start', async (_req, res, next) => {
  try { res.json(await startClient()); } catch (error) { next(error); }
});
app.delete('/session', async (_req, res, next) => {
  try { res.json(await stopClient(true)); } catch (error) { next(error); }
});
app.post('/messages', async (req, res, next) => {
  try {
    if (state.status !== 'READY' || !client) return res.status(409).json({ detail: 'WhatsApp session is not ready' });
    const recipient = String(req.body?.recipient || '').replace(/\D/g, '');
    const message = String(req.body?.message || '');
    if (!/^\d{8,15}$/.test(recipient)) return res.status(422).json({ detail: 'Recipient must contain 8 to 15 digits' });
    if (!message || message.length > 10000) return res.status(422).json({ detail: 'Message must contain 1 to 10000 characters' });
    const numberId = await client.getNumberId(recipient);
    if (!numberId) return res.status(422).json({ detail: 'Recipient is not registered on WhatsApp' });
    await client.sendMessage(numberId._serialized, message);
    return res.status(202).json({ status: 'accepted' });
  } catch (error) { return next(error); }
});
app.use((error, _req, res, _next) => {
  console.error('whatsapp_bridge_request_failed', { error_type: error?.name || 'Error' });
  res.status(500).json({ detail: 'WhatsApp bridge operation failed' });
});

const server = app.listen(port, host, () => console.log('whatsapp_bridge_started', { host, port }));
setImmediate(() => startClient().catch(() => undefined));
for (const signal of ['SIGTERM', 'SIGINT']) {
  process.on(signal, async () => {
    server.close();
    await stopClient(false).catch(() => undefined);
    process.exit(0);
  });
}
