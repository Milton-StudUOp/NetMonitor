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
            Reports and Metrics SLA / MTTR / MTBF
          </h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>
            Consolidated analysis of infrastructure availability and redundancy losses.
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
              {p === 'daily' ? 'Daily' : p === 'weekly' ? 'Weekly' : 'Monthly'}
            </button>
          ))}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '20px', marginBottom: '24px' }}>
        <div className="glass-card" style={{ padding: '20px' }}>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Overall Availability (SLA)</span>
          <div style={{ fontSize: '2.5rem', fontWeight: 700, color: '#10b981', margin: '8px 0' }}>
            {metrics?.availability_pct ?? 100}%
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Based on probe history ICMP/SNMP</span>
        </div>

        <div className="glass-card" style={{ padding: '20px' }}>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Mean Time to Repair (MTTR)</span>
          <div style={{ fontSize: '2.5rem', fontWeight: 700, color: '#3b82f6', margin: '8px 0' }}>
            {metrics?.mttr_minutes ?? 0} <span style={{ fontSize: '1rem' }}>min</span>
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Average time to incident resolution</span>
        </div>

        <div className="glass-card" style={{ padding: '20px' }}>
          <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Redundancy Losses</span>
          <div style={{ fontSize: '2.5rem', fontWeight: 700, color: '#f59e0b', margin: '8px 0' }}>
            {metrics?.redundancy_loss_events ?? 0}
          </div>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Events where redundancy prevented an outage</span>
        </div>
      </div>
    </div>
  );
}
