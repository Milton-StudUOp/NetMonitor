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
          Visualização da Topologia da Rede
        </h2>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>
          Grafo em tempo real dos equipamentos, enlaces primários (linha contínua) e caminhos redundantes (linha tracejada).
        </p>
      </div>

      <TopologyGraph graphData={topology} />
    </div>
  );
}
