import React, { useEffect, useMemo, useRef, useState } from 'react';
import { LayoutGrid, Maximize2, Minimize2, Move, RotateCcw, Save, Trash2 } from 'lucide-react';
import ReactFlow, {
  BaseEdge,
  EdgeLabelRenderer,
  ReactFlowProvider,
  Background,
  Controls,
  Handle,
  Position,
  getSmoothStepPath,
  useEdgesState,
  useNodesState,
} from 'reactflow';
import 'reactflow/dist/style.css';
import api from '../api/client';
import DeviceIcon from './DeviceIcon';

const NODE_WIDTH = 190;
const HORIZONTAL_GAP = 110;
const VERTICAL_GAP = 190;
function prepareEdges(edges) {
  return edges.map((edge) => ({
    ...edge,
    type: 'topologyEdge',
    label: undefined,
    data: edge.data || {},
    sourceHandle: edge.data?.is_redundancy ? 'right' : 'bottom',
    targetHandle: edge.data?.is_redundancy ? 'left' : 'top',
  }));
}

function layoutTopology(nodes, edges) {
  const nodeIds = new Set(nodes.map((node) => node.id));
  const inDegree = new Map(nodes.map((node) => [node.id, 0]));
  const children = new Map(nodes.map((node) => [node.id, []]));

  edges.forEach((edge) => {
    if (edge.data?.is_redundancy) return;
    if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) return;
    children.get(edge.source).push(edge.target);
    inDegree.set(edge.target, inDegree.get(edge.target) + 1);
  });

  const depth = new Map();
  const queue = nodes
    .filter((node) => inDegree.get(node.id) === 0)
    .sort((a, b) => (a.data?.label || '').localeCompare(b.data?.label || ''));

  queue.forEach((node) => depth.set(node.id, 0));
  for (let index = 0; index < queue.length; index += 1) {
    const node = queue[index];
    const nodeDepth = depth.get(node.id) || 0;
    children.get(node.id).forEach((childId) => {
      depth.set(childId, Math.max(depth.get(childId) || 0, nodeDepth + 1));
      inDegree.set(childId, inDegree.get(childId) - 1);
      if (inDegree.get(childId) === 0) {
        queue.push(nodes.find((candidate) => candidate.id === childId));
      }
    });
  }

  // Cycles or isolated malformed links remain visible on the first layer.
  nodes.forEach((node) => {
    if (!depth.has(node.id)) depth.set(node.id, 0);
  });

  const layers = new Map();
  nodes.forEach((node) => {
    const level = depth.get(node.id);
    if (!layers.has(level)) layers.set(level, []);
    layers.get(level).push(node);
  });

  return nodes.map((node) => {
    const level = depth.get(node.id);
    const layer = layers.get(level);
    layer.sort((a, b) => (a.data?.label || '').localeCompare(b.data?.label || ''));
    const index = layer.findIndex((candidate) => candidate.id === node.id);
    const layerWidth = layer.length * NODE_WIDTH + (layer.length - 1) * HORIZONTAL_GAP;

    return {
      ...node,
      type: node.type || 'customDevice',
      position: {
        x: index * (NODE_WIDTH + HORIZONTAL_GAP) - layerWidth / 2,
        y: level * VERTICAL_GAP,
      },
      data: node.data || {},
    };
  });
}

const TopologyEdge = ({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  style,
  data = {},
}) => {
  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
    borderRadius: 18,
    offset: 28,
  });
  const hasWarning = Boolean(data.network_warning);
  const status = data.status || 'UNKNOWN';
  const hasStatusProblem = status !== 'UP';
  const showLabel = hasWarning || hasStatusProblem;
  const isDown = status === 'DOWN';
  const isUnknown = status === 'UNKNOWN';
  const isRedundancy = Boolean(data.is_redundancy);
  const text = isDown
    ? (isRedundancy ? 'Redundância crítica' : 'Enlace indisponível')
    : status === 'DEGRADED'
      ? (isRedundancy ? 'Redundância degradada' : 'Enlace degradado')
      : hasWarning
        ? 'Redes distintas'
        : 'Estado desconhecido';
  const accentColor = isDown ? '#f87171' : isUnknown ? '#94a3b8' : '#fbbf24';
  const borderColor = isDown ? '#ef444480' : isUnknown ? '#64748b80' : '#f59e0b80';
  const backgroundColor = isDown ? '#450a0af2' : isUnknown ? '#1e293bf2' : '#422006f2';
  const tooltip = [
    data.label,
    `Status: ${status}`,
    data.network_warning_reason,
  ].filter(Boolean).join(' — ');

  return (
    <>
      <BaseEdge id={id} path={edgePath} markerEnd={markerEnd} style={style} />
      {showLabel && <EdgeLabelRenderer>
        <div
          className="nodrag nopan"
          title={tooltip}
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            maxWidth: '170px',
            padding: '5px 9px',
            borderRadius: '999px',
            border: `1px solid ${borderColor}`,
            background: backgroundColor,
            boxShadow: '0 4px 12px rgba(0, 0, 0, 0.35)',
            color: accentColor,
            fontSize: '10px',
            fontWeight: 700,
            lineHeight: 1,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            pointerEvents: 'all',
            zIndex: 5,
          }}
        >
          ⚠ {text}
        </div>
      </EdgeLabelRenderer>}
    </>
  );
};

