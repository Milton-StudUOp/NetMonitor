import React, { useState } from 'react';
import { Radar, Search, Download, CheckSquare } from 'lucide-react';
import api from '../api/client';
import { getApiErrorMessage } from '../utils/errors';

export default function Discovery() {
  const [target, setTarget] = useState('192.168.1.0/24');
  const [ports, setPorts] = useState('22,23,80,443,161,8080,8443');
  const [methods, setMethods] = useState(['ICMP', 'TCP']);
  const [snmpCommunity, setSnmpCommunity] = useState('');
  const [snmpVersion, setSnmpVersion] = useState('2c');
  const [snmpV3, setSnmpV3] = useState({ username:'', auth_key:'', priv_key:'' });
  const [results, setResults] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState(null);

  const toggleMethod = (method) => setMethods((old) => old.includes(method) ? old.filter(x => x !== method) : [...old, method]);
  const scan = async (event) => {
    event.preventDefault(); setLoading(true); setMessage(null); setSelected(new Set());
    try {
      const response = await api.post('/discovery/scan', { target, methods, ports: ports.split(',').map(Number).filter(Boolean), snmp_version:snmpVersion, snmp_community: snmpCommunity || null, snmp_username:snmpV3.username||null, snmp_auth_key:snmpV3.auth_key||null, snmp_priv_key:snmpV3.priv_key||null });
      setResults(response.data.map((item) => ({ ...item, name: item.hostname || `Device-${item.ip_address.replaceAll('.', '-')}`, location: 'Descoberta de rede', group_name: '' })));
      setMessage({ type: 'success', text: `${response.data.length} equipamento(s) ativo(s) encontrado(s).` });
    } catch (error) { setMessage({ type: 'error', text: getApiErrorMessage(error) }); }
    finally { setLoading(false); }
  };
  const update = (index, field, value) => setResults(old => old.map((x, i) => i === index ? { ...x, [field]: value } : x));
  const importSelected = async () => {
    const devices = results.filter((_, index) => selected.has(index));
    if (!devices.length) return;
    setLoading(true);
    try {
      const response = await api.post('/discovery/import', { devices });
      setMessage({ type: 'success', text: `${response.data.imported.length} equipamento(s) importado(s); ${response.data.skipped.length} ignorado(s).` });
      setSelected(new Set());
    } catch (error) { setMessage({ type: 'error', text: getApiErrorMessage(error) }); }
    finally { setLoading(false); }
  };

  return <div>
    <div className="page-title"><div><h2>Descoberta de Rede</h2><p>Localize ativos por ICMP e portas TCP antes de adicioná-los ao monitoramento.</p></div></div>
    <form className="glass-card platform-form" onSubmit={scan}>
      <div className="form-group grow"><label className="form-label">Rede, intervalo ou IP</label><input className="form-input" value={target} onChange={e => setTarget(e.target.value)} required /></div>
      <div className="form-group grow"><label className="form-label">Portas TCP</label><input className="form-input" value={ports} onChange={e => setPorts(e.target.value)} /></div>
      <div className="method-options">{['ICMP', 'TCP', 'SNMP'].map(method => <label key={method}><input type="checkbox" checked={methods.includes(method)} onChange={() => toggleMethod(method)} /> {method}</label>)}</div>
      {methods.includes('SNMP') && <><div className="form-group"><label className="form-label">Versão SNMP</label><select className="form-select" value={snmpVersion} onChange={e=>setSnmpVersion(e.target.value)}><option value="2c">SNMPv2c</option><option value="3">SNMPv3</option></select></div>{snmpVersion==='2c'?<div className="form-group"><label className="form-label">Community (não será guardada)</label><input className="form-input" type="password" value={snmpCommunity} onChange={e => setSnmpCommunity(e.target.value)} /></div>:<><div className="form-group"><label className="form-label">Utilizador SNMPv3</label><input className="form-input" value={snmpV3.username} onChange={e=>setSnmpV3({...snmpV3,username:e.target.value})}/></div><div className="form-group"><label className="form-label">Auth key</label><input className="form-input" type="password" value={snmpV3.auth_key} onChange={e=>setSnmpV3({...snmpV3,auth_key:e.target.value})}/></div><div className="form-group"><label className="form-label">Privacy key</label><input className="form-input" type="password" value={snmpV3.priv_key} onChange={e=>setSnmpV3({...snmpV3,priv_key:e.target.value})}/></div></>}</>}
      <button className="btn btn-primary" disabled={loading || !methods.length}><Radar size={17} /> {loading ? 'A pesquisar…' : 'Iniciar descoberta'}</button>
    </form>
    {message && <div className={`notice ${message.type}`}>{message.text}</div>}
    <div className="glass-card" style={{ overflow: 'auto' }}>
      {!results.length ? <div className="empty-platform"><Search size={40} /><strong>Nenhuma descoberta executada</strong><span>Informe um alvo e inicie uma pesquisa controlada.</span></div> : <>
        <div className="table-toolbar"><span>{selected.size} selecionado(s)</span><button className="btn btn-primary" disabled={!selected.size || loading} onClick={importSelected}><Download size={16} /> Adicionar selecionados</button></div>
        <table className="custom-table"><thead><tr><th></th><th>IP / Estado</th><th>Nome editável</th><th>Tipo</th><th>Localização / Grupo</th><th>Latência</th><th>Portas</th></tr></thead><tbody>
          {results.map((item, index) => <tr key={item.ip_address}>
            <td><input type="checkbox" checked={selected.has(index)} onChange={() => setSelected(old => { const next = new Set(old); next.has(index) ? next.delete(index) : next.add(index); return next; })} /></td>
            <td><strong>{item.ip_address}</strong><div><span className="badge badge-online">{item.status}</span></div></td>
            <td><input className="form-input compact" value={item.name} onChange={e => update(index, 'name', e.target.value)} /></td>
            <td><select className="form-select compact" value={item.device_type} onChange={e => update(index, 'device_type', e.target.value)}>{['SWITCH','ROUTER','FIREWALL','SERVER','ACCESS_POINT','RADIO','OTHER'].map(x => <option key={x}>{x}</option>)}</select></td>
            <td><input className="form-input compact" value={item.location} onChange={e => update(index, 'location', e.target.value)} /><input className="form-input compact" placeholder="Grupo" value={item.group_name} onChange={e => update(index, 'group_name', e.target.value)} /></td>
            <td>{item.latency_ms ? `${item.latency_ms} ms` : '—'}</td><td>{item.open_ports.join(', ') || '—'}</td>
          </tr>)}</tbody></table></>}
    </div>
  </div>;
}
