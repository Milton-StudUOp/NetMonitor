import React, { useEffect, useMemo, useState } from 'react';
import { Activity, Cpu, Edit3, HardDrive, MemoryStick, Network, RefreshCw, Search } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import api from '../api/client';
import { getApiErrorMessage } from '../utils/errors';
import '../styles/metrics.css';

const bytes=value=>value==null?'—':value>=1073741824?`${(value/1073741824).toFixed(1)} GB`:value>=1048576?`${(value/1048576).toFixed(1)} MB`:`${value} B`;
const uptime=value=>value==null?'—':`${Math.floor(value/86400)}d ${Math.floor(value%86400/3600)}h`;
const enabled=(item,key)=>item?.enabled_metrics?.includes(key);
const scalar=(item,key,value,suffix='')=>enabled(item,key)?(value==null?'Awaiting data':`${value}${suffix}`):'Not monitored';
const count=(item,key,value)=>enabled(item,key)?(value==null?'Awaiting data':value):'Not monitored';

export default function MetricsMonitoring(){
  const navigate=useNavigate();
  return <div className="data-page">
    <div className="page-title"><div><h2>Metrics Monitoring</h2><p>Windows, Linux, and SNMP system, storage, network, and process telemetry.</p></div><div className="row-actions"><button className="btn btn-primary" onClick={()=>navigate('/metrics-discovery')}>Discover Metrics</button></div></div>
    <MonitoredDevicesSection />
  </div>;
}

export function MonitoredDevicesSection({ embedded=false }){
  const [rows,setRows]=useState([]); const [search,setSearch]=useState(''); const [selectedDeviceId,setSelectedDeviceId]=useState(''); const [loading,setLoading]=useState(true); const [error,setError]=useState('');
  const load=()=>{setLoading(true);api.get('/metrics/overview').then(r=>{setRows(r.data);setError('');}).catch(e=>setError(getApiErrorMessage(e))).finally(()=>setLoading(false));};
  useEffect(()=>{load();const timer=setInterval(load,15000);return()=>clearInterval(timer);},[]);
  const visible=useMemo(()=>rows.filter(x=>!search||`${x.device.name} ${x.device.ip_address||''}`.toLowerCase().includes(search.toLowerCase())),[rows,search]);
  useEffect(()=>{if(!selectedDeviceId&&visible.length)setSelectedDeviceId(String(visible[0].device.id));},[visible,selectedDeviceId]);
  const selectedRow=visible.find(x=>String(x.device.id)===selectedDeviceId)||visible[0]||rows[0];
  const latest=selectedRow?.latest;
  return <section className={embedded?'dashboard-monitored-devices':'metrics-monitoring-section'}>
    {error&&<div className="notice error">{error}</div>}
    <div className="metrics-selected-context">{selectedRow?`Showing metrics for ${selectedRow.device.name}`:'No device selected'}</div>
    <div className="service-kpi-grid"><Metric icon={Cpu} label="CPU" value={scalar(latest,'cpu',latest?.cpu_percent,'%')}/><Metric icon={MemoryStick} label="Memory" value={scalar(latest,'memory',latest?.memory_percent,'%')}/><Metric icon={Activity} label="Uptime" value={enabled(latest,'uptime')?(latest?.uptime_seconds==null?'Awaiting data':uptime(latest.uptime_seconds)):'Not monitored'}/><Metric icon={Network} label="Interfaces" value={count(latest,'network_interfaces',latest?.network_interfaces?.length)}/></div>
    <section className="glass-card analytics-panel">
      <div className="panel-title"><div><h3>Monitored devices</h3><p>Latest normalized Windows, Linux, and SNMP metrics by device.</p></div><button className="btn btn-secondary" onClick={load}><RefreshCw size={15} className={loading?'spin':''}/>Refresh</button></div>
      <div className="search-wrapper metrics-search"><Search size={16}/><input className="form-input" placeholder="Search device or IP…" value={search} onChange={e=>setSearch(e.target.value)}/></div>
      <div className="metrics-device-grid">{visible.map(row=><MetricDeviceCard key={row.device.id} {...row} selected={String(row.device.id)===String(selectedRow?.device?.id)} onSelect={()=>setSelectedDeviceId(String(row.device.id))}/>)}</div>
      {!loading&&!visible.length&&<div className="service-placeholder"><Activity size={32}/><span>No devices have active metric monitoring. Discover metrics and select the required categories.</span></div>}
    </section>
  </section>;
}

