import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Activity, LayoutGrid, Maximize2, Minimize2, Move, RefreshCw, RotateCcw, Save, Trash2 } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import ReactFlow, { Background, Controls, MarkerType, MiniMap, Position, useEdgesState, useNodesState } from 'reactflow';
import 'reactflow/dist/style.css';
import api from '../api/client';
import ServiceConfigModal from '../components/ServiceConfigModal';
import { getApiErrorMessage } from '../utils/errors';

const colors={UP:'#22c55e',DOWN:'#ef4444',SUSPECTED:'#f59e0b',RECOVERING:'#f59e0b',UNKNOWN:'#64748b'};
const POSITION_KEY='netmonitor.service-topology.positions';
const VIEW_KEY='netmonitor.service-topology.views';
const read=(key,fallback)=>{try{return JSON.parse(localStorage.getItem(key)||'null')||fallback;}catch{return fallback;}};

function buildGraph(data,selected) {
  const devices=selected?data.devices.filter(x=>String(x.id)===selected):data.devices;
  const visibleIds=new Set(devices.map(x=>x.id)); const services=data.services.filter(x=>visibleIds.has(x.device_id)); const nodes=[];
  devices.forEach((device,column)=>{const own=services.filter(x=>x.device_id===device.id);const x=column*360;
    nodes.push({id:`device-${device.id}`,type:'default',position:{x,y:20},sourcePosition:Position.Bottom,targetPosition:Position.Top,data:{kind:'device',record:device,label:<div className="rf-device-node"><strong>{device.name}</strong><span>{device.ip_address||device.location}</span><b>{device.status}</b></div>},style:{width:250,border:`1px solid ${device.status==='ONLINE'?'#3b82f6':'#ef4444'}`,borderRadius:12,background:'#111827',color:'#fff',padding:0}});
    own.forEach((service,row)=>nodes.push({id:`service-${service.id}`,position:{x:x+15,y:155+row*105},sourcePosition:Position.Bottom,targetPosition:Position.Top,data:{kind:'service',record:service,label:<div className="rf-service-node"><span style={{background:colors[service.monitor_state]}}/><div><strong>{service.display_name}</strong><small>{service.name} · {service.state}</small></div><b style={{color:colors[service.monitor_state]}}>{service.monitor_state}</b></div>},style:{width:220,border:`1px solid ${colors[service.monitor_state]}`,borderRadius:10,background:'#0f172a',color:'#fff',padding:0}}));
  });
  const edges=services.map(service=>({id:`edge-${service.id}`,source:`device-${service.device_id}`,target:`service-${service.id}`,type:'smoothstep',markerEnd:{type:MarkerType.ArrowClosed,color:colors[service.monitor_state]},style:{stroke:colors[service.monitor_state],strokeWidth:1.5},animated:['DOWN','SUSPECTED'].includes(service.monitor_state)}));
  return {nodes,edges};
}

