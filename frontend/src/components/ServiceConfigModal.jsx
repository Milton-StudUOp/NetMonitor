import React, { useEffect, useState } from 'react';
import { Save, X } from 'lucide-react';
import api from '../api/client';
import { getApiErrorMessage } from '../utils/errors';

export default function ServiceConfigModal({ service, deviceName, onClose, onSaved }) {
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!service) return;
    setForm({
      expected_state: service.expected_state || 'running',
      check_interval: service.check_interval || 60,
      failure_threshold: service.failure_threshold || 3,
      recovery_threshold: service.recovery_threshold || 2,
      severity: service.severity || 'CRITICAL',
      notifications_enabled: service.notifications_enabled ?? true,
    });
    setError('');
  }, [service]);

  if (!service || !form) return null;
  const update = (key, value) => setForm(current => ({ ...current, [key]: value }));
  const submit = async (monitored) => {
    setBusy(monitored ? 'save' : 'stop'); setError('');
    try {
      await api.put(`/devices/${service.device_id}/services/monitoring`, {
        service_ids: [service.id], monitored, ...form,
      });
      await onSaved?.(); onClose();
    } catch (e) { setError(getApiErrorMessage(e)); }
    finally { setBusy(''); }
  };

  return <div className="modal-overlay" role="presentation" onMouseDown={e=>e.target===e.currentTarget&&onClose()}>
    <section className="glass-card service-config-modal" role="dialog" aria-modal="true" aria-labelledby="service-config-title">
      <div className="modal-header"><div><h3 id="service-config-title">Configure monitored service</h3><p>{service.display_name} · {deviceName || service.device_name}</p></div><button className="icon-button" onClick={onClose} aria-label="Close"><X size={18}/></button></div>
      {error&&<div className="notice error">{error}</div>}
      <div className="service-config-identity"><div><span>Service name</span><strong>{service.name}</strong></div><div><span>Observed state</span><strong>{service.state}</strong></div><div><span>Start mode</span><strong>{service.start_mode}</strong></div></div>
      <div className="service-policy service-policy-modal">
        <Field label="Expected state"><select className="form-select" value={form.expected_state} onChange={e=>update('expected_state',e.target.value)}><option value="running">Running</option><option value="stopped">Stopped</option></select></Field>
        <Field label="Interval (seconds)"><input className="form-input" type="number" min="30" value={form.check_interval} onChange={e=>update('check_interval',Number(e.target.value))}/></Field>
        <Field label="Failures before alert"><input className="form-input" type="number" min="1" value={form.failure_threshold} onChange={e=>update('failure_threshold',Number(e.target.value))}/></Field>
        <Field label="Successes before recovery"><input className="form-input" type="number" min="1" value={form.recovery_threshold} onChange={e=>update('recovery_threshold',Number(e.target.value))}/></Field>
        <Field label="Severity"><select className="form-select" value={form.severity} onChange={e=>update('severity',e.target.value)}><option>INFORMATION</option><option>WARNING</option><option>CRITICAL</option></select></Field>
      </div>
      <label className="check-line"><input type="checkbox" checked={form.notifications_enabled} onChange={e=>update('notifications_enabled',e.target.checked)}/>Notifications enabled for this service</label>
      <div className="modal-actions"><button className="btn btn-danger" disabled={!!busy} onClick={()=>submit(false)}>{busy==='stop'?'Stopping…':'Stop Monitoring'}</button><button className="btn btn-primary" disabled={!!busy} onClick={()=>submit(true)}><Save size={15}/>{busy==='save'?'Saving…':'Save Service'}</button></div>
    </section>
  </div>;
}

function Field({label,children}) { return <div className="form-group"><label className="form-label">{label}</label>{children}</div>; }