const CustomDeviceNode = ({ data = {} }) => {
  const statusColors = {
    ONLINE: '#10b981',
    UP: '#10b981',
    OFFLINE: '#ef4444',
    DOWN: '#ef4444',
    DEGRADED: '#f59e0b',
    UNKNOWN: '#64748b',
  };

  const status = data.status || 'UNKNOWN';
  const border = statusColors[status] || '#64748b';

  return (
    <div style={{
      padding: '12px 18px',
      borderRadius: '10px',
      background: '#0f172a',
      border: `2px solid ${border}`,
      boxShadow: `0 0 15px ${border}40`,
      color: '#fff',
      width: `${NODE_WIDTH}px`,
      boxSizing: 'border-box',
      textAlign: 'center',
    }}>
      <Handle id="top" type="target" position={Position.Top} style={{ background: border }} />
      <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>
        <span style={{display:'inline-flex',alignItems:'center',gap:'6px'}}><DeviceIcon size={15} color={border} icon={{lucide_name:data.icon_name,custom_data:data.icon_custom_data,mime_type:data.icon_mime_type}} />{data.device_type || 'EQUIPAMENTO'}</span>
      </div>
      <div style={{ fontSize: '0.95rem', fontWeight: 700, margin: '4px 0' }}>
        {data.label || 'Equipamento'}
      </div>
      <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
        {data.ip_address || 'Sem IP'}
      </div>
      {data.network && (
        <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginTop: '2px' }}>
          {data.network}
        </div>
      )}
      <div style={{ marginTop: '6px' }}>
        <span className={`badge badge-${status.toLowerCase()}`}>
          {status}
        </span>
      </div>
      <Handle id="bottom" type="source" position={Position.Bottom} style={{ background: border }} />
      <Handle id="right" type="source" position={Position.Right} style={{ background: '#22d3ee' }} />
      <Handle id="left" type="target" position={Position.Left} style={{ background: '#22d3ee' }} />
    </div>
  );
};

