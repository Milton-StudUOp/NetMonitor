import React, { useEffect, useRef, useState } from 'react';
import { Ban, CheckSquare, Download, Radar, Search } from 'lucide-react';
import api from '../api/client';
import { getApiErrorMessage } from '../utils/errors';
import Pagination from '../components/Pagination';

const terminalStates = new Set(['COMPLETED', 'CANCELLED', 'FAILED']);
const stageLabels = { HOST_DISCOVERY: 'Discovering active hosts', PORT_SCAN: 'Scanning ports on active hosts', FINALIZING: 'Finalizing results', COMPLETED: 'Completed', CANCELLED: 'Cancelled', FAILED: 'Failed' };
const formatElapsed = (seconds = 0) => `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
const PAGE_SIZE = 25;

export default function Discovery({ user }) {
  const canAddDevices = user?.role !== 'VIEWER';
  const [target, setTarget] = useState('');
  const [portMode, setPortMode] = useState('NONE');
  const [ports, setPorts] = useState('');
  const [profile, setProfile] = useState('SAFE');
  const [methods, setMethods] = useState(['ICMP']);
  const [snmpCommunity, setSnmpCommunity] = useState('');
  const [snmpVersion, setSnmpVersion] = useState('2c');
  const [snmpV3, setSnmpV3] = useState({ username: '', auth_key: '', priv_key: '' });
  const [results, setResults] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [page, setPage] = useState(1);
  const [job, setJob] = useState(null);
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [message, setMessage] = useState(null);
  const timer = useRef(null);
  const visibleResults = results.map((item, index) => ({ item, index })).slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  useEffect(() => () => clearTimeout(timer.current), []);
  const toggleMethod = (method) => setMethods(old => old.includes(method) ? old.filter(x => x !== method) : [...old, method]);
  const prepareResults = items => items.map(item => ({ ...item, name: item.hostname || `Device-${item.ip_address.replaceAll('.', '-')}`, location: 'Network discovery', group_name: '' }));

  const poll = async id => {
    try {
      const response = await api.get(`/discovery/jobs/${id}`);
      setJob(response.data);
      if (!terminalStates.has(response.data.status)) {
        timer.current = setTimeout(() => poll(id), 600);
      } else {
        setLoading(false);
        if (response.data.status === 'COMPLETED') {
          setResults(prepareResults(response.data.results));
          setMessage({ type: 'success', text: `${response.data.hosts_found} active device(s) found safely.` });
        } else if (response.data.status === 'FAILED') setMessage({ type: 'error', text: response.data.error || 'Discovery failed.' });
        else setMessage({ type: 'success', text: 'Discovery was cancelled safely.' });
      }
    } catch (error) { setLoading(false); setMessage({ type: 'error', text: getApiErrorMessage(error) }); }
  };

  const scan = async event => {
    event.preventDefault();
    if (profile === 'AGGRESSIVE' && !window.confirm('Aggressive discovery creates substantially more network traffic and requires server administrator approval. Continue?')) return;
    const customPorts = ports.split(',').map(value => Number(value.trim())).filter(Number.isInteger);
    setLoading(true); setMessage(null); setSelected(new Set()); setResults([]); setJob(null);
    try {
      const response = await api.post('/discovery/jobs', { target, methods, port_scan_mode: portMode, scan_profile: profile, ports: portMode === 'CUSTOM' ? customPorts : [], snmp_version: snmpVersion, snmp_community: snmpCommunity || null, snmp_username: snmpV3.username || null, snmp_auth_key: snmpV3.auth_key || null, snmp_priv_key: snmpV3.priv_key || null });
      setJob(response.data); poll(response.data.id);
    } catch (error) { setLoading(false); setMessage({ type: 'error', text: getApiErrorMessage(error) }); }
  };

  const cancel = async () => {
    if (!job?.id) return;
    clearTimeout(timer.current);
    try { const response = await api.post(`/discovery/jobs/${job.id}/cancel`); setJob(response.data); setLoading(false); setMessage({ type: 'success', text: 'Discovery was cancelled safely.' }); }
    catch (error) { setMessage({ type: 'error', text: getApiErrorMessage(error) }); }
  };
  const update = (index, field, value) => setResults(old => old.map((item, i) => i === index ? { ...item, [field]: value } : item));
  const importSelected = async () => {
    const devices = results.filter((_, index) => selected.has(index));
    if (!devices.length) return;
    setImporting(true); setMessage(null);
    try {
      const response = await api.post('/discovery/import', { devices });
      const importedIPs = new Set(response.data.imported.map(item => item.ip_address));
      const skippedDetails = response.data.skipped.map(item => `${item.ip_address}: ${item.reason}`).join(' · ');
      setResults(old => old.filter(item => !importedIPs.has(item.ip_address)));
      setMessage({ type: response.data.imported.length ? 'success' : 'error', text: `${response.data.imported.length} device(s) added. ${response.data.skipped.length} skipped.${skippedDetails ? ` ${skippedDetails}` : ''}` });
      setSelected(new Set());
    }
    catch (error) { setMessage({ type: 'error', text: getApiErrorMessage(error) }); }
    finally { setImporting(false); }
  };

  return <div className="data-page">
    <div className="page-title"><div><h2>Network Discovery</h2><p>Discover hosts first, enrich their identity, then optionally scan TCP ports.</p></div></div>
    <form className={`glass-card platform-form discovery-form ${portMode === 'CUSTOM' ? 'has-custom-ports' : ''}`} onSubmit={scan}>
      <div className="form-group discovery-target"><label className="form-label">IP, CIDR, or range *</label><input className="form-input" value={target} onChange={e => setTarget(e.target.value)} required disabled={loading} /></div>
      <div className="form-group discovery-port-mode"><label className="form-label">Port Scan Mode</label><select className="form-select" value={portMode} onChange={e => setPortMode(e.target.value)} disabled={loading}><option value="NONE">No Port Scan</option><option value="TOP_100">Top 100 Ports</option><option value="CUSTOM">Custom Ports</option></select></div>
      {portMode === 'CUSTOM' && <div className="form-group discovery-custom-ports"><label className="form-label">Ports (optional)</label><input className="form-input" placeholder="22,80,443,3389" value={ports} onChange={e => setPorts(e.target.value)} disabled={loading} /></div>}
      <div className="form-group discovery-profile"><label className="form-label">Scan Profile</label><select className="form-select" value={profile} onChange={e => setProfile(e.target.value)} disabled={loading}><option value="SAFE">Safe (recommended)</option><option value="NORMAL">Normal</option><option value="AGGRESSIVE">Aggressive (admin only)</option></select></div>
      <div className="method-options discovery-methods"><span className="method-title">Host discovery</span><label><input type="checkbox" checked={methods.includes('ICMP')} onChange={() => toggleMethod('ICMP')} disabled={loading} /> ICMP</label><label><input type="checkbox" checked={methods.includes('SNMP')} onChange={() => toggleMethod('SNMP')} disabled={loading} /> SNMP</label><span className="method-hint">ARP is checked automatically when available.</span></div>
      {methods.includes('SNMP') && <div className="discovery-snmp"><div className="form-group"><label className="form-label">SNMP Version</label><select className="form-select" value={snmpVersion} onChange={e => setSnmpVersion(e.target.value)}><option value="2c">SNMPv2c</option><option value="3">SNMPv3</option></select></div>{snmpVersion === '2c' ? <div className="form-group"><label className="form-label">Community (not stored)</label><input className="form-input" type="password" value={snmpCommunity} onChange={e => setSnmpCommunity(e.target.value)} /></div> : <><div className="form-group"><label className="form-label">SNMPv3 User</label><input className="form-input" value={snmpV3.username} onChange={e => setSnmpV3({ ...snmpV3, username: e.target.value })} /></div><div className="form-group"><label className="form-label">Auth key</label><input className="form-input" type="password" value={snmpV3.auth_key} onChange={e => setSnmpV3({ ...snmpV3, auth_key: e.target.value })} /></div><div className="form-group"><label className="form-label">Privacy key</label><input className="form-input" type="password" value={snmpV3.priv_key} onChange={e => setSnmpV3({ ...snmpV3, priv_key: e.target.value })} /></div></>}</div>}
      <div className="discovery-actions">{!loading ? <button className="btn btn-primary"><Radar size={17} /> Start Discovery</button> : <button className="btn btn-danger" type="button" onClick={cancel}><Ban size={17} /> Cancel Discovery</button>}</div>
    </form>
    {profile === 'AGGRESSIVE' && <div className="notice warning">Aggressive mode is intended for controlled environments and must be enabled by a server administrator.</div>}
    {job && <div className="glass-card discovery-progress" aria-live="polite"><div className="progress-heading"><strong>{stageLabels[job.stage] || job.stage}</strong><span>{job.progress_percent}%</span></div><div className="progress-track" role="progressbar" aria-label="Discovery progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow={job.progress_percent}><div className={job.status === 'RUNNING' && job.progress_percent === 0 ? 'is-indeterminate' : ''} style={job.progress_percent > 0 ? { width: `${job.progress_percent}%` } : undefined} /></div><div className="progress-stats"><span>Hosts checked <strong>{job.hosts_processed}/{job.total_hosts}</strong></span><span>Hosts found <strong>{job.hosts_found}</strong></span><span>Ports scanned <strong>{job.ports_scanned}/{job.total_port_checks}</strong></span><span>Elapsed <strong>{formatElapsed(job.elapsed_seconds)}</strong></span></div></div>}
    {message && <div className={`notice ${message.type}`}>{message.text}</div>}
    <div className="glass-card data-grid-card">
      {!results.length ? <div className="empty-platform"><Search size={40} /><strong>{loading ? 'Discovery in progress' : 'No discovery results'}</strong><span>Only active hosts will be included in the results.</span></div> : <><div className="table-toolbar"><span>{canAddDevices ? `${selected.size} of ${results.length} selected` : `${results.length} discovered device(s)`}</span>{canAddDevices&&<button type="button" className="btn btn-primary" disabled={!selected.size || loading || importing} onClick={importSelected}><Download size={16} /> {importing ? 'Adding…' : 'Add Selected Devices'}</button>}</div><table className="custom-table"><thead><tr>{canAddDevices&&<th><input type="checkbox" aria-label="Select all discovered devices" checked={selected.size === results.length} onChange={() => setSelected(selected.size === results.length ? new Set() : new Set(results.map((_, index) => index)))} /></th>}<th>Host / IP</th><th>Editable Name</th><th>Type</th><th>SNMP</th><th>Location / Group</th><th>Response</th><th>Open TCP Ports</th></tr></thead><tbody>{results.map((item, index) => <tr key={item.ip_address}>{canAddDevices&&<td><input type="checkbox" checked={selected.has(index)} onChange={() => setSelected(old => { const next = new Set(old); next.has(index) ? next.delete(index) : next.add(index); return next; })} /></td>}<td><strong>{item.hostname || item.ip_address}</strong><div>{item.ip_address} <span className="badge badge-online">{item.status}</span></div></td><td><input className="form-input compact" disabled={!canAddDevices} value={item.name} onChange={e => update(index, 'name', e.target.value)} /></td><td><select className="form-select compact" disabled={!canAddDevices} value={item.device_type} onChange={e => update(index, 'device_type', e.target.value)}>{['SWITCH', 'ROUTER', 'FIREWALL', 'SERVER', 'ACCESS_POINT', 'RADIO', 'OTHER'].map(value => <option key={value}>{value}</option>)}</select></td><td>{item.snmp_available ? <span className="badge badge-online">Available</span> : 'Not detected'}</td><td><input className="form-input compact" disabled={!canAddDevices} value={item.location} onChange={e => update(index, 'location', e.target.value)} /><input className="form-input compact" disabled={!canAddDevices} placeholder="Group" value={item.group_name} onChange={e => update(index, 'group_name', e.target.value)} /></td><td>{item.latency_ms != null ? `${item.latency_ms} ms` : '—'}</td><td>{item.open_ports.join(', ') || 'None detected'}</td></tr>)}</tbody></table></>}
    </div>
  </div>;
}
