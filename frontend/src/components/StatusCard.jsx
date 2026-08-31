import React from 'react';

export default function StatusCard({ title, count, icon: Icon, type = 'normal', subtitle }) {
  const typeColors = {
    normal: { text: '#10b981', border: 'rgba(16, 185, 129, 0.3)', bg: 'rgba(16, 185, 129, 0.1)' },
    degraded: { text: '#f59e0b', border: 'rgba(245, 158, 11, 0.3)', bg: 'rgba(245, 158, 11, 0.1)' },
    critical: { text: '#ef4444', border: 'rgba(239, 68, 68, 0.3)', bg: 'rgba(239, 68, 68, 0.1)' },
    info: { text: '#3b82f6', border: 'rgba(59, 130, 246, 0.3)', bg: 'rgba(59, 130, 246, 0.1)' },
  };

  const style = typeColors[type] || typeColors.info;

  return (
    <div className="glass-card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)', fontWeight: 500 }}>
          {title}
        </span>
        {Icon && (
          <div style={{
            width: '36px',
            height: '36px',
            borderRadius: '10px',
            background: style.bg,
            border: `1px solid ${style.border}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: style.text,
          }}>
            <Icon size={18} />
          </div>
        )}
      </div>

      <div style={{ fontSize: '2rem', fontWeight: 700, color: '#fff', lineHeight: 1 }}>
        {count}
      </div>

      {subtitle && (
        <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
          {subtitle}
        </span>
      )}
    </div>
  );
}
