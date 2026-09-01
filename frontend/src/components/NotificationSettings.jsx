import React, { useEffect, useMemo, useState } from 'react';
import { Bell, CheckCircle2, Edit3, Plus, Save, Send, Trash2, X } from 'lucide-react';
import api from '../api/client';
import { getApiErrorMessage } from '../utils/errors';

const defaults = {
  EMAIL: { provider: 'EMAIL', name: 'SMTP Email', enabled: false, config: { smtp_server: '', smtp_port: 587, username: '', from_address: '', recipients: [], tls: true, ssl: false }, secrets: { password: '' }, secrets_configured: [], last_status: 'UNTESTED' },
  TELEGRAM: { provider: 'TELEGRAM', name: 'Telegram', enabled: false, config: { chat_ids: [] }, secrets: { bot_token: '' }, secrets_configured: [], last_status: 'UNTESTED' },
  WHATSAPP: { provider: 'WHATSAPP', name: 'WhatsApp API', enabled: false, config: { api_url: '', sender_id: '', recipients: [] }, secrets: { api_token: '' }, secrets_configured: [], last_status: 'UNTESTED' },
};

const blankRule = { name: '', event_type: 'DEVICE_DOWN', severity: 'CRITICAL', source: '', channels: ['EMAIL'], recipients: '', reminder_minutes: 0, notify_recovery: true, enabled: true };
const cloneDefaults = () => Object.fromEntries(Object.entries(defaults).map(([key, value]) => [key, { ...value, config: { ...value.config }, secrets: { ...value.secrets }, secrets_configured: [] }]));

function Field({ label, required, hint, children }) {
  return <div className="form-group"><label className="form-label">{label}{required ? ' *' : ''}</label>{children}{hint && <small className="field-hint">{hint}</small>}</div>;
}

function Status({ integration }) {
  const value = integration.last_status || 'UNTESTED';
  const badge = value === 'SUCCESS' ? 'online' : value === 'FAILED' ? 'offline' : 'unknown';
  return <div className="notification-status"><span className={`badge badge-${badge}`}>{value}</span>{integration.last_error && <small>{integration.last_error}</small>}</div>;
}

function SecretField({ label, configured, value, onChange, hint }) {
  return <Field label={label} required hint={configured ? `${label} is securely stored. Enter a new value only to replace it.` : hint}>
    <div className="secret-input-wrap"><input className="form-input" type="password" autoComplete="new-password" placeholder={configured ? '••••••••  (saved)' : ''} value={value} onChange={onChange}/>{configured && <span className="secret-configured"><CheckCircle2 size={13}/> Configured</span>}</div>
  </Field>;
}

