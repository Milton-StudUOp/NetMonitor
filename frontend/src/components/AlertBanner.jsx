import React from 'react';
import { AlertTriangle, AlertCircle, Info, CheckCircle2, Clock3 } from 'lucide-react';

export default function AlertBanner({ alert, onResolve }) {
  if (!alert) return null;

  const isCritical = alert.severity === 'CRITICAL';
  const isWarning = alert.severity === 'WARNING';

  const bg = isCritical ? 'rgba(239, 68, 68, 0.15)' : (isWarning ? 'rgba(245, 158, 11, 0.15)' : 'rgba(59, 130, 246, 0.15)');
  const border = isCritical ? 'rgba(239, 68, 68, 0.4)' : (isWarning ? 'rgba(245, 158, 11, 0.4)' : 'rgba(59, 130, 246, 0.4)');
  const text = isCritical ? '#ef4444' : (isWarning ? '#f59e0b' : '#3b82f6');
  const Icon = isCritical ? AlertCircle : (isWarning ? AlertTriangle : Info);

  return (
    <div style={{
      background: bg,
      border: `1px solid ${border}`,
      borderRadius: '12px',
      padding: '16px 20px',
      marginBottom: '24px',
      display: 'flex',
      alignItems: 'flex-start',
      gap: '16px',
    }}>
      <div style={{ color: text, marginTop: '2px' }}>
        <Icon size={22} />
      </div>

      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '4px' }}>
          <h4 style={{ color: '#fff', fontSize: '0.95rem', fontWeight: 600 }}>
            {alert.title}
          </h4>
          <span className={`badge badge-${(alert.severity || 'INFORMATION').toLowerCase()}`}>
            {alert.severity || 'INFORMATION'}
          </span>
        </div>
        <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', lineHeight: 1.5 }}>
          {alert.message}
        </p>
        <div className="alert-dates"><span><Clock3 size={13}/> Triggered {alert.created_at ? new Date(alert.created_at).toLocaleString() : 'at an unknown time'}</span>{alert.resolved_at && <span><CheckCircle2 size={13}/> Resolved {new Date(alert.resolved_at).toLocaleString()}</span>}</div>

        {alert.root_cause && (
          <div style={{
            marginTop: '8px',
            padding: '8px 12px',
            background: 'rgba(0, 0, 0, 0.2)',
            borderRadius: '6px',
            fontSize: '0.8rem',
            color: '#fbbf24',
            fontFamily: 'var(--font-mono)',
          }}>
            📍 <strong>Probable Cause:</strong> {alert.root_cause}
          </div>
        )}
      </div>

      {onResolve && (
        <button
          onClick={() => onResolve(alert.id)}
          className="btn btn-secondary"
          style={{ fontSize: '0.8rem', padding: '6px 12px' }}
        >
          <CheckCircle2 size={14} /> Resolve
        </button>
      )}
    </div>
  );
}
