import React from 'react';
import { NavLink } from 'react-router-dom';
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
} from 'lucide-react';

export default function Sidebar({ user }) {
  const navItems = [
    { to: '/', label: 'Dashboard', icon: LayoutDashboard },
    { to: '/topology', label: 'Topology', icon: GitBranch },
    { to: '/redundancy', label: 'Redundancy', icon: GitFork },
    { to: '/alerts', label: 'Alerts', icon: AlertTriangle },
    { to: '/devices', label: 'Devices', icon: Server },
    { to: '/links', label: 'Links', icon: Network },
    { to: '/history', label: 'History', icon: History },
    { to: '/reports', label: 'Reports', icon: FileText },
    ...(user?.role !== 'VIEWER' ? [{ to: '/discovery', label: 'Discovery', icon: Radar }] : []),
    ...(user?.role === 'ADMINISTRATOR' ? [{ to: '/settings', label: 'Settings', icon: Settings }] : []),
    ...(user?.role === 'ADMINISTRATOR' ? [{ to: '/system-health', label: 'System Health', icon: HeartPulse }] : []),
  ];

  return (
    <aside style={{
      width: '260px',
      background: '#0d1322',
      borderRight: '1px solid var(--border-color)',
      display: 'flex',
      flexDirection: 'column',
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
          <h2 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#fff', letterSpacing: '-0.02em' }}>
            NetMonitor
          </h2>
          <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Link & Redundancy
          </span>
        </div>
      </div>

      <nav style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
        {navItems.map((item) => {
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
                color: isActive ? '#fff' : 'var(--text-muted)',
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
      </nav>
    </aside>
  );
}
