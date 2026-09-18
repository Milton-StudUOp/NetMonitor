import React, { useEffect, useState } from 'react';
import { Activity, ArrowLeft, Clock3, Gauge, Server, ShieldCheck, TimerOff, Save, TestTube } from 'lucide-react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import api from '../api/client';
import { getApiErrorMessage } from '../utils/errors';

const periods = [['24h', '24 hours'], ['7d', '7 days'], ['30d', '30 days'], ['90d', '90 days']];
const formatDate = value => value ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'medium' }).format(new Date(value)) : 'Ongoing';
const formatAxis = value => new Intl.DateTimeFormat(undefined, { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value));
const formatDuration = seconds => {
  const days = Math.floor(seconds / 86400); const hours = Math.floor((seconds % 86400) / 3600); const minutes = Math.floor((seconds % 3600) / 60);
  return [days && `${days}d`, hours && `${hours}h`, `${minutes}m`].filter(Boolean).join(' ');
};
const tooltipStyle = { background: '#0f172a', border: '1px solid rgba(255,255,255,.12)', borderRadius: 10, color: '#fff' };

export default function DeviceAnalytics() {
  const { deviceId } = useParams(); const navigate = useNavigate(); const location = useLocation();
  const returnTo = new URLSearchParams(location.search).get('from') === 'devices' ? '/devices' : '/topology';
  const [period, setPeriod] = useState('24h'); const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true); const [error, setError] = useState('');

  useEffect(() => {
    let active = true; setLoading(true); setError('');
    api.get(`/history/devices/${deviceId}/analytics?period=${period}`).then(response => { if (active) setData(response.data); }).catch(err => { if (active) setError(getApiErrorMessage(err)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [deviceId, period]);

  if (loading && !data) return <div className="analytics-state"><Activity className="spin" size={30} /><span>Loading device metrics…</span></div>;
  if (error && !data) return <div className="notice error">{error}</div>;
  const summary = data?.summary || {}; const device = data?.device || {}; const series = data?.series || [];

  return <div>
    <div className="analytics-header"><div className="analytics-heading"><button className="icon-button" onClick={() => navigate(returnTo)} title={returnTo === '/devices' ? 'Back to devices' : 'Back to topology'} aria-label={returnTo === '/devices' ? 'Back to devices' : 'Back to topology'}><ArrowLeft size={18} /></button><div><div className="analytics-title-line"><h2>{device.name}</h2><span className={`badge badge-${device.status?.toLowerCase() || 'unknown'}`}>{device.status}</span></div><p>{device.ip_address || 'No IP address'} · {device.device_type} · {device.location || 'No location'}</p></div></div><div className="period-selector">{periods.map(([value, label]) => <button key={value} className={period === value ? 'active' : ''} onClick={() => setPeriod(value)}>{label}</button>)}</div></div>
    {error && <div className="notice error">Could not refresh metrics: {error}</div>}
    <WindowsMonitoring device={device} />
    <div className="metric-summary-grid">
      <div className="metric-summary-card"><ShieldCheck /><span>Availability</span><strong>{summary.availability_pct == null ? 'No data' : `${summary.availability_pct}%`}</strong><small>{summary.successful_probes || 0} successful of {summary.total_probes || 0} probes</small></div>
      <div className="metric-summary-card"><Gauge /><span>Average latency</span><strong>{summary.average_latency_ms == null ? '—' : `${summary.average_latency_ms} ms`}</strong><small>Maximum {summary.maximum_latency_ms == null ? '—' : `${summary.maximum_latency_ms} ms`}</small></div>
      <div className="metric-summary-card"><Activity /><span>Packet loss</span><strong>{summary.average_packet_loss_pct == null ? '—' : `${summary.average_packet_loss_pct}%`}</strong><small>Average during selected period</small></div>
      <div className="metric-summary-card critical"><TimerOff /><span>Downtime</span><strong>{formatDuration(summary.downtime_seconds || 0)}</strong><small>{summary.outage_count || 0} outage event(s)</small></div>
    </div>
    <div className="analytics-grid">
      <section className="glass-card analytics-panel analytics-chart-wide"><div className="panel-title"><div><h3>Latency and packet loss</h3><p>Performance trend from successful monitoring probes</p></div><span>{series.length} data points</span></div>{series.length ? <div className="chart-container"><ResponsiveContainer width="100%" height="100%"><ComposedChart data={series} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}><defs><linearGradient id="deviceLatency" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#3b82f6" stopOpacity={.42}/><stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/></linearGradient></defs><CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,.06)"/><XAxis dataKey="timestamp" tickFormatter={formatAxis} minTickGap={45} stroke="#64748b" fontSize={11}/><YAxis yAxisId="latency" unit=" ms" stroke="#64748b" fontSize={11}/><YAxis yAxisId="loss" orientation="right" domain={[0,100]} unit="%" stroke="#64748b" fontSize={11}/><Tooltip contentStyle={tooltipStyle} labelFormatter={formatDate}/><Area yAxisId="latency" type="monotone" dataKey="latency_ms" name="Latency" stroke="#3b82f6" strokeWidth={2} fill="url(#deviceLatency)" dot={series.length < 30} connectNulls/><Line yAxisId="loss" type="monotone" dataKey="packet_loss_pct" name="Packet loss" stroke="#f59e0b" strokeWidth={2} dot={series.length < 30} connectNulls/></ComposedChart></ResponsiveContainer></div> : <EmptyMetrics />}</section>
      <section className="glass-card analytics-panel"><div className="panel-title"><div><h3>Availability timeline</h3><p>Green is available; red is unavailable</p></div></div>{series.length ? <div className="availability-strip" title="Availability timeline">{series.map((point, index) => <span key={`${point.timestamp}-${index}`} className={`status-${point.status.toLowerCase()}`} title={`${formatDate(point.timestamp)} — ${point.status}`} />)}</div> : <EmptyMetrics />}</section>
      <section className="glass-card analytics-panel"><div className="panel-title"><div><h3>Device information</h3><p>Identity associated with these metrics</p></div></div><dl className="device-facts"><div><dt>Manufacturer</dt><dd>{device.manufacturer || 'Not configured'}</dd></div><div><dt>Model</dt><dd>{device.model || 'Not configured'}</dd></div><div><dt>Monitoring period</dt><dd>{formatDate(data.period.start)} — {formatDate(data.period.end)}</dd></div><div><dt>Aggregation</dt><dd>{Math.round(data.period.bucket_seconds / 60)} minute buckets</dd></div></dl></section>
    </div>
    <section className="glass-card analytics-panel outage-panel"><div className="panel-title"><div><h3>Outage history</h3><p>Exact detected start, recovery time, and duration</p></div><Clock3 size={20}/></div>{data.outages.length ? <div className="outage-table-wrap"><table className="custom-table"><thead><tr><th>Started</th><th>Recovered</th><th>Duration</th><th>State</th></tr></thead><tbody>{data.outages.map(outage => <tr key={outage.started_at}><td>{formatDate(outage.started_at)}</td><td>{formatDate(outage.ended_at)}</td><td>{formatDuration(outage.duration_seconds)}</td><td><span className={`badge ${outage.ongoing ? 'badge-critical' : 'badge-online'}`}>{outage.ongoing ? 'ONGOING' : 'RECOVERED'}</span></td></tr>)}</tbody></table></div> : <div className="no-outages"><ShieldCheck size={24}/><div><strong>No outages detected</strong><span>No DOWN state was recorded in this period.</span></div></div>}</section>
  </div>;
}

function EmptyMetrics() { return <div className="chart-empty"><Server size={28}/><strong>No monitoring data</strong><span>Metrics will appear after the monitoring engine records probes.</span></div>; }

function WindowsMonitoring({ device }) {
  const [form, setForm] = useState({ username:'', password:'', port:5986, use_https:true, verify_certificate:true, authentication:'NTLM', enabled:true });
  const [result, setResult] = useState(null); const [busy, setBusy] = useState(''); const [notice, setNotice] = useState('');
  useEffect(() => {
    if (!device?.id) return;
    api.get(`/devices/${device.id}/windows-monitoring`).then(r => r.data && setForm(f => ({...f,...r.data,password:''}))).catch(() => {});
  }, [device?.id]);
  const save = async e => { e.preventDefault(); setBusy('save'); setNotice(''); try { await api.put(`/devices/${device.id}/windows-monitoring`, form); setForm(f=>({...f,password:''})); setNotice('Windows monitoring connection saved securely.'); } catch(e) { setNotice(getApiErrorMessage(e)); } finally { setBusy(''); } };
  const test = async () => { setBusy('test'); setNotice(''); try { const r=await api.post(`/devices/${device.id}/windows-monitoring/test`); setResult(r.data); if(r.data.status!=='READY') setNotice(r.data.message); } catch(e) { setNotice(getApiErrorMessage(e)); } finally { setBusy(''); } };
  return <section className="glass-card analytics-panel" style={{marginBottom:'18px'}}><div className="panel-title"><div><h3>Windows Monitoring</h3><p>Securely test compatibility before discovering services and metrics.</p></div>{result&&<span className={`badge badge-${result.status==='READY'?'online':'offline'}`}>{result.status}</span>}</div>
    {notice&&<div className={`notice ${result?.status==='READY'?'success':'error'}`}>{notice}</div>}
    <form onSubmit={save}><div className="form-row"><div className="form-group"><label className="form-label">Monitoring account</label><input className="form-input" required value={form.username} onChange={e=>setForm({...form,username:e.target.value})}/></div><div className="form-group"><label className="form-label">{form.password_configured?'New password (leave blank to keep current)':'Password'}</label><input className="form-input" type="password" required={!form.password_configured} value={form.password} onChange={e=>setForm({...form,password:e.target.value})}/></div></div>
      <div className="form-row"><div className="form-group"><label className="form-label">Authentication</label><select className="form-select" value={form.authentication} onChange={e=>setForm({...form,authentication:e.target.value})}><option>NTLM</option><option>KERBEROS</option><option>CREDSSP</option></select></div><div className="form-group"><label className="form-label">Port</label><input className="form-input" type="number" min="1" max="65535" value={form.port} onChange={e=>setForm({...form,port:Number(e.target.value)})}/></div></div>
      <label className="check-line"><input type="checkbox" checked={form.use_https} onChange={e=>setForm({...form,use_https:e.target.checked,port:e.target.checked?5986:5985})}/> Use encrypted HTTPS connection</label><label className="check-line"><input type="checkbox" checked={form.verify_certificate} disabled={!form.use_https} onChange={e=>setForm({...form,verify_certificate:e.target.checked})}/> Verify server certificate</label>
      <div className="row-actions"><button className="btn btn-primary" disabled={!!busy}><Save size={15}/>{busy==='save'?'Saving…':'Save Connection'}</button><button type="button" className="btn btn-secondary" disabled={!!busy||!form.password_configured&&!form.password} onClick={test}><TestTube size={15}/>{busy==='test'?'Testing…':'Test Connection'}</button></div></form>
    {result&&<div className="device-facts" style={{marginTop:'18px'}}><dl><div><dt>Connectivity</dt><dd>{result.connectivity?'✓':'—'}</dd></div><div><dt>WinRM</dt><dd>{result.winrm?'✓':'—'}</dd></div><div><dt>Authentication</dt><dd>{result.authentication?'✓':'—'}</dd></div><div><dt>Windows</dt><dd>{result.operating_system||'Unknown'}</dd></div><div><dt>Provider</dt><dd>{result.provider_mode==='LEGACY_WMI'?'Legacy compatible':result.provider_mode||'Unavailable'}</dd></div><div><dt>Service Discovery</dt><dd>{result.service_discovery?'Supported':'Unavailable'}</dd></div></dl>{result.status==='READY'&&<strong>Ready for Discovery</strong>}<details><summary>Advanced diagnostics</summary><pre>{JSON.stringify({error_code:result.error_code,powershell_version:result.powershell_version,capabilities:result.capabilities,diagnostics:result.diagnostics},null,2)}</pre></details></div>}
  </section>;
}
