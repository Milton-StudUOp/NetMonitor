import React, { useEffect, useState } from 'react';
import { Activity, Bell, RefreshCw, CheckCircle, AlertOctagon, Radio } from 'lucide-react';
import api from '../api/client';

export default function History() {
  const [activeTab, setActiveTab] = useState('probes'); // 'probes' or 'alerts'
  const [probes, setProbes] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchHistoryData = async () => {
    setLoading(true);
    try {
      const [probeRes, alertRes] = await Promise.all([
        api.get('/history/probes?limit=100'),
        api.get('/alerts?limit=100'),
      ]);
      setProbes(probeRes.data);
      setAlerts(alertRes.data);
    } catch (err) {
      console.error('Failed to fetch history:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistoryData();
    const interval = setInterval(fetchHistoryData, 8000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h2 style={{ fontSize: '1.35rem', color: '#fff', fontWeight: 700, letterSpacing: '-0.01em' }}>
            Histórico Operacional de Rede em Tempo Real
          </h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginTop: '2px' }}>
            Acompanhe o registro sequencial de sondagens ICMP/SNMP e o histórico completo de incidentes salvos no banco de dados.
          </p>
        </div>

        <button
          className="btn btn-secondary"
          onClick={fetchHistoryData}
          disabled={loading}
          style={{ padding: '8px 16px', fontSize: '0.85rem', gap: '6px' }}
        >
          <RefreshCw size={14} className={loading ? 'spin' : ''} />
          Atualizar Dados
        </button>
      </div>

      {/* Navigation Tabs */}
      <div style={{ display: 'flex', gap: '12px', marginBottom: '20px', borderBottom: '1px solid var(--border-color)', paddingBottom: '12px' }}>
        <button
          onClick={() => setActiveTab('probes')}
          style={{
            background: activeTab === 'probes' ? 'rgba(59, 130, 246, 0.15)' : 'transparent',
            border: activeTab === 'probes' ? '1px solid rgba(59, 130, 246, 0.4)' : '1px solid transparent',
            color: activeTab === 'probes' ? '#3b82f6' : 'var(--text-muted)',
            padding: '8px 16px',
            borderRadius: '8px',
            fontSize: '0.875rem',
            fontWeight: 600,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            transition: 'all 0.2s ease',
          }}
        >
          <Activity size={16} /> Sondagens ICMP/SNMP ({probes.length})
        </button>

        <button
          onClick={() => setActiveTab('alerts')}
          style={{
            background: activeTab === 'alerts' ? 'rgba(239, 68, 68, 0.15)' : 'transparent',
            border: activeTab === 'alerts' ? '1px solid rgba(239, 68, 68, 0.4)' : '1px solid transparent',
            color: activeTab === 'alerts' ? '#ef4444' : 'var(--text-muted)',
            padding: '8px 16px',
            borderRadius: '8px',
            fontSize: '0.875rem',
            fontWeight: 600,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            transition: 'all 0.2s ease',
          }}
        >
          <Bell size={16} /> Incidentes e Alertas Registrados ({alerts.length})
        </button>
      </div>

      {/* Tab 1: Probes History */}
      {activeTab === 'probes' && (
        <div className="glass-card" style={{ overflow: 'hidden' }}>
          {probes.length === 0 ? (
            <div style={{ padding: '48px 24px', textAlign: 'center', color: 'var(--text-muted)' }}>
              <Radio size={40} style={{ marginBottom: '12px', opacity: 0.4 }} />
              <h4 style={{ color: '#fff', fontSize: '0.95rem', marginBottom: '4px' }}>Aguardando primeira rodada de sondagem...</h4>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>
                O motor de monitoramento executa pings a cada 5 segundos nos equipamentos cadastrados.
              </p>
            </div>
          ) : (
            <table className="custom-table">
              <thead>
                <tr>
                  <th>Data e Hora (Local)</th>
                  <th>Alvo / Equipamento</th>
                  <th>Tipo de Enlace</th>
                  <th>Resultado ICMP</th>
                  <th>Latência (ms)</th>
                  <th>Perda de Pacotes (%)</th>
                </tr>
              </thead>
              <tbody>
                {probes.map((p) => (
                  <tr key={p.id}>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                      {p.timestamp ? new Date(p.timestamp).toLocaleString('pt-PT') : '—'}
                    </td>
                    <td style={{ fontWeight: 600, color: '#fff' }}>{p.target_name}</td>
                    <td>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)', background: 'rgba(255, 255, 255, 0.05)', padding: '2px 6px', borderRadius: '4px' }}>
                        {p.target_type}
                      </span>
                    </td>
                    <td>
                      <span className={`badge badge-${p.status?.toLowerCase() === 'up' ? 'online' : 'offline'}`}>
                        {p.status}
                      </span>
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem' }}>
                      {p.latency_ms !== null && p.latency_ms !== undefined ? (
                        <span style={{ color: p.latency_ms < 50 ? '#10b981' : '#f59e0b' }}>
                          {p.latency_ms} ms
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem' }}>
                      {p.packet_loss_pct !== null && p.packet_loss_pct !== undefined ? (
                        <span style={{ color: p.packet_loss_pct === 0 ? '#10b981' : '#ef4444' }}>
                          {p.packet_loss_pct}%
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Tab 2: Alerts History */}
      {activeTab === 'alerts' && (
        <div className="glass-card" style={{ overflow: 'hidden' }}>
          {alerts.length === 0 ? (
            <div style={{ padding: '48px 24px', textAlign: 'center', color: 'var(--text-muted)' }}>
              <CheckCircle size={40} style={{ marginBottom: '12px', color: '#10b981', opacity: 0.6 }} />
              <h4 style={{ color: '#fff', fontSize: '0.95rem', marginBottom: '4px' }}>Nenhum alerta registrado</h4>
              <p style={{ fontSize: '0.8rem', color: 'var(--text-dim)' }}>
                Todos os equipamentos e grupos de redundância estão operando dentro da normalidade.
              </p>
            </div>
          ) : (
            <table className="custom-table">
              <thead>
                <tr>
                  <th>Data do Disparo</th>
                  <th>Severidade</th>
                  <th>Título do Evento</th>
                  <th>Mensagem / Causa Raiz</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {alerts.map((a) => (
                  <tr key={a.id}>
                    <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                      {a.created_at ? new Date(a.created_at).toLocaleString('pt-PT') : '—'}
                    </td>
                    <td>
                      <span className={`badge badge-${a.severity?.toLowerCase() || 'unknown'}`}>
                        {a.severity}
                      </span>
                    </td>
                    <td style={{ fontWeight: 600, color: '#fff' }}>{a.title}</td>
                    <td style={{ fontSize: '0.85rem' }}>
                      <div>{a.message}</div>
                      {a.root_cause && (
                        <div style={{ fontSize: '0.75rem', color: '#f59e0b', marginTop: '2px' }}>
                          Causa: {a.root_cause}
                        </div>
                      )}
                    </td>
                    <td>
                      {a.is_resolved ? (
                        <span className="badge badge-normal">Resolvido</span>
                      ) : (
                        <span className="badge badge-critical">Ativo</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
