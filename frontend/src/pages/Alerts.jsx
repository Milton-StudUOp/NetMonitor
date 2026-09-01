import React, { useEffect, useState } from 'react';
import api from '../api/client';
import AlertBanner from '../components/AlertBanner';

export default function Alerts() {
  const [alerts, setAlerts] = useState([]);

  const fetchAlerts = async () => {
    try {
      const res = await api.get('/alerts');
      setAlerts(res.data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchAlerts();
    const interval = setInterval(fetchAlerts, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleResolve = async (id) => {
    await api.put(`/alerts/${id}/resolve`);
    fetchAlerts();
  };

  const handleClearAll = async () => {
    try {
      await api.delete('/alerts');
      fetchAlerts();
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h2 style={{ fontSize: '1.25rem', color: '#fff', fontWeight: 600 }}>
            Alerts and Incidents Center
          </h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>
            History of triggered alerts, probable-cause diagnostics, and resolution actions.
          </p>
        </div>

        {alerts.length > 0 && (
          <button className="btn btn-secondary" onClick={handleClearAll} style={{ padding: '8px 16px', fontSize: '0.85rem' }}>
            Clear All Alerts
          </button>
        )}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {alerts.length === 0 ? (
          <div className="glass-card" style={{ padding: '24px', color: 'var(--text-muted)' }}>
            No alerts recorded.
          </div>
        ) : (
          alerts.map((alert) => (
            <AlertBanner key={alert.id} alert={alert} onResolve={alert.is_resolved ? null : handleResolve} />
          ))
        )}
      </div>
    </div>
  );
}
