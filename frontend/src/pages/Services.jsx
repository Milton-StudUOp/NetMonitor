import React, { useEffect, useMemo, useState } from 'react';
import { Edit3, ListTree, Plus, RefreshCw, Search } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import api from '../api/client';
import Pagination from '../components/Pagination';
import ServiceConfigModal from '../components/ServiceConfigModal';
import { getApiErrorMessage } from '../utils/errors';

const PAGE_SIZE = 25;

export default function Services({ user }) {
  const navigate = useNavigate(); const canManage = user?.role !== 'VIEWER';
  const [items,setItems]=useState([]); const [loading,setLoading]=useState(true); const [error,setError]=useState('');
  const [search,setSearch]=useState(''); const [device,setDevice]=useState(''); const [state,setState]=useState(''); const [monitoring,setMonitoring]=useState(''); const [page,setPage]=useState(1); const [editing,setEditing]=useState(null);
  const load=()=>{setLoading(true);setError('');api.get('/services/catalog').then(r=>setItems(r.data)).catch(e=>setError(getApiErrorMessage(e))).finally(()=>setLoading(false));};
  useEffect(load,[]);
  const devices=useMemo(()=>Array.from(new Map(items.map(item=>[item.device_id,{id:item.device_id,name:item.device_name}])).values()),[items]);
  const filtered=useMemo(()=>items.filter(item=>(!search||`${item.display_name} ${item.name} ${item.device_name} ${item.ip_address||''}`.toLowerCase().includes(search.toLowerCase()))&&(!device||String(item.device_id)===device)&&(!state||item.state===state)&&(!monitoring||String(item.monitored)===monitoring)),[items,search,device,state,monitoring]);
  const visible=filtered.slice((page-1)*PAGE_SIZE,page*PAGE_SIZE);
  useEffect(()=>setPage(current=>Math.min(current,Math.max(1,Math.ceil(filtered.length/PAGE_SIZE)))),[filtered.length]);
  const change=(setter)=>(event)=>{setter(event.target.value);setPage(1);};
  return <div className="data-page">
    <div className="page-title"><div><h2>Services</h2><p>Complete catalog of discovered services across registered devices.</p></div><div className="row-actions"><button className="btn btn-secondary" onClick={load} disabled={loading}><RefreshCw size={15} className={loading?'spin':''}/>Refresh</button>{canManage&&<button className="btn btn-primary" onClick={()=>navigate('/service-discovery')}><Plus size={15}/>Discover Services</button>}</div></div>
    <div className="glass-card service-catalog-filters"><div className="search-wrapper"><Search size={16}/><input className="form-input" placeholder="Search service, device, or IP…" value={search} onChange={change(setSearch)}/></div><select className="form-select" value={device} onChange={change(setDevice)}><option value="">All devices</option>{devices.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select><select className="form-select" value={state} onChange={change(setState)}><option value="">All observed states</option><option value="running">Running</option><option value="stopped">Stopped</option><option value="unknown">Unknown</option></select><select className="form-select" value={monitoring} onChange={change(setMonitoring)}><option value="">Any monitoring state</option><option value="true">Monitored</option><option value="false">Not monitored</option></select></div>
    {error&&<div className="notice error">{error}</div>}
    <div className="result-summary">{loading?'Loading services…':`${filtered.length} of ${items.length} service(s)`}</div>
    <div className="glass-card data-grid-card">{!loading&&!visible.length?<div className="filtered-empty"><ListTree size={32}/><strong>No services found</strong><span>Run service discovery or adjust the filters.</span></div>:<table className="custom-table"><thead><tr><th>Device</th><th>Service</th><th>Observed</th><th>Start mode</th><th>Monitoring</th><th>Health</th><th>Last discovered</th><th></th></tr></thead><tbody>{visible.map(item=><tr key={item.id}><td><strong>{item.device_name}</strong><small>{item.ip_address||'No IP'}</small></td><td><strong>{item.display_name}</strong><small>{item.name}</small></td><td>{item.state}</td><td>{item.start_mode}</td><td>{item.monitored?'Enabled':'Disabled'}</td><td><span className={`badge badge-${!item.monitored?'unknown':item.monitor_state==='UP'?'online':item.monitor_state==='DOWN'?'offline':'unknown'}`}>{item.monitored?item.monitor_state:'NOT MONITORED'}</span></td><td>{item.last_discovered_at?new Date(item.last_discovered_at).toLocaleString():'—'}</td><td>{canManage?<button className="btn btn-secondary" onClick={()=>setEditing(item)}><Edit3 size={14}/>Configure</button>:item.monitored&&<button className="btn btn-secondary" onClick={()=>navigate(`/services/${item.id}`)}>Metrics</button>}</td></tr>)}</tbody></table>}</div>
    <Pagination page={page} pageSize={PAGE_SIZE} total={filtered.length} count={visible.length} disabled={loading} onPageChange={setPage}/>
    {editing&&<ServiceConfigModal service={editing} deviceName={editing.device_name} onClose={()=>setEditing(null)} onSaved={load}/>} 
  </div>;
}