export default function NotificationSettings({ report }) {
  const [providers, setProviders] = useState(cloneDefaults);
  const [rules, setRules] = useState([]);
  const [rule, setRule] = useState(blankRule);
  const [editingRuleId, setEditingRuleId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const [providerResponse, ruleResponse] = await Promise.all([
        api.get('/platform/notifications'), api.get('/platform/notification-rules'),
      ]);
      const merged = cloneDefaults();
      providerResponse.data.forEach(item => {
        if (!merged[item.provider]) return;
        merged[item.provider] = { ...merged[item.provider], ...item, config: { ...merged[item.provider].config, ...(item.config || {}) }, secrets: { ...merged[item.provider].secrets } };
      });
      setProviders(merged);
      setRules(ruleResponse.data);
    } catch (error) {
      report('error', `Could not load notification settings: ${getApiErrorMessage(error)}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const updateProvider = (provider, section, field, value) => setProviders(current => ({
    ...current,
    [provider]: { ...current[provider], [section]: { ...current[provider][section], [field]: value } },
  }));

  const toggleProvider = (provider, enabled) => setProviders(current => ({
    ...current, [provider]: { ...current[provider], enabled },
  }));

  const saveProvider = async (provider, testAfter = false) => {
    const integration = providers[provider];
    setBusy(`${testAfter ? 'test' : 'save'}-${provider}`);
    try {
      await api.put(`/platform/notifications/${provider}`, integration);
      if (testAfter) {
        const response = await api.post(`/platform/notifications/${provider}/test`);
        report(response.data.status === 'SUCCESS' ? 'success' : 'error', response.data.message);
      } else {
        report('success', `${integration.name} configuration saved.`);
      }
      await load();
    } catch (error) {
      report('error', getApiErrorMessage(error));
    } finally {
      setBusy('');
    }
  };

  const saveRule = async event => {
    event.preventDefault();
    setBusy('create-rule');
    try {
      const payload = {
        ...rule,
        recipients: rule.recipients.split(',').map(value => value.trim()).filter(Boolean),
        reminder_minutes: Number(rule.reminder_minutes),
      };
      if (editingRuleId) await api.put(`/platform/notification-rules/${editingRuleId}`, payload);
      else await api.post('/platform/notification-rules', payload);
      setRule({ ...blankRule });
      setEditingRuleId(null);
      report('success', `Notification rule ${editingRuleId ? 'updated' : 'created'}.`);
      await load();
    } catch (error) {
      report('error', getApiErrorMessage(error));
    } finally {
      setBusy('');
    }
  };

  const editRule = item => {
    setEditingRuleId(item.id);
    setRule({
      name: item.name, event_type: item.event_type, severity: item.severity,
      source: item.source || '', channels: [...(item.channels || [])],
      recipients: (item.recipients || []).join(', '), reminder_minutes: item.reminder_minutes || 0,
      notify_recovery: item.notify_recovery, enabled: item.enabled,
    });
    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
  };

  const cancelEdit = () => { setEditingRuleId(null); setRule({ ...blankRule }); };

  const deleteRule = async item => {
    if (!window.confirm(`Delete notification rule "${item.name}"?`)) return;
    setBusy(`delete-rule-${item.id}`);
    try {
      await api.delete(`/platform/notification-rules/${item.id}`);
      report('success', 'Notification rule deleted.');
      await load();
    } catch (error) {
      report('error', getApiErrorMessage(error));
    } finally {
      setBusy('');
    }
  };

  const toggleRule = async item => {
    setBusy(`toggle-rule-${item.id}`);
    try {
      const { id, created_at, updated_at, ...payload } = item;
      await api.put(`/platform/notification-rules/${item.id}`, { ...payload, enabled: !item.enabled });
      report('success', `Notification rule ${item.enabled ? 'disabled' : 'enabled'}.`);
      await load();
    } catch (error) {
      report('error', getApiErrorMessage(error));
    } finally {
      setBusy('');
    }
  };

  const enabledChannels = useMemo(() => Object.values(providers).filter(item => item.enabled).map(item => item.provider), [providers]);
  if (loading) return <div className="glass-card settings-panel">Loading notification settings…</div>;

  return <>
    <div className="notification-intro glass-card"><Bell size={20}/><div><strong>Notification channels</strong><p>Save and test each channel before enabling rules. Credentials are encrypted and never returned by the API.</p></div></div>
    <div className="provider-grid">
      {Object.entries(providers).map(([key, provider]) => <section className="glass-card settings-panel" key={key}>
        <div className="panel-heading"><div><h3>{provider.name}</h3><Status integration={provider}/></div><label className="switch-label"><input type="checkbox" checked={provider.enabled} onChange={event => toggleProvider(key, event.target.checked)}/> Enabled</label></div>
        {key === 'EMAIL' && <>
          <Field label="SMTP server" required><input className="form-input" value={provider.config.smtp_server} onChange={event => updateProvider(key, 'config', 'smtp_server', event.target.value.trim())}/></Field>
          <div className="form-row"><Field label="Port" required><input className="form-input" type="number" min="1" max="65535" value={provider.config.smtp_port} onChange={event => updateProvider(key, 'config', 'smtp_port', Number(event.target.value))}/></Field><Field label="Username"><input className="form-input" autoComplete="username" value={provider.config.username} onChange={event => updateProvider(key, 'config', 'username', event.target.value)}/></Field></div>
          <SecretField label="Password" configured={provider.secrets_configured?.includes('password')} value={provider.secrets.password} onChange={event => updateProvider(key, 'secrets', 'password', event.target.value)}/>
          <Field label="Sender address" required><input className="form-input" type="email" value={provider.config.from_address} onChange={event => updateProvider(key, 'config', 'from_address', event.target.value.trim())}/></Field>
          <Field label="Recipients" required hint="Separate multiple addresses with commas."><input className="form-input" value={(provider.config.recipients || []).join(', ')} onChange={event => updateProvider(key, 'config', 'recipients', event.target.value.split(',').map(value => value.trim()).filter(Boolean))}/></Field>
          <div className="method-options"><label><input type="checkbox" checked={provider.config.tls} onChange={event => updateProvider(key, 'config', 'tls', event.target.checked)}/> STARTTLS</label><label><input type="checkbox" checked={provider.config.ssl} onChange={event => updateProvider(key, 'config', 'ssl', event.target.checked)}/> Implicit TLS</label></div>
        </>}
        {key === 'TELEGRAM' && <><SecretField label="Bot token" configured={provider.secrets_configured?.includes('bot_token')} hint="Create a bot with BotFather." value={provider.secrets.bot_token} onChange={event => updateProvider(key, 'secrets', 'bot_token', event.target.value.trim())}/><Field label="Chat IDs" required hint="Separate multiple Chat IDs with commas. Groups and channels may use negative IDs."><input className="form-input" placeholder="123456789, -1001234567890" value={(provider.config.chat_ids?.length ? provider.config.chat_ids : provider.config.chat_id ? [provider.config.chat_id] : []).join(', ')} onChange={event => updateProvider(key, 'config', 'chat_ids', event.target.value.split(',').map(value => value.trim()).filter(Boolean))}/></Field></>}
        {key === 'WHATSAPP' && <><Field label="Provider API URL" required><input className="form-input" type="url" placeholder="https://provider.example/messages" value={provider.config.api_url} onChange={event => updateProvider(key, 'config', 'api_url', event.target.value.trim())}/></Field><SecretField label="API token" configured={provider.secrets_configured?.includes('api_token')} value={provider.secrets.api_token} onChange={event => updateProvider(key, 'secrets', 'api_token', event.target.value.trim())}/><Field label="Sender ID"><input className="form-input" value={provider.config.sender_id} onChange={event => updateProvider(key, 'config', 'sender_id', event.target.value.trim())}/></Field><Field label="Recipients" required hint="Separate multiple international-format numbers with commas."><input className="form-input" placeholder="258841234567, 258851234567" value={(provider.config.recipients?.length ? provider.config.recipients : provider.config.recipient ? [provider.config.recipient] : []).join(', ')} onChange={event => updateProvider(key, 'config', 'recipients', event.target.value.split(',').map(value => value.trim()).filter(Boolean))}/></Field></>}
        <div className="row-actions notification-actions"><button type="button" className="btn btn-primary" disabled={Boolean(busy)} onClick={() => saveProvider(key)}><Save size={14}/> {busy === `save-${key}` ? 'Saving…' : 'Save'}</button><button type="button" className="btn btn-secondary" disabled={Boolean(busy)} onClick={() => saveProvider(key, true)}><Send size={14}/> {busy === `test-${key}` ? 'Testing…' : 'Save & Test'}</button></div>
      </section>)}
    </div>

    <div className="settings-grid">
      <form className="glass-card settings-panel" onSubmit={saveRule}><div className="panel-heading"><h3>{editingRuleId ? 'Edit notification rule' : 'New notification rule'}</h3>{editingRuleId && <button type="button" className="btn btn-secondary" onClick={cancelEdit}><X size={14}/> Cancel</button>}</div>
        <Field label="Rule name" required><input required className="form-input" value={rule.name} onChange={event => setRule({ ...rule, name: event.target.value })}/></Field>
        <div className="form-row"><Field label="Event" required><select className="form-select" value={rule.event_type} onChange={event => setRule({ ...rule, event_type: event.target.value })}><option value="DEVICE_DOWN">Device down</option><option value="DEVICE_UP">Device recovery</option><option value="LINK_DOWN">Link down</option><option value="LINK_UP">Link recovery</option><option value="REDUNDANCY_DEGRADED">Redundancy degraded</option><option value="REDUNDANCY_CRITICAL">Redundancy critical</option><option value="RECOVERY">Any recovery</option></select></Field><Field label="Severity" required><select className="form-select" value={rule.severity} onChange={event => setRule({ ...rule, severity: event.target.value })}><option value="INFORMATION">Information</option><option value="WARNING">Warning</option><option value="CRITICAL">Critical</option></select></Field></div>
        <Field label="Source filter" hint="Optional case-insensitive text matched against the alert title and message."><input className="form-input" value={rule.source} onChange={event => setRule({ ...rule, source: event.target.value })}/></Field>
        <Field label="Channels" required><div className="method-options">{Object.keys(defaults).map(channel => <label key={channel}><input type="checkbox" checked={rule.channels.includes(channel)} onChange={() => setRule({ ...rule, channels: rule.channels.includes(channel) ? rule.channels.filter(value => value !== channel) : [...rule.channels, channel] })}/>{channel}{!enabledChannels.includes(channel) && ' (disabled)'}</label>)}</div></Field>
        <Field label="Additional recipients" hint="Optional comma-separated email addresses, Telegram chat IDs, or WhatsApp numbers for this rule."><input className="form-input" value={rule.recipients} onChange={event => setRule({ ...rule, recipients: event.target.value })}/></Field>
        <div className="form-row"><Field label="Reminder interval (minutes)"><input className="form-input" type="number" min="0" value={rule.reminder_minutes} onChange={event => setRule({ ...rule, reminder_minutes: event.target.value })}/></Field><Field label="Recovery"><label className="check-line"><input type="checkbox" checked={rule.notify_recovery} onChange={event => setRule({ ...rule, notify_recovery: event.target.checked })}/> Notify when recovered</label></Field></div>
        <button className="btn btn-primary" disabled={Boolean(busy) || !rule.channels.length}>{editingRuleId ? <Save size={15}/> : <Plus size={15}/>} {busy === 'create-rule' ? 'Saving…' : editingRuleId ? 'Save Changes' : 'Create Rule'}</button>
      </form>
      <section className="glass-card settings-panel"><h3>Notification rules</h3>{!rules.length ? <p className="muted">No notification rules configured.</p> : rules.map(item => <div className={`integration-row ${editingRuleId === item.id ? 'is-editing' : ''}`} key={item.id}><div><strong>{item.name}</strong><span>{item.event_type.replaceAll('_', ' ')} · {item.severity} · {item.channels.join(' + ')}</span>{item.source && <span>Source filter: {item.source}</span>}{item.reminder_minutes > 0 && <span>Reminder every {item.reminder_minutes} minutes</span>}</div><span className={`badge badge-${item.enabled ? 'online' : 'unknown'}`}>{item.enabled ? 'ACTIVE' : 'INACTIVE'}</span><div className="row-actions"><button type="button" className="btn btn-secondary" disabled={Boolean(busy)} onClick={() => editRule(item)}><Edit3 size={14}/> Edit</button><button type="button" className="btn btn-secondary" disabled={Boolean(busy)} onClick={() => toggleRule(item)}>{item.enabled ? 'Disable' : 'Enable'}</button><button type="button" className="btn btn-danger" disabled={Boolean(busy)} onClick={() => deleteRule(item)}><Trash2 size={14}/></button></div></div>)}</section>
    </div>
  </>;
}