function MetricDeviceCard({device,latest:item,selected,onSelect}){
  const navigate=useNavigate();
  const metricRows=[
    ['cpu',<Cpu size={15}/>,'CPU',scalar(item,'cpu',item.cpu_percent,'%')],
    ['memory',<MemoryStick size={15}/>,'Memory',scalar(item,'memory',item.memory_percent,'%')],
    ['uptime',<Activity size={15}/>,'Uptime',enabled(item,'uptime')?(item.uptime_seconds==null?'Awaiting data':uptime(item.uptime_seconds)):'Not monitored'],
    ['storage',<HardDrive size={15}/>,'Disks',count(item,'storage',item.storage?.length)],
    ['network_interfaces',<Network size={15}/>,'Interfaces',count(item,'network_interfaces',item.network_interfaces?.length)],
  ];
  return <article className={`metrics-device-card ${selected?'selected':''}`} onClick={onSelect}>
    <header onDoubleClick={()=>navigate(`/devices/${device.id}`)}><div><strong>{device.name}</strong><span>{device.ip_address||'No IP'}</span></div><span className={`badge badge-${device.status==='ONLINE'?'online':'offline'}`}>{device.status}</span></header>
    <div className="metrics-values">{metricRows.map(([key,icon,label,value])=><span key={key} className={!enabled(item,key)?'metric-not-monitored':''}>{icon}{label}<b>{value}</b></span>)}</div>
    <small>Collected {new Date(item.collected_at).toLocaleString()}</small>
    <div className="metric-card-actions"><button className="btn btn-secondary" onClick={()=>navigate(`/metrics-discovery?device=${device.id}`)}><Edit3 size={14}/>Edit monitored metrics</button></div>
    <MetricDetails item={item}/>
  </article>;
}

function Metric({icon:Icon,label,value}){return <div className="glass-card service-kpi"><Icon size={22}/><div><span>{label}</span><strong className={value==='Not monitored'?'metric-not-monitored':''}>{value}</strong></div></div>}
function MetricDetails({item}){return <details className="metric-details"><summary>View collected details</summary><div className="metric-detail-sections"><section className="system-information-detail"><h4>System information</h4><dl>{Object.entries(item.system_information||{}).map(([k,v])=><div key={k}><dt>{k.replaceAll('_',' ')}</dt><dd title={String(v??'—')}>{String(v??'—')}</dd></div>)}</dl></section><section><h4>Storage</h4>{enabled(item,'storage')?item.storage?.map(x=><p key={x.name}><strong>{x.name} {x.label}</strong><span>{x.used_percent}% used · {bytes(x.free_bytes)} free / {bytes(x.size_bytes)}</span></p>):<p className="metric-not-monitored">Not monitored</p>}</section><section><h4>Network interfaces</h4>{enabled(item,'network_interfaces')?item.network_interfaces?.map(x=><p key={x.index??x.name}><strong>{x.name}</strong><span className={`interface-state ${interfaceState(x)}`}>{interfaceLabel(x)}</span></p>):<p className="metric-not-monitored">Not monitored</p>}</section><section><h4>Top processes</h4>{enabled(item,'processes')?item.processes?.slice(0,10).map(x=><p key={`${x.name}-${x.process_id}`}><strong>{x.name} (PID {x.process_id})</strong><span>CPU {x.cpu_percent}% · Memory {bytes(x.working_set_bytes)}</span></p>):<p className="metric-not-monitored">Not monitored</p>}</section><section><h4>Recent critical events</h4>{enabled(item,'events')?item.events?.slice(0,10).map((x,i)=><p key={`${x.event_code}-${i}`}><strong>{x.source} · Event {x.event_code}</strong><span>{x.message||'No event message'}</span></p>):<p className="metric-not-monitored">Not monitored</p>}</section></div></details>}
function interfaceState(item){const state=String(item.oper_status||item.status||'unknown').toLowerCase();return state==='up'||state==='down'?state:'unknown'}
function interfaceLabel(item){const state=interfaceState(item);return state==='up'?'Up':state==='down'?'Down':'Status unavailable'}
function formatRate(value){return value==null?'Awaiting second sample':value>=1e9?`${(value/1e9).toFixed(2)} Gbps`:value>=1e6?`${(value/1e6).toFixed(2)} Mbps`:value>=1e3?`${(value/1e3).toFixed(2)} Kbps`:`${value.toFixed(0)} bps`}
