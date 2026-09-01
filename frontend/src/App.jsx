import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Sidebar from './components/Layout/Sidebar';
import Header from './components/Layout/Header';
import ErrorBoundary from './components/ErrorBoundary';
import { useWebSocket } from './hooks/useWebSocket';

import Dashboard from './pages/Dashboard';
import Topology from './pages/Topology';
import Redundancy from './pages/Redundancy';
import Alerts from './pages/Alerts';
import Devices from './pages/Devices';
import Links from './pages/Links';
import History from './pages/History';
import Reports from './pages/Reports';
import Discovery from './pages/Discovery';
import PlatformSettings from './pages/PlatformSettings';

export default function App() {
  const { isConnected } = useWebSocket((event) => {
    console.log('WS Event received:', event);
  });

  return (
    <BrowserRouter>
      <div className="app-layout">
        <Sidebar />
        <div className="main-content">
          <Header isConnected={isConnected} />
          <div className="page-body">
            <ErrorBoundary>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/topology" element={<Topology />} />
                <Route path="/redundancy" element={<Redundancy />} />
                <Route path="/alerts" element={<Alerts />} />
                <Route path="/devices" element={<Devices />} />
                <Route path="/links" element={<Links />} />
                <Route path="/history" element={<History />} />
                <Route path="/reports" element={<Reports />} />
                <Route path="/discovery" element={<Discovery />} />
                <Route path="/settings" element={<PlatformSettings />} />
              </Routes>
            </ErrorBoundary>
          </div>
        </div>
      </div>
    </BrowserRouter>
  );
}
