import React, { useEffect, useState } from 'react';
import { Server, Network, GitFork, AlertTriangle, ShieldCheck } from 'lucide-react';
import api from '../api/client';
import StatusCard from '../components/StatusCard';
import AlertBanner from '../components/AlertBanner';
import RedundancyPanel from '../components/RedundancyPanel';
import TopologyGraph from '../components/TopologyGraph';

export default function Dashboard() {
  const [summary, setSummary] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [redundancyGroups, setRedundancyGroups] = useState([]);
  const [topology, setTopology] = useState(null);

  const fetchData = async () => {
    try {
      const [sumRes, alertRes, rgRes, topoRes] = await Promise.all([
        api.get('/dashboard/summary'),
        api.get('/alerts?is_resolved=false'),
        api.get('/redundancy-groups'),
        api.get('/topology'),
      ]);
      setSummary(sumRes.data);
      setAlerts(alertRes.data);
      setRedundancyGroups(rgRes.data);
      setTopology(topoRes.data);
    } catch (err) {
      console.error('Failed to fetch dashboard data:', err);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  const topAlert = alerts.length > 0 ? alerts[0] : null;

  return (
    <div>
      {/* Top Banner if unresolved alert */}
      {topAlert && (
        <AlertBanner
          alert={topAlert}
          onResolve={async (id) => {
            await api.put(`/alerts/${id}/resolve`);
            fetchData();
          }}
        />
      )}

      {/* KPI Cards Grid */}
      <div className="grid-cards">
        <StatusCard
          title="Equipamentos Monitorados"
          count={summary?.total_devices ?? 0}
          icon={Server}
          type="info"
          subtitle={`${summary?.online_devices ?? 0} Online · ${summary?.offline_devices ?? 0} Offline`}
        />
        <StatusCard
          title="Links de Comunicação"
          count={summary?.total_links ?? 0}
          icon={Network}
          type="info"
          subtitle={`${summary?.up_links ?? 0} UP · ${summary?.down_links ?? 0} DOWN`}
        />
        <StatusCard
          title="Grupos de Redundância"
          count={summary?.total_redundancy_groups ?? 0}
          icon={GitFork}
          type={summary?.degraded_redundancy_groups > 0 ? 'degraded' : 'normal'}
          subtitle={`${summary?.normal_redundancy_groups ?? 0} Normal · ${summary?.degraded_redundancy_groups ?? 0} Degradados`}
        />
        <StatusCard
          title="Alertas Ativos"
          count={summary?.active_alerts_count ?? 0}
          icon={AlertTriangle}
          type={summary?.critical_alerts_count > 0 ? 'critical' : (summary?.active_alerts_count > 0 ? 'degraded' : 'normal')}
          subtitle={`${summary?.critical_alerts_count ?? 0} Críticos`}
        />
      </div>

      {/* Redundancy Groups Overview */}
      <div style={{ marginBottom: '24px' }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: '#fff', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <ShieldCheck size={20} color="var(--color-info)" /> Estado da Redundância em Tempo Real
        </h2>
        {redundancyGroups.length === 0 ? (
          <div className="glass-card" style={{ padding: '20px', color: 'var(--text-muted)' }}>
            Nenhum grupo de redundância cadastrado.
          </div>
        ) : (
          redundancyGroups.map((g) => <RedundancyPanel key={g.id} group={g} />)
        )}
      </div>

      {/* Full-width topology */}
      <div>
          <h3 style={{ fontSize: '1rem', fontWeight: 600, color: '#fff', marginBottom: '12px' }}>
            Mapa da Topologia de Enlaces
          </h3>
          <TopologyGraph graphData={topology} />
      </div>
    </div>
  );
}
