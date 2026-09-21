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
const collectedAt=item=>item?.collected_at?new Date(item.collected_at).toLocaleString():'Awaiting data';

export default function MetricsMonitoring({user}){
  const navigate=useNavigate();
  const canManage=user?.role !== 'VIEWER';
  return <div className="data-page">
    <div className="page-title"><div><h2>Metrics Monitoring</h2><p>Windows, Linux, and SNMP system, storage, network, and process telemetry.</p></div>{canManage&&<div className="row-actions"><button className="btn btn-primary" onClick={()=>navigate('/metrics-discovery')}>Discover Metrics</button></div>}</div>
    <MonitoredDevicesSection canManage={canManage}/>
  </div>;
}

export function MonitoredDevicesSection({ embedded=false,canManage=false }){
  const [rows,setRows]=useState([]); const [search,setSearch]=useState(''); const [selectedDeviceId,setSelectedDeviceId]=useState(''); const [loading,setLoading]=useState(true); const [error,setError]=useState('');
  const load=()=>{setLoading(true);api.get('/metrics/overview').then(r=>{setRows(r.data);setError('');}).catch(e=>setError(getApiErrorMessage(e))).finally(()=>setLoading(false));};
  useEffect(()=>{load();const timer=setInterval(load,15000);return()=>clearInterval(timer);},[]);
  const visible=useMemo(()=>rows.filter(x=>!search||`${x.device.name} ${x.device.ip_address||''}`.toLowerCase().includes(search.toLowerCase())),[rows,search]);
  useEffect(()=>{if(!selectedDeviceId&&visible.length)setSelectedDeviceId(String(visible[0].device.id));},[visible,selectedDeviceId]);
  const selectedRow=visible.find(x=>String(x.device.id)===selectedDeviceId)||visible[0]||rows[0];
  const latest=selectedRow?.latest;
  return <section className={embedded?'dashboard-monitored-devices':'metrics-monitoring-section'}>
    {error&&<div className="notice error">{error}</div>}
    <section className="glass-card analytics-panel">
      <div className="panel-title metrics-panel-heading"><div><span className="metrics-eyebrow">Live inventory</span><h3>Monitored devices</h3><p>Latest normalized Windows, Linux, and SNMP metrics by device.</p></div><button className="btn btn-secondary" onClick={load}><RefreshCw size={15} className={loading?'spin':''}/>Refresh</button></div>
      {selectedRow&&<SelectedMetricDevice row={selectedRow} canManage={canManage}/>}
      <div className="metrics-toolbar"><div className="search-wrapper metrics-search"><Search size={16}/><input className="form-input" placeholder="Search device or IP…" value={search} onChange={e=>setSearch(e.target.value)}/></div><span>{visible.length} device(s)</span></div>
      <div className="metrics-device-grid">{visible.map(row=><MetricDeviceCard key={row.device.id} {...row} canManage={canManage} selected={String(row.device.id)===String(selectedRow?.device?.id)} onSelect={()=>setSelectedDeviceId(String(row.device.id))}/>)}</div>
      {!loading&&!visible.length&&<div className="service-placeholder"><Activity size={32}/><span>No devices have active metric monitoring. Discover metrics and select the required categories.</span></div>}
    </section>
  </section>;
}

function SelectedMetricDevice({row,canManage}){
  const navigate=useNavigate(); const {device,latest:item}=row;
  return <div className="metrics-spotlight">
    <div className="metrics-spotlight-main"><div className="metrics-device-identity"><span className="metrics-eyebrow">Device overview</span><h3>{device.name}</h3><p>{device.ip_address||'No IP address'} <span aria-hidden="true">•</span> Updated {collectedAt(item)}</p></div><span className={`badge badge-${device.status==='ONLINE'?'online':'offline'}`}>{device.status}</span></div>
    <div className="metrics-spotlight-grid"><Metric icon={Cpu} label="CPU usage" value={scalar(item,'cpu',item?.cpu_percent,'%')}/><Metric icon={MemoryStick} label="Memory" value={scalar(item,'memory',item?.memory_percent,'%')}/><Metric icon={Activity} label="System uptime" value={enabled(item,'uptime')?(item?.uptime_seconds==null?'Awaiting data':uptime(item.uptime_seconds)):'Not monitored'}/><Metric icon={Network} label="Interfaces" value={count(item,'network_interfaces',item?.network_interfaces?.length)}/></div>
    <div className="metrics-spotlight-actions"><button className="btn btn-secondary" onClick={()=>navigate(`/devices/${device.id}`)}>Open analytics</button>{canManage&&<button className="btn btn-primary" onClick={()=>navigate(`/metrics-discovery?device=${device.id}`)}><Edit3 size={14}/>Configure metrics</button>}</div>
  </div>
}

