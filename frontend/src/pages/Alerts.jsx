import React, { useCallback, useEffect, useState } from 'react';
import { Filter, RefreshCw, Trash2, X } from 'lucide-react';
import api from '../api/client';
import AlertBanner from '../components/AlertBanner';
import Pagination from '../components/Pagination';
import { getApiErrorMessage } from '../utils/errors';

const defaults = { search:'', severity:'', state:'', source_type:'', source_id:'', start:'', end:'', limit:'100', page:'1' };
const dateBoundary = (value, endOfDay) => new Date(`${value}T${endOfDay?'23:59:59.999':'00:00:00'}`).toISOString();
const queryFrom = filters => { const query = new URLSearchParams(); Object.entries(filters).forEach(([key,value]) => { if (!value) return; const apiKey = key === 'state' ? 'is_resolved' : key; const normalized = ['start','end'].includes(key) ? dateBoundary(value,key==='end') : key === 'state' ? String(value === 'resolved') : value; query.set(apiKey, normalized); }); return query.toString(); };

export default function Alerts() {
  const [filters, setFilters] = useState(defaults); const [alerts, setAlerts] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false); const [error, setError] = useState('');
  const fetchAlerts = useCallback(async () => { setLoading(true); setError(''); try { const response=await api.get(`/alerts?${queryFrom(filters)}`);setAlerts(response.data);setTotal(Number(response.headers['x-total-count']??response.data.length)); } catch (err) { setError(getApiErrorMessage(err)); } finally { setLoading(false); } }, [filters]);
  useEffect(() => { fetchAlerts(); const timer = setInterval(fetchAlerts, 15000); return () => clearInterval(timer); }, [fetchAlerts]);
  const change = event => setFilters(old => ({...old,[event.target.name]:event.target.value,page:'1'}));
  const handleResolve = async id => { await api.put(`/alerts/${id}/resolve`); fetchAlerts(); };
  const clearAll = async () => { if (window.confirm('Permanently delete every alert?')) { await api.delete('/alerts'); fetchAlerts(); } };
  const hasFilters = Object.entries(filters).some(([key,value]) => key !== 'limit' && value);
  return <div className="data-page">
    <div className="page-title"><div><h2>Alerts and Incidents Center</h2><p>Filter incidents, review timestamps and probable causes, and manage resolution.</p></div><div className="row-actions"><button className="btn btn-secondary" onClick={fetchAlerts} disabled={loading}><RefreshCw size={15} className={loading?'spin':''}/> Refresh</button>{alerts.length>0&&<button className="btn btn-danger" onClick={clearAll}><Trash2 size={15}/> Clear All</button>}</div></div>
    <div className="glass-card filter-panel"><div className="filter-panel-title"><Filter size={16}/><strong>Alert filters</strong>{hasFilters&&<button onClick={()=>setFilters(defaults)}><X size={14}/> Clear filters</button>}</div><div className="filter-grid">
      <div className="form-group filter-search"><label className="form-label">Search</label><input name="search" className="form-input" placeholder="Title, message, or probable cause" value={filters.search} onChange={change}/></div>
      <div className="form-group"><label className="form-label">Severity</label><select name="severity" className="form-select" value={filters.severity} onChange={change}><option value="">All severities</option><option>INFORMATION</option><option>WARNING</option><option>CRITICAL</option></select></div>
      <div className="form-group"><label className="form-label">State</label><select name="state" className="form-select" value={filters.state} onChange={change}><option value="">All states</option><option value="active">Active</option><option value="resolved">Resolved</option></select></div>
      <div className="form-group"><label className="form-label">Source</label><select name="source_type" className="form-select" value={filters.source_type} onChange={change}><option value="">All sources</option><option value="DEVICE">Device</option><option value="LINK">Link</option><option value="REDUNDANCY_GROUP">Redundancy group</option></select></div>
      <div className="form-group"><label className="form-label">Source ID</label><input name="source_id" type="number" min="1" className="form-input" value={filters.source_id} onChange={change}/></div>
      <div className="form-group"><label className="form-label">From date</label><input name="start" type="date" className="form-input" value={filters.start} onChange={change}/></div>
      <div className="form-group"><label className="form-label">To date</label><input name="end" type="date" className="form-input" value={filters.end} onChange={change}/></div>
      <div className="form-group"><label className="form-label">Maximum results</label><select name="limit" className="form-select" value={filters.limit} onChange={change}><option>50</option><option>100</option><option>250</option><option>500</option></select></div>
    </div></div>
    {error&&<div className="notice error">{error}</div>}<div className="result-summary">{loading?'Loading alerts…':`${alerts.length} alert(s) found`}</div>
    <div className="alert-list data-grid-card">{!loading&&alerts.length===0?<div className="glass-card filtered-empty"><strong>No alerts match these filters</strong><span>Adjust or clear the filters to see more incidents.</span></div>:alerts.map(alert=><AlertBanner key={alert.id} alert={alert} onResolve={alert.is_resolved?null:handleResolve}/>)}</div>
    <Pagination page={Number(filters.page)} pageSize={Number(filters.limit)} total={total} count={alerts.length} disabled={loading} onPageChange={page=>setFilters(old=>({...old,page:String(page)}))}/>
  </div>;
}
