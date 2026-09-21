import React, { Suspense, lazy, useEffect, useState } from 'react';
import { Server, Network, GitFork, AlertTriangle } from 'lucide-react';
import api from '../api/client';
import StatusCard from '../components/StatusCard';
import AlertBanner from '../components/AlertBanner';
import TopologyGraph from '../components/TopologyGraph';
import { MonitoredDevicesSection } from './MetricsMonitoring';

const ServiceTopology = lazy(() => import('./ServiceTopology'));

export default function Dashboard({user}) {
  const [summary, setSummary] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [topology, setTopology] = useState(null);

  const fetchData = async () => {
    try {
      const [sumRes, alertRes, topoRes] = await Promise.all([
        api.get('/dashboard/summary'),
        api.get('/alerts?is_resolved=false'),
        api.get('/topology'),
      ]);
      setSummary(sumRes.data);
      setAlerts(alertRes.data);
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
          title="Monitored Devices"
          count={summary?.total_devices ?? 0}
          icon={Server}
          type="info"
          subtitle={`${summary?.online_devices ?? 0} Online · ${summary?.offline_devices ?? 0} Offline`}
        />
        <StatusCard
          title="Communication Links"
          count={summary?.total_links ?? 0}
          icon={Network}
          type="info"
          subtitle={`${summary?.up_links ?? 0} UP · ${summary?.down_links ?? 0} DOWN`}
        />
        <StatusCard
          title="Redundancy Groups"
          count={summary?.total_redundancy_groups ?? 0}
          icon={GitFork}
          type={summary?.degraded_redundancy_groups > 0 ? 'degraded' : 'normal'}
          subtitle={`${summary?.normal_redundancy_groups ?? 0} Normal · ${summary?.degraded_redundancy_groups ?? 0} Degraded`}
        />
        <StatusCard
          title="Active Alerts"
          count={summary?.active_alerts_count ?? 0}
          icon={AlertTriangle}
          type={summary?.critical_alerts_count > 0 ? 'critical' : (summary?.active_alerts_count > 0 ? 'degraded' : 'normal')}
          subtitle={`${summary?.critical_alerts_count ?? 0} Critical`}
        />
      </div>

      {/* Full-width topology */}
      <div>
          <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)', marginBottom: '12px' }}>
            Network Topology
          </h3>
          <TopologyGraph graphData={topology} />
      </div>
      <div className="dashboard-topology-section">
        <h3 style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-main)', marginBottom: '12px' }}>Service Topology</h3>
        <Suspense fallback={<div className="glass-card analytics-state">Loading service topology…</div>}><ServiceTopology embedded /></Suspense>
      </div>
      <div className="dashboard-topology-section">
        <MonitoredDevicesSection embedded canManage={user?.role !== 'VIEWER'} />
      </div>
    </div>
  );
}
