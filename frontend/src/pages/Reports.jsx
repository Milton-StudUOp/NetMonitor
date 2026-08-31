import React, { useEffect, useState } from 'react';
import api from '../api/client';
import { FileText, Download } from 'lucide-react';

export default function Reports() {
  const [period, setPeriod] = useState('daily');
  const [reportData, setReportData] = useState(null);

  const fetchReport = async () => {
    try {
      const res = await api.get(`/reports?period=${period}`);
      setReportData(res.data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchReport();
  }, [period]);

  const metrics = reportData?.metrics;

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
        <div>
          <h2 style={{ fontSize: '1.25rem', color: '#fff', fontWeight: 600 }}>
            Relatórios e Indicadores SLA / MTTR / MTBF
          </h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>
            Análise consolidada de disponibilidade da infraestrutura e perdas de redundância.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '12px' }}>
          {['daily', 'weekly', 'monthly'].map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`btn ${period === p ? 'btn-primary' : 'btn-secondary'}`}
              style={{ textTransform: 'capitalize' }}
            >
              {p === 'daily' ? 'Diário' : p === 'weekly' ? 'Semanal' : 'Mensal'}
            </button>
          ))}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '20px', marginBottom: '24px' }}>
        <div className="glass-card" style={{ padding: '20px' }}>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Disponibilidade Geral (SLA)</span>
          <div style={{ fontSize: '2.5rem', fontWeight: 700, color: '#10b981', margin: '8px 0' }}>
            {metrics?.availability_pct ?? 100}%
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Baseado no histórico de sondagens ICMP/SNMP</span>
        </div>

        <div className="glass-card" style={{ padding: '20px' }}>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Tempo Médio de Reparo (MTTR)</span>
          <div style={{ fontSize: '2.5rem', fontWeight: 700, color: '#3b82f6', margin: '8px 0' }}>
            {metrics?.mttr_minutes ?? 0} <span style={{ fontSize: '1rem' }}>min</span>
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Média até a resolução de incidentes</span>
        </div>

        <div className="glass-card" style={{ padding: '20px' }}>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Perdas de Redundância</span>
          <div style={{ fontSize: '2.5rem', fontWeight: 700, color: '#f59e0b', margin: '8px 0' }}>
            {metrics?.redundancy_loss_events ?? 0}
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Ocorrências em que a redundância evitou a queda</span>
        </div>
      </div>
    </div>
  );
}