function MetricDeviceCard({device,latest:item,selected,onSelect,canManage}){
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
    <div className="metrics-values">{metricRows.map(([key,icon,label,value])=><div key={key} className={`metric-tile ${!enabled(item,key)?'metric-not-monitored':''}`}><span className="metric-tile-label">{icon}{label}</span><b>{value}</b></div>)}</div>
    <div className="metric-card-footer"><small>Updated {collectedAt(item)}</small>{canManage&&<button className="metric-config-link" onClick={event=>{event.stopPropagation();navigate(`/metrics-discovery?device=${device.id}`)}}><Edit3 size={14}/>Configure</button>}</div>
    <MetricDetails item={item}/>
  </article>;
}

function Metric({icon:Icon,label,value}){return <div className="metric-highlight"><span className="metric-highlight-icon"><Icon size={18}/></span><div><span>{label}</span><strong className={value==='Not monitored'?'metric-not-monitored':''}>{value}</strong></div></div>}
function MetricDetails({item}){return <details className="metric-details"><summary>View collected details</summary><div className="metric-detail-sections"><section className="system-information-detail"><h4>System information</h4><dl>{Object.entries(item.system_information||{}).map(([k,v])=><div key={k}><dt>{k.replaceAll('_',' ')}</dt><dd title={String(v??'—')}>{String(v??'—')}</dd></div>)}</dl></section><section><h4>Storage</h4>{enabled(item,'storage')?item.storage?.map(x=><p key={x.name}><strong>{x.name} {x.label}</strong><span>{x.used_percent}% used · {bytes(x.free_bytes)} free / {bytes(x.size_bytes)}</span></p>):<p className="metric-not-monitored">Not monitored</p>}</section><section><h4>Network interfaces</h4>{enabled(item,'network_interfaces')?item.network_interfaces?.map(x=><p key={x.index??x.name}><strong>{x.name}</strong><span className={`interface-state ${interfaceState(x)}`}>{interfaceLabel(x)}</span></p>):<p className="metric-not-monitored">Not monitored</p>}</section><section><h4>Top processes</h4>{enabled(item,'processes')?item.processes?.slice(0,10).map(x=><p key={`${x.name}-${x.process_id}`}><strong>{x.name} (PID {x.process_id})</strong><span>CPU {x.cpu_percent}% · Memory {bytes(x.working_set_bytes)}</span></p>):<p className="metric-not-monitored">Not monitored</p>}</section><section><h4>Recent critical events</h4>{enabled(item,'events')?item.events?.slice(0,10).map((x,i)=><p key={`${x.event_code}-${i}`}><strong>{x.source} · Event {x.event_code}</strong><span>{x.message||'No event message'}</span></p>):<p className="metric-not-monitored">Not monitored</p>}</section></div></details>}
function interfaceState(item){const state=String(item.oper_status||item.status||'unknown').trim().toLowerCase();if(['up','running','connected','online','1','true'].includes(state))return 'up';if(['down','disconnected','disabled','notpresent','not present','lowerlayerdown','lower-layer-down','dormant','offline','2','false'].includes(state))return 'down';return 'unknown'}
function interfaceLabel(item){const state=interfaceState(item);return state==='up'?'Up':state==='down'?'Down':'Status unavailable'}
function formatRate(value){return value==null?'Awaiting second sample':value>=1e9?`${(value/1e9).toFixed(2)} Gbps`:value>=1e6?`${(value/1e6).toFixed(2)} Mbps`:value>=1e3?`${(value/1e3).toFixed(2)} Kbps`:`${value.toFixed(0)} bps`}
