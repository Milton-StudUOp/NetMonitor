import React, { useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Server,
  Network,
  GitFork,
  AlertTriangle,
  GitBranch,
  History,
  FileText,
  Activity,
  Radar,
  Settings,
  HeartPulse,
  ScanSearch,
  Gauge,
  ChevronDown,
} from 'lucide-react';

export default function Sidebar({ user }) {
  const location=useLocation();
  const networkPaths=['/topology','/redundancy','/devices','/links','/discovery'];
  const networkActive=networkPaths.some(path=>location.pathname===path||location.pathname.startsWith(`${path}/`));
  const [networkOpen,setNetworkOpen]=useState(networkActive);
  const servicesActive=location.pathname.startsWith('/service-')||location.pathname.startsWith('/services');
  const [servicesOpen,setServicesOpen]=useState(servicesActive);
  const metricsActive=location.pathname.startsWith('/metrics-');
  const [metricsOpen,setMetricsOpen]=useState(metricsActive);
  const navItems = [
    { to: '/', label: 'Dashboard', icon: LayoutDashboard },
    { to: '/alerts', label: 'Alerts', icon: AlertTriangle },
    { to: '/history', label: 'History', icon: History },
    { to: '/reports', label: 'Reports', icon: FileText },
    ...(user?.role === 'ADMINISTRATOR' ? [{ to: '/settings', label: 'Settings', icon: Settings }] : []),
    ...(user?.role === 'ADMINISTRATOR' ? [{ to: '/system-health', label: 'System Health', icon: HeartPulse }] : []),
  ];

  return (
    <aside className="app-sidebar" style={{
      width: '260px',
      background: 'var(--sidebar-bg)',
      borderRight: '1px solid var(--border-color)',
      display: 'flex',
      flexDirection: 'column',
      flexShrink: 0,
      minHeight: 0,
      overflowY: 'auto',
      overflowX: 'hidden',
      scrollbarGutter: 'stable',
      padding: '20px 16px',
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        marginBottom: '32px',
        padding: '0 8px',
      }}>
        <div style={{
          width: '36px',
          height: '36px',
          borderRadius: '10px',
          background: 'linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: '0 0 15px rgba(59, 130, 246, 0.4)',
        }}>
          <Activity size={22} color="#fff" />
        </div>
        <div>
          <h2 style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-main)', letterSpacing: '-0.02em' }}>
            NetMonitor
          </h2>
          <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Link & Redundancy
          </span>
        </div>
      </div>

      <nav style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        {navItems.slice(0,1).map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              style={({ isActive }) => ({
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                padding: '12px 14px',
                borderRadius: '8px',
                fontSize: '0.9rem',
                fontWeight: 500,
                color: isActive ? 'var(--text-main)' : 'var(--text-muted)',
                background: isActive ? 'rgba(59, 130, 246, 0.15)' : 'transparent',
                border: isActive ? '1px solid rgba(59, 130, 246, 0.3)' : '1px solid transparent',
                textDecoration: 'none',
                transition: 'all 0.2s ease',
              })}
            >
              <Icon size={18} />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
        <div className={`sidebar-nav-group ${networkActive?'active':''}`}>
          <button className="sidebar-nav-group-toggle" onClick={()=>setNetworkOpen(value=>!value)} aria-expanded={networkOpen}><Network size={18}/><span>Network Monitoring</span><ChevronDown size={15} className={networkOpen?'open':''}/></button>
          {networkOpen&&<div className="sidebar-nav-children"><NavLink to="/topology"><GitBranch size={14}/>Topology</NavLink><NavLink to="/redundancy"><GitFork size={14}/>Redundancy</NavLink><NavLink to="/devices"><Server size={14}/>Devices</NavLink><NavLink to="/links"><Network size={14}/>Links</NavLink>{user?.role!=='VIEWER'&&<NavLink to="/discovery"><Radar size={14}/>Discovery</NavLink>}</div>}
        </div>
        <div className={`sidebar-nav-group ${servicesActive?'active':''}`}>
          <button className="sidebar-nav-group-toggle" onClick={()=>setServicesOpen(value=>!value)} aria-expanded={servicesOpen}><Activity size={18}/><span>Services Monitoring</span><ChevronDown size={15} className={servicesOpen?'open':''}/></button>
          {servicesOpen&&<div className="sidebar-nav-children"><NavLink to="/service-topology"><GitBranch size={14}/>Topology</NavLink><NavLink to="/service-monitoring"><Activity size={14}/>Service Monitoring</NavLink>{user?.role!=='VIEWER'&&<NavLink to="/service-discovery"><ScanSearch size={14}/>Discovery</NavLink>}</div>}
        </div>
        <div className={`sidebar-nav-group ${metricsActive?'active':''}`}>
          <button className="sidebar-nav-group-toggle" onClick={()=>setMetricsOpen(value=>!value)} aria-expanded={metricsOpen}><Gauge size={18}/><span>Metrics Monitoring</span><ChevronDown size={15} className={metricsOpen?'open':''}/></button>
          {metricsOpen&&<div className="sidebar-nav-children"><NavLink to="/metrics-monitoring"><Gauge size={14}/>Metrics Monitoring</NavLink>{user?.role!=='VIEWER'&&<NavLink to="/metrics-discovery"><ScanSearch size={14}/>Discover Windows Metrics</NavLink>}</div>}
        </div>
        {navItems.slice(1).map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              style={({ isActive }) => ({
                display: 'flex', alignItems: 'center', gap: '12px', padding: '12px 14px', borderRadius: '8px',
                fontSize: '0.9rem', fontWeight: 500, color: isActive ? 'var(--text-main)' : 'var(--text-muted)',
                background: isActive ? 'rgba(59, 130, 246, 0.15)' : 'transparent',
                border: isActive ? '1px solid rgba(59, 130, 246, 0.3)' : '1px solid transparent',
                textDecoration: 'none', transition: 'all 0.2s ease',
              })}
            >
              <Icon size={18}/><span>{item.label}</span>
            </NavLink>
          );
        })}
      </nav>
    </aside>
  );
}
