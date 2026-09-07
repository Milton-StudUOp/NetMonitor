import React from 'react';
import { Wifi, WifiOff, KeyRound, LogOut } from 'lucide-react';

export default function Header({ isConnected, user, onLogout, onChangePassword, title = 'Dashboard' }) {
  return (
    <header style={{
      height: '64px',
      borderBottom: '1px solid var(--border-color)',
      background: 'rgba(15, 23, 42, 0.6)',
      backdropFilter: 'blur(12px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 24px',
    }}>
      <h1 style={{ fontSize: '1.25rem', fontWeight: 600, color: '#fff' }}>
        {title}
      </h1>

      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '6px 12px',
          borderRadius: '9999px',
          fontSize: '0.8rem',
          fontWeight: 500,
          background: isConnected ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)',
          color: isConnected ? '#10b981' : '#ef4444',
          border: `1px solid ${isConnected ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
        }}>
          {isConnected ? <Wifi size={14} /> : <WifiOff size={14} />}
          <span>{isConnected ? 'Real-time WebSocket' : 'Disconnected'}</span>
        </div>
        <div className="header-user"><div><strong>{user?.display_name}</strong><span>{user?.role}</span></div><button className="icon-button" onClick={onChangePassword} title="Change password"><KeyRound size={16}/></button><button className="icon-button" onClick={onLogout} title="Sign out"><LogOut size={16}/></button></div>
      </div>
    </header>
  );
}
