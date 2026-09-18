import React from 'react';
import { AlertTriangle, AlertCircle, Info, CheckCircle2, Clock3, SearchCheck } from 'lucide-react';

const severityConfig = {
  CRITICAL: { Icon: AlertCircle, label: 'Critical' },
  WARNING: { Icon: AlertTriangle, label: 'Warning' },
  INFORMATION: { Icon: Info, label: 'Information' },
};

export default function AlertBanner({ alert, onResolve }) {
  if (!alert) return null;
  const severity = severityConfig[alert.severity] ? alert.severity : 'INFORMATION';
  const { Icon, label } = severityConfig[severity];
  const resolved = Boolean(alert.is_resolved || alert.resolved_at);

  return (
    <article className={`incident-card severity-${severity.toLowerCase()}${resolved ? ' is-resolved' : ''}`}>
      <div className="incident-icon" aria-hidden="true"><Icon size={20} /></div>
      <div className="incident-content">
        <header className="incident-header">
          <div className="incident-title-row">
            <h4>{alert.title}</h4>
            <span className="incident-severity">{label}</span>
            {resolved && <span className="incident-resolved"><CheckCircle2 size={12}/> Resolved</span>}
          </div>
          {onResolve && <button onClick={() => onResolve(alert.id)} className="btn btn-secondary incident-action"><CheckCircle2 size={14}/> Resolve</button>}
        </header>
        <p className="incident-message">{alert.message}</p>
        <div className="incident-meta">
          <span><Clock3 size={13}/> Triggered {alert.created_at ? new Date(alert.created_at).toLocaleString() : 'at an unknown time'}</span>
          {alert.resolved_at && <span><CheckCircle2 size={13}/> Resolved {new Date(alert.resolved_at).toLocaleString()}</span>}
        </div>
        {alert.root_cause && <div className="incident-cause"><SearchCheck size={14}/><span>Probable cause</span><strong>{alert.root_cause}</strong></div>}
      </div>
    </article>
  );
}