export default function ServiceTopology() {
  const navigate=useNavigate(); const [params,setParams]=useSearchParams(); const container=useRef(null); const flow=useRef(null);
  const [data,setData]=useState({devices:[],services:[],edges:[]}); const [error,setError]=useState(''); const [loading,setLoading]=useState(true); const [layout,setLayout]=useState('auto'); const [fullscreen,setFullscreen]=useState(false); const [editing,setEditing]=useState(null);
  const [nodes,setNodes,onNodesChange]=useNodesState([]); const [edges,setEdges,onEdgesChange]=useEdgesState([]); const [views,setViews]=useState(()=>read(VIEW_KEY,[])); const [viewId,setViewId]=useState('');
  const selected=params.get('device')||''; const generated=useMemo(()=>buildGraph(data,selected),[data,selected]);
  const load=()=>{setLoading(true);setError('');api.get('/services/topology').then(r=>setData(r.data)).catch(e=>setError(getApiErrorMessage(e))).finally(()=>setLoading(false));};
  useEffect(()=>{load();const timer=setInterval(load,5000);return()=>clearInterval(timer);},[]);
  useEffect(()=>{const saved=read(POSITION_KEY,{});setNodes(generated.nodes.map(n=>({...n,position:layout==='free'&&saved[n.id]?saved[n.id]:n.position})));setEdges(generated.edges);},[generated,layout,setNodes,setEdges]);
  useEffect(()=>{const listener=()=>setFullscreen(document.fullscreenElement===container.current);document.addEventListener('fullscreenchange',listener);return()=>document.removeEventListener('fullscreenchange',listener);},[]);
  const persist=current=>{const positions=Object.fromEntries(current.map(n=>[n.id,n.position]));localStorage.setItem(POSITION_KEY,JSON.stringify(positions));};
  const dragStop=(_,node)=>{if(layout!=='free')return;setNodes(current=>{const next=current.map(x=>x.id===node.id?{...x,position:node.position}:x);persist(next);return next;});};
  const reorganize=()=>{setNodes(generated.nodes);persist(generated.nodes);setTimeout(()=>flow.current?.fitView({padding:.2,duration:350}),0);};
  const changeLayout=value=>{setLayout(value);if(value==='auto')reorganize();else persist(nodes);};
  const toggleFullscreen=async()=>document.fullscreenElement===container.current?document.exitFullscreen():container.current?.requestFullscreen?.();
  const saveViews=next=>{setViews(next);localStorage.setItem(VIEW_KEY,JSON.stringify(next));};
  const newView=()=>{const name=window.prompt('View/layout name:',`View ${new Date().toLocaleString('en-GB')}`)?.trim();if(!name)return;const item={id:String(Date.now()),name,positions:Object.fromEntries(nodes.map(n=>[n.id,n.position])),viewport:flow.current?.getViewport?.()};saveViews([...views,item]);setViewId(item.id);};
  const saveView=()=>{if(!viewId)return newView();saveViews(views.map(v=>v.id===viewId?{...v,positions:Object.fromEntries(nodes.map(n=>[n.id,n.position])),viewport:flow.current?.getViewport?.()}:v));};
  const restoreView=()=>{const view=views.find(v=>v.id===viewId);if(!view)return;setLayout('free');setNodes(current=>current.map(n=>({...n,position:view.positions[n.id]||n.position})));if(view.viewport)setTimeout(()=>flow.current?.setViewport(view.viewport,{duration:350}),0);};
  const deleteView=()=>{if(!viewId||!window.confirm('Delete this saved view?'))return;saveViews(views.filter(v=>v.id!==viewId));setViewId('');};
  const openNode=(_,node)=>node.data.kind==='service'?setEditing(node.data.record):navigate(`/devices/${node.data.record.id}?from=service-topology`);

  return <div className="data-page"><div className="page-title"><div><h2>Service Topology</h2><p>Live topology with reusable views, automatic or free layout, zoom, pan, and fullscreen.</p></div><div className="row-actions"><select className="form-select compact" value={selected} onChange={e=>setParams(e.target.value?{device:e.target.value}:{})}><option value="">All monitored devices</option>{data.devices.map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select><button className="btn btn-secondary" onClick={load}><RefreshCw size={15} className={loading?'spin':''}/>Refresh</button></div></div>{error&&<div className="notice error">{error}</div>}
    <section ref={container} className="glass-card service-reactflow-board topology-canvas">{!nodes.length?<div className="service-placeholder"><Activity size={38}/><strong>No monitored service topology</strong><span>Discover and add services first.</span></div>:<><div className="service-topology-toolbar"><select className="form-select compact" value={viewId} onChange={e=>setViewId(e.target.value)}><option value="">My saved views…</option>{views.map(v=><option key={v.id} value={v.id}>{v.name}</option>)}</select><button className="btn btn-secondary" onClick={saveView}><Save size={14}/>{viewId?'Save':'Save View'}</button><button className="btn btn-secondary" onClick={newView}>+ New View</button><button className="btn btn-secondary" disabled={!viewId} onClick={restoreView}><RotateCcw size={14}/>Restore</button><button className="btn btn-danger" disabled={!viewId} onClick={deleteView}><Trash2 size={14}/></button><button className={`btn ${layout==='auto'?'btn-primary':'btn-secondary'}`} onClick={()=>changeLayout('auto')}><LayoutGrid size={14}/>Automatic</button><button className={`btn ${layout==='free'?'btn-primary':'btn-secondary'}`} onClick={()=>changeLayout('free')}><Move size={14}/>Free</button><button className="btn btn-secondary" onClick={reorganize}>Reorganize</button><button className="btn btn-secondary" onClick={toggleFullscreen}>{fullscreen?<Minimize2 size={14}/>:<Maximize2 size={14}/>} {fullscreen?'Exit':'Fullscreen'}</button></div><ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} onEdgesChange={onEdgesChange} onNodeDragStop={dragStop} onNodeDoubleClick={openNode} onInit={instance=>flow.current=instance} fitView fitViewOptions={{padding:.2}} minZoom={.15} maxZoom={1.8} nodesDraggable={layout==='free'} nodesConnectable={false} elementsSelectable><Background color="#334155" gap={22}/><MiniMap pannable zoomable nodeColor={node=>node.id.startsWith('device-')?'#3b82f6':colors[node.data?.record?.monitor_state]||'#64748b'}/><Controls showInteractive={false}/></ReactFlow></>}</section>
    <ServiceConfigModal service={editing} deviceName={data.devices.find(x=>x.id===editing?.device_id)?.name} onClose={()=>setEditing(null)} onSaved={load}/>
  </div>;
}
