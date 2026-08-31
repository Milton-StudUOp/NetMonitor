import React from 'react';
import {
  Activity,
  AlertTriangle,
  Clock3,
  GitFork,
  MapPin,
  Network,
  Server,
  ShieldCheck,
  ShieldX,
} from 'lucide-react';

const statusColors = {
  NORMAL: '#10b981',
  ONLINE: '#10b981',
  UP: '#10b981',
  DEGRADED: '#f59e0b',
  CRITICAL: '#ef4444',
  OFFLINE: '#ef4444',
  DOWN: '#ef4444',
  UNKNOWN: '#64748b',
};

function formatDate(value) {
  if (!value) return 'Aguardando primeira avaliação';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Data indisponível';
  return date.toLocaleString('pt-PT', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function EndpointCard({ role, type, target }) {
  const isDevice = type === 'DEVICE';
  const status = target?.status || 'UNKNOWN';
  const color = statusColors[status] || statusColors.UNKNOWN;
  const Icon = isDevice ? Server : Network;

  return (
    <div style={{
      minWidth: 0,
      padding: '16px',
      borderRadius: '10px',
      border: `1px solid ${color}45`,
      borderLeft: `3px solid ${color}`,
      background: 'rgba(15, 23, 42, 0.72)',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: '7px', color: 'var(--text-muted)', fontSize: '0.72rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
          <Icon size={14} color={color} /> {role}
        </span>
        <span className={`badge badge-${status.toLowerCase()}`}>{status}</span>
      </div>

      {target ? (
        <>
          <div style={{ color: '#fff', fontSize: '1rem', fontWeight: 700, marginBottom: '8px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={target.name}>
            {target.name}
          </div>
          {isDevice ? (
            <div style={{ display: 'grid', gap: '6px', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
              <div><span style={{ color: 'var(--text-dim)' }}>IP:</span> <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-main)' }}>{target.ip_address || 'Não configurado'}</span></div>
              <div><span style={{ color: 'var(--text-dim)' }}>Rede:</span> <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-main)' }}>{target.network || 'Não informada'}</span></div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}><MapPin size={12} /> {target.location || 'Localização não informada'}</div>
              <div><span style={{ color: 'var(--text-dim)' }}>Tipo:</span> {target.device_type || 'OTHER'}</div>
            </div>
          ) : (
            <div style={{ display: 'grid', gap: '6px', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
              <div><span style={{ color: 'var(--text-dim)' }}>Tecnologia:</span> {target.link_type || 'OTHER'}</div>
              <div><span style={{ color: 'var(--text-dim)' }}>Prioridade:</span> {target.priority || 'N/A'}</div>
              <div><span style={{ color: 'var(--text-dim)' }}>Pontas:</span> Equipamento #{target.source_device_id} → #{target.destination_device_id}</div>
              <div><span style={{ color: 'var(--text-dim)' }}>Intervalo:</span> {target.monitoring_interval || 5}s</div>
            </div>
          )}
        </>
      ) : (
        <div style={{ color: '#f87171', fontSize: '0.82rem' }}>Unidade não encontrada ou removida.</div>
      )}
    </div>
  );
}

function StatusMessage({ status, type }) {
  const isDevice = type === 'DEVICE';
  const messages = {
    NORMAL: `As duas ${isDevice ? 'unidades' : 'rotas'} estão operacionais e a tolerância a falhas está preservada.`,
    DEGRADED: `O serviço ainda possui uma ${isDevice ? 'unidade' : 'rota'} operacional, mas perdeu a tolerância a uma nova falha.`,
    CRITICAL: `As duas ${isDevice ? 'unidades' : 'rotas'} estão indisponíveis. O serviço pode estar interrompido.`,
    UNKNOWN: 'O grupo ainda não possui dados suficientes para determinar a disponibilidade.',
  };
  const color = statusColors[status] || statusColors.UNKNOWN;
  const Icon = status === 'NORMAL' ? ShieldCheck : status === 'CRITICAL' ? ShieldX : AlertTriangle;

  return (
    <div style={{ marginTop: '14px', padding: '11px 14px', borderRadius: '8px', border: `1px solid ${color}40`, background: `${color}12`, color, display: 'flex', alignItems: 'center', gap: '9px', fontSize: '0.8rem' }}>
      <Icon size={17} style={{ flexShrink: 0 }} />
      <span>{messages[status] || messages.UNKNOWN}</span>
    </div>
  );
}

export default function RedundancyPanel({ group }) {
  if (!group) return null;
  const type = group.redundancy_type || 'LINK';
  const primary = type === 'DEVICE' ? group.primary_device : group.primary_link;
  const secondary = type === 'DEVICE' ? group.secondary_device : group.secondary_link;
  const status = group.status || 'UNKNOWN';

  return (
    <div className="glass-card" style={{ padding: '20px', marginBottom: '16px' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '16px', gap: '16px', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
          <GitFork size={20} color="var(--color-info)" style={{ marginTop: '2px' }} />
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '9px', flexWrap: 'wrap' }}>
              <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#fff' }}>{group.name}</h3>
              <span style={{ padding: '3px 8px', borderRadius: '999px', background: 'rgba(59,130,246,.12)', border: '1px solid rgba(59,130,246,.3)', color: '#60a5fa', fontSize: '0.65rem', fontWeight: 700 }}>
                {type === 'DEVICE' ? 'EQUIPAMENTOS' : 'ENLACES'}
              </span>
            </div>
            {group.description && <p style={{ marginTop: '3px', fontSize: '0.78rem', color: 'var(--text-muted)' }}>{group.description}</p>}
          </div>
        </div>
        <span className={`badge badge-${status.toLowerCase()}`}>{status}</span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
        <EndpointCard role="Unidade Primária" type={type} target={primary} />
        <EndpointCard role="Unidade Secundária" type={type} target={secondary} />
      </div>

      <div style={{ marginTop: '13px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap', color: 'var(--text-dim)', fontSize: '0.74rem' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Activity size={13} /> Verificação: {group.service_check_type || 'NONE'}
          {group.service_check_target ? ` · ${group.service_check_target}` : ''}
          {group.service_check_port ? `:${group.service_check_port}` : ''}
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }} title={group.last_evaluated || ''}>
          <Clock3 size={13} /> Última avaliação: {formatDate(group.last_evaluated)}
        </span>
      </div>

      <StatusMessage status={status} type={type} />
    </div>
  );
}
