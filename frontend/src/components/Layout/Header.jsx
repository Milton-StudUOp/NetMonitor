import React from 'react';
import { Wifi, WifiOff, KeyRound, LogOut, Monitor, Moon, Sun } from 'lucide-react';

export default function Header({ isConnected, user, theme, onThemeChange, onLogout, onChangePassword, title = 'Dashboard' }) {
  return (
    <header className="app-header" style={{
      height: '64px',
      borderBottom: '1px solid var(--border-color)',
      background: 'var(--header-bg)',
      backdropFilter: 'blur(12px)',
      display: 'flex',
      flexShrink: 0,
      minWidth: 0,
      overflowX: 'auto',
      overflowY: 'hidden',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 24px',
    }}>
      <h1 style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--text-main)' }}>
        {title}
      </h1>

      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <label className="theme-selector" title="Application theme"><span className="sr-only">Theme</span>{theme==='light'?<Sun size={15}/>:theme==='dark'?<Moon size={15}/>:<Monitor size={15}/>}<select value={theme} onChange={event=>onThemeChange(event.target.value)} aria-label="Application theme"><option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option></select></label>
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
