import React, { useEffect, useState } from 'react';
import api from '../api/client';
import TopologyGraph from '../components/TopologyGraph';

export default function Topology() {
  const [topology, setTopology] = useState(null);

  const fetchTopology = async () => {
    try {
      const res = await api.get('/topology');
      setTopology(res.data);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchTopology();
    const interval = setInterval(fetchTopology, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div>
      <div style={{ marginBottom: '20px' }}>
        <h2 style={{ fontSize: '1.25rem', color: '#fff', fontWeight: 600 }}>
          Network Topology View
        </h2>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>
          Real-time graph of devices, primary links (solid lines), and redundant paths (dashed lines).
        </p>
      </div>

      <TopologyGraph graphData={topology} />
    </div>
  );
}