export default function TopologyGraph({ graphData }) {
  const nodeTypes = useMemo(() => ({ customDevice: CustomDeviceNode }), []);
  const edgeTypes = useMemo(() => ({ topologyEdge: TopologyEdge }), []);
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [layoutMode, setLayoutMode] = useState('auto');
  const [persistedPositions, setPersistedPositions] = useState(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [snapshots, setSnapshots] = useState([]);
  const [selectedSnapshotId, setSelectedSnapshotId] = useState('');
  const lastStructureRef = useRef('');
  const flowInstanceRef = useRef(null);
  const containerRef = useRef(null);

  const rawNodes = graphData?.nodes || [];
  const rawEdges = graphData?.edges || [];
  const structureSignature = useMemo(
    () => JSON.stringify({
      nodes: rawNodes.map((node) => node.id).sort(),
      edges: rawEdges.map((edge) => `${edge.source}>${edge.target}:${Boolean(edge.data?.is_redundancy)}`).sort(),
    }),
    [rawNodes, rawEdges],
  );

  useEffect(() => {
    api.get('/platform/topology-layout').then(({ data }) => {
      setLayoutMode(data.layout_mode || 'auto');
      setPersistedPositions(Object.fromEntries((data.positions || []).map(item => [`device_${item.device_id}`, { x:item.x, y:item.y }])));
    }).catch(() => setPersistedPositions({}));
    api.get('/platform/topology-layout/snapshots').then(({ data }) => setSnapshots(data)).catch(() => setSnapshots([]));
  }, []);

  const reloadSnapshots = () => api.get('/platform/topology-layout/snapshots').then(({ data }) => setSnapshots(data));

  const snapshotPayload = (name) => ({
    name,
    layout_mode: layoutMode,
    positions: nodes.map(node => ({ device_id:Number(node.id.replace('device_', '')), x:node.position.x, y:node.position.y })).filter(item => Number.isInteger(item.device_id)),
    viewport: flowInstanceRef.current?.getViewport?.() || {},
  });

  const createSnapshot = async () => {
    const suggested = `Vista ${new Date().toLocaleString()}`;
    const name = window.prompt('Nome da vista/layout:', suggested)?.trim();
    if (!name) return;
    try {
      const response = await api.post('/platform/topology-layout/snapshots', snapshotPayload(name));
      await reloadSnapshots(); setSelectedSnapshotId(String(response.data.id));
    } catch (error) { console.error('Unable to save topology view', error); }
  };

  const saveSnapshot = async () => {
    if (!selectedSnapshotId) return createSnapshot();
    const selected = snapshots.find(snapshot => String(snapshot.id) === String(selectedSnapshotId));
    if (!selected) return createSnapshot();
    try {
      await api.put(`/platform/topology-layout/snapshots/${selectedSnapshotId}`, snapshotPayload(selected.name));
      await reloadSnapshots();
    } catch (error) { console.error('Unable to update topology view', error); }
  };

  const restoreSnapshot = async () => {
    if (!selectedSnapshotId) return;
    try {
      const { data } = await api.post(`/platform/topology-layout/snapshots/${selectedSnapshotId}/restore`);
      const restored = Object.fromEntries(data.positions.map(item => [`device_${item.device_id}`, { x:item.x, y:item.y }]));
      setPersistedPositions(restored); setLayoutMode(data.layout_mode || 'free');
      setNodes(current => current.map(node => ({ ...node, position:restored[node.id] || node.position })));
      if (data.viewport && Number.isFinite(data.viewport.zoom)) {
        setTimeout(() => flowInstanceRef.current?.setViewport(data.viewport, { duration:350 }), 30);
      } else {
        setTimeout(() => flowInstanceRef.current?.fitView({ padding:0.2, duration:350 }), 30);
      }
    } catch (error) { console.error('Unable to restore topology view', error); }
  };

  const deleteSnapshot = async () => {
    if (!selectedSnapshotId || !window.confirm('Eliminar esta vista guardada?')) return;
    try { await api.delete(`/platform/topology-layout/snapshots/${selectedSnapshotId}`); setSelectedSnapshotId(''); await reloadSnapshots(); }
    catch (error) { console.error('Unable to delete topology view', error); }
  };

  useEffect(() => {
    const handleFullscreenChange = () => {
      const active = document.fullscreenElement === containerRef.current;
      setIsFullscreen(active);
      setTimeout(() => flowInstanceRef.current?.fitView({ padding: 0.15, duration: 250 }), 80);
    };
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  const toggleFullscreen = async () => {
    try {
      if (document.fullscreenElement === containerRef.current) {
        await document.exitFullscreen();
      } else if (containerRef.current?.requestFullscreen) {
        await containerRef.current.requestFullscreen();
      }
    } catch (error) {
      console.error('Unable to change topology fullscreen mode', error);
    }
  };

  useEffect(() => {
    const autoNodes = layoutTopology(rawNodes, rawEdges);
    const autoPositionById = new Map(autoNodes.map((node) => [node.id, node.position]));
    const savedPositions = persistedPositions ?? {};
    const structureChanged = lastStructureRef.current !== structureSignature;

    setNodes((currentNodes) => {
      const currentPositionById = new Map(currentNodes.map((node) => [node.id, node.position]));
      const shouldReorganize = currentNodes.length === 0 || (layoutMode === 'auto' && structureChanged);
      if (shouldReorganize) return autoNodes;

      return rawNodes.map((node) => ({
        ...node,
        type: node.type || 'customDevice',
        data: node.data || {},
        position: layoutMode === 'free'
          ? (savedPositions[node.id] || currentPositionById.get(node.id) || autoPositionById.get(node.id))
          : (currentPositionById.get(node.id) || autoPositionById.get(node.id)),
      }));
    });
    setEdges(prepareEdges(rawEdges));
    lastStructureRef.current = structureSignature;
  }, [graphData, structureSignature, layoutMode, persistedPositions, setNodes, setEdges]);

  const persistLayout = (mode, currentNodes) => {
    const positions = currentNodes.map(node => ({ device_id:Number(node.id.replace('device_', '')), x:node.position.x, y:node.position.y })).filter(x => Number.isInteger(x.device_id));
    // Keep the in-memory persisted snapshot synchronized immediately. Without
    // this, the 5-second topology refresh could reapply the stale snapshot
    // loaded when the component was mounted and visually undo a user drag.
    setPersistedPositions(Object.fromEntries(
      positions.map(item => [`device_${item.device_id}`, { x: item.x, y: item.y }]),
    ));
    api.put('/platform/topology-layout', { layout_mode:mode, positions }).catch(error => console.error('Unable to persist topology layout', error));
  };

  const changeLayoutMode = (mode) => {
    setLayoutMode(mode);
    if (mode === 'auto') {
      const arranged = layoutTopology(rawNodes, rawEdges);
      setNodes(arranged);
      persistLayout(mode, arranged);
      setTimeout(() => flowInstanceRef.current?.fitView({ padding: 0.2, duration: 350 }), 0);
    } else {
      persistLayout(mode, nodes);
    }
  };

  const reorganize = () => {
    const arranged = layoutTopology(rawNodes, rawEdges);
    setNodes(arranged);
    persistLayout(layoutMode, arranged);
    setTimeout(() => flowInstanceRef.current?.fitView({ padding: 0.2, duration: 350 }), 0);
  };

  const handleNodeDragStop = (_, node) => {
    if (layoutMode !== 'free') return;
    setNodes((currentNodes) => {
      const updated = currentNodes.map((item) => item.id === node.id ? { ...item, position: node.position } : item);
      persistLayout('free', updated);
      return updated;
    });
  };

  if (rawNodes.length === 0) {
    return (
      <div className="glass-card" style={{ width: '100%', height: 'clamp(620px, calc(100vh - 210px), 860px)', borderRadius: '12px', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', color: 'var(--text-muted)' }}>
        <p style={{ fontSize: '1rem', fontWeight: 500, marginBottom: '8px' }}>Nenhum equipamento cadastrado na topologia</p>
        <p style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>Cadastre equipamentos e links na barra lateral para visualizar a topologia em tempo real.</p>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="glass-card topology-canvas" style={{ width: '100%', height: isFullscreen ? '100vh' : 'clamp(620px, calc(100vh - 210px), 860px)', borderRadius: isFullscreen ? 0 : '12px', overflow: 'hidden', position: 'relative', background: '#111827' }}>
      <div style={{ position: 'absolute', top: '12px', right: '12px', left: '12px', zIndex: 10, display: 'flex', justifyContent:'flex-end', flexWrap:'wrap', gap: '6px', padding: '5px', borderRadius: '9px', background: 'rgba(15, 23, 42, 0.94)', border: '1px solid var(--border-color)', boxShadow: '0 6px 18px rgba(0,0,0,.28)' }}>
        <select className="form-select" value={selectedSnapshotId} onChange={event => setSelectedSnapshotId(event.target.value)} style={{ width:'190px', padding:'5px 8px', fontSize:'0.72rem' }} title="Vistas guardadas">
          <option value="">Vistas guardadas…</option>
          {snapshots.map(snapshot => <option key={snapshot.id} value={snapshot.id}>{snapshot.name}</option>)}
        </select>
        <button type="button" className="btn btn-secondary" onClick={saveSnapshot} style={{ padding:'6px 9px', fontSize:'0.72rem' }} title={selectedSnapshotId ? 'Atualizar a vista selecionada' : 'Guardar uma nova vista'}><Save size={14}/> {selectedSnapshotId ? 'Salvar' : 'Guardar vista'}</button>
        <button type="button" className="btn btn-secondary" onClick={createSnapshot} style={{ padding:'6px 9px', fontSize:'0.72rem' }} title="Guardar o layout atual como uma nova vista">+ Nova vista</button>
        <button type="button" className="btn btn-secondary" disabled={!selectedSnapshotId} onClick={restoreSnapshot} style={{ padding:'6px 9px', fontSize:'0.72rem' }} title="Recuperar a vista selecionada"><RotateCcw size={14}/> Recuperar</button>
        <button type="button" className="btn btn-danger" disabled={!selectedSnapshotId} onClick={deleteSnapshot} style={{ padding:'6px 8px', fontSize:'0.72rem' }} title="Eliminar a vista selecionada"><Trash2 size={14}/></button>
        <button type="button" className={`btn ${layoutMode === 'auto' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => changeLayoutMode('auto')} style={{ padding: '6px 9px', fontSize: '0.72rem' }} title="Organização hierárquica automática">
          <LayoutGrid size={14} /> Automático
        </button>
        <button type="button" className={`btn ${layoutMode === 'free' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => changeLayoutMode('free')} style={{ padding: '6px 9px', fontSize: '0.72rem' }} title="Permite arrastar e guardar posições">
          <Move size={14} /> Livre
        </button>
        <button type="button" className="btn btn-secondary" onClick={reorganize} style={{ padding: '6px 9px', fontSize: '0.72rem' }} title="Recalcular a organização da topologia">
          Reorganizar
        </button>
        <button type="button" className="btn btn-secondary" onClick={toggleFullscreen} style={{ padding: '6px 9px', fontSize: '0.72rem' }} title={isFullscreen ? 'Sair da tela cheia' : 'Abrir topologia em tela cheia'}>
          {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          {isFullscreen ? 'Sair' : 'Tela cheia'}
        </button>
      </div>
      <ReactFlowProvider>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeDragStop={handleNodeDragStop}
          nodesDraggable={layoutMode === 'free'}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onInit={(instance) => { flowInstanceRef.current = instance; }}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.35}
        >
          <Background color="#1e293b" gap={16} />
          <Controls style={{ background: '#0f172a', borderColor: 'var(--border-color)', color: '#fff' }} />
        </ReactFlow>
      </ReactFlowProvider>
    </div>
  );
}
