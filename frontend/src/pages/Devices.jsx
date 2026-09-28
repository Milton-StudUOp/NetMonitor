import React, { useEffect, useState } from 'react';
import { Plus, Trash2, Edit3, Server, Search, Radio, CheckCircle, AlertCircle, RefreshCw, Activity } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import api from '../api/client';
import Modal from '../components/Modal';
import ConfirmModal from '../components/ConfirmModal';
import { getApiErrorMessage } from '../utils/errors';
import DeviceIcon from '../components/DeviceIcon';
import Pagination from '../components/Pagination';

const PAGE_SIZE = 25;

export default function Devices({ user }) {
  const canManageDevices = user?.role !== 'VIEWER';
  const navigate = useNavigate();
  const [devices, setDevices] = useState([]);
  const [links, setLinks] = useState([]);
  const [redundancyGroups, setRedundancyGroups] = useState([]);
  const [icons, setIcons] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [typeFilter, setTypeFilter] = useState('ALL');
  const [page, setPage] = useState(1);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [pingResult, setPingResult] = useState({});
  const [pingingId, setPingingId] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState('');

  const initialFormState = {
    name: '',
    ip_address: '',
    gateway_ip_address: '',
    gateway_device_id: '',
    primary_link_id: '',
    device_type: 'SWITCH',
    location: '',
    network: '',
    manufacturer: '',
    model: '',
    function: '',
    group_name: '',
    icon_id: '',
    monitoring_method: 'ICMP',
    is_critical: true,
    monitoring_interval: 30,
    connectivity_mode: 'SINGLE',
    redundancy_group_id: '',
    link_type: 'OTHER',
    link_monitoring_interval: 5,
    links_are_critical: true,
  };

  const [formData, setFormData] = useState(initialFormState);

  const fetchDevices = async () => {
    try {
      const res = await api.get('/devices');
      setDevices(res.data);
    } catch (err) {
      console.error('Failed to fetch devices:', err);
    }
  };

  const fetchLinks = async () => {
    try {
      const res = await api.get('/links');
      setLinks(res.data);
    } catch (err) {
      console.error('Failed to fetch links:', err);
    }
  };

  useEffect(() => {
    fetchDevices();
    fetchLinks();
    api.get('/platform/icons').then((res) => setIcons(res.data)).catch(() => {});
    api.get('/redundancy-groups').then((res) => setRedundancyGroups(res.data)).catch(() => setRedundancyGroups([]));
  }, []);

  const handleOpenAdd = () => {
    setEditingId(null);
    setFormData(initialFormState);
    setIsModalOpen(true);
  };

  const handleOpenEdit = (dev) => {
    const explicitPrimaryLink = links.find((link) => link.id === dev.primary_link_id);
    const discoveredPrimaryLinks = links.filter((link) => link.destination_device_id === dev.id && link.priority === 'PRIMARY');
    const primaryLink = explicitPrimaryLink || (discoveredPrimaryLinks.length === 1 ? discoveredPrimaryLinks[0] : null);
    const secondaryLinks = links.filter((link) => link.destination_device_id === dev.id && link.priority === 'SECONDARY');
    const secondaryLink = secondaryLinks.length === 1 ? secondaryLinks[0] : null;
    const matchingGroup = primaryLink && secondaryLink
      ? redundancyGroups.find((group) => group.redundancy_type === 'DEVICE'
        && group.primary_device_id === primaryLink.source_device_id
        && group.secondary_device_id === secondaryLink.source_device_id)
      : null;
    setEditingId(dev.id);
    setFormData({
      name: dev.name || '',
      ip_address: dev.ip_address || '',
      gateway_ip_address: dev.gateway_ip_address || '',
      gateway_device_id: dev.gateway_device_id || '',
      primary_link_id: dev.primary_link_id || '',
      device_type: dev.device_type || 'SWITCH',
      location: dev.location || '',
      network: dev.network || '',
      manufacturer: dev.manufacturer || '',
      model: dev.model || '',
      function: dev.function || '',
      group_name: dev.group_name || '',
      icon_id: dev.icon_id || '',
      monitoring_method: dev.monitoring_method || 'ICMP',
      is_critical: dev.is_critical ?? true,
      monitoring_interval: dev.monitoring_interval || 30,
      connectivity_mode: matchingGroup ? 'REDUNDANT' : 'SINGLE',
      redundancy_group_id: matchingGroup?.id || '',
      link_type: primaryLink?.link_type || secondaryLink?.link_type || 'OTHER',
      link_monitoring_interval: primaryLink?.monitoring_interval || secondaryLink?.monitoring_interval || 5,
      links_are_critical: primaryLink?.is_critical ?? secondaryLink?.is_critical ?? true,
    });
    setIsModalOpen(true);
  };

  // The groups and links are loaded independently. If an operator opens Edit
  // before both requests finish, reconcile the legacy relationship as soon as
  // the remaining inventory arrives instead of showing a false SINGLE state.
  useEffect(() => {
    if (!isModalOpen || !editingId) return;
    const dev = devices.find((item) => item.id === editingId);
    if (!dev) return;
    const explicitPrimary = links.find((link) => link.id === dev.primary_link_id);
    const primaryCandidates = links.filter((link) => link.destination_device_id === dev.id && link.priority === 'PRIMARY');
    const secondaryCandidates = links.filter((link) => link.destination_device_id === dev.id && link.priority === 'SECONDARY');
    const primary = explicitPrimary || (primaryCandidates.length === 1 ? primaryCandidates[0] : null);
    const secondary = secondaryCandidates.length === 1 ? secondaryCandidates[0] : null;
    const group = primary && secondary ? redundancyGroups.find((item) => item.redundancy_type === 'DEVICE'
      && item.primary_device_id === primary.source_device_id
      && item.secondary_device_id === secondary.source_device_id) : null;
    if (!group) return;
    setFormData((current) => current.connectivity_mode === 'REDUNDANT' ? current : ({
      ...current,
      connectivity_mode: 'REDUNDANT',
      redundancy_group_id: group.id,
      link_type: primary.link_type || secondary.link_type || 'OTHER',
      link_monitoring_interval: primary.monitoring_interval || secondary.monitoring_interval || 5,
      links_are_critical: primary.is_critical ?? secondary.is_critical ?? true,
    }));
  }, [isModalOpen, editingId, devices, links, redundancyGroups]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    const {
      primary_link_id, connectivity_mode, redundancy_group_id, link_type,
      link_monitoring_interval, links_are_critical, ...deviceFields
    } = formData;
    const payload = {
      ...deviceFields,
      gateway_ip_address: formData.gateway_ip_address || null,
      gateway_device_id: formData.gateway_device_id ? Number(formData.gateway_device_id) : null,
      icon_id: formData.icon_id ? Number(formData.icon_id) : null,
      ...(editingId && {
        primary_link_id: primary_link_id ? Number(primary_link_id) : null,
      }),
    };
    setSaving(true);
    setFeedback('');
    try {
      if (editingId && connectivity_mode === 'REDUNDANT') {
        await api.put(`/devices/with-redundant-links/${editingId}`, {
          device: payload,
          redundancy_group_id: Number(redundancy_group_id),
          link_type,
          link_monitoring_interval: Number(link_monitoring_interval),
          links_are_critical,
        });
      } else if (editingId) {
        await api.put(`/devices/${editingId}`, payload);
      } else if (connectivity_mode === 'REDUNDANT') {
        await api.post('/devices/with-redundant-links', {
          device: payload,
          redundancy_group_id: Number(redundancy_group_id),
          link_type,
          link_monitoring_interval: Number(link_monitoring_interval),
          links_are_critical,
        });
      } else {
        await api.post('/devices', payload);
      }
      setIsModalOpen(false);
      await Promise.all([fetchDevices(), fetchLinks()]);
      setFeedback(connectivity_mode === 'REDUNDANT' && !editingId
        ? 'Device registered with primary and secondary links.'
        : `Device ${editingId ? 'updated' : 'registered'} successfully.`);
    } catch (err) {
      alert('Error saving device: ' + getApiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const executeDelete = async () => {
    if (!deleteTarget) return;
    try {
      await api.delete(`/devices/${deleteTarget.id}`);
      fetchDevices();
    } catch (err) {
      alert('Error deleting device: ' + getApiErrorMessage(err));
    } finally {
      setDeleteTarget(null);
    }
  };

  const handleTestPing = async (dev) => {
    if (!dev.ip_address) return;
    setPingingId(dev.id);
    try {
      const res = await api.get(`/devices/${dev.id}/status`);
      setPingResult(prev => ({
        ...prev,
        [dev.id]: {
          is_up: res.data.status === 'ONLINE',
          latency: res.data.last_latency_ms != null ? `${res.data.last_latency_ms}ms` : 'OK',
        }
      }));
    } catch (err) {
      setPingResult(prev => ({
        ...prev,
        [dev.id]: { is_up: false, latency: null }
      }));
    } finally {
      setPingingId(null);
    }
  };

  const filteredDevices = devices.filter((d) => {
    const matchesSearch =
      d.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (d.ip_address && d.ip_address.includes(searchTerm)) ||
      (d.gateway_ip_address && d.gateway_ip_address.includes(searchTerm)) ||
      (d.location && d.location.toLowerCase().includes(searchTerm.toLowerCase()));
    const matchesType = typeFilter === 'ALL' || d.device_type === typeFilter;
    return matchesSearch && matchesType;
  });
  const visibleDevices = filteredDevices.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const deviceRedundancyGroups = redundancyGroups.filter((group) => group.redundancy_type === 'DEVICE' && group.primary_device && group.secondary_device);
  const selectedRedundancyGroup = deviceRedundancyGroups.find((group) => String(group.id) === String(formData.redundancy_group_id));
  const editingHasSecondaryLink = Boolean(editingId && links.some((link) => link.destination_device_id === editingId && link.priority === 'SECONDARY'));
  const primaryLinkFor = (device) => links.find((link) => link.id === device.primary_link_id)
    || links.find((link) => link.destination_device_id === device.id && link.priority === 'PRIMARY');
  const secondaryLinkFor = (device) => links.find((link) => link.destination_device_id === device.id && link.priority === 'SECONDARY');
  useEffect(() => { setPage(current => Math.min(current, Math.max(1, Math.ceil(filteredDevices.length / PAGE_SIZE)))); }, [filteredDevices.length]);

  return (
    <div className="data-page">
      {feedback && <div className="notice success" role="status">{feedback}</div>}
      {/* Action Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h2 style={{ fontSize: '1.35rem', color: 'var(--text-main)', fontWeight: 700, letterSpacing: '-0.01em' }}>
            Network Device Management
          </h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginTop: '2px' }}>
            Register switches, media converters, routers, and radio links monitored in real time.
          </p>
        </div>

        {canManageDevices && <button className="btn btn-primary" onClick={handleOpenAdd} style={{ padding: '10px 20px', fontSize: '0.9rem' }}>
          <Plus size={18} /> Add Device
        </button>}
      </div>

      {/* Filter Bar */}
      <div className="glass-card" style={{ padding: '14px 18px', marginBottom: '20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1, minWidth: '260px' }}>
          <Search size={18} color="var(--text-dim)" />
          <input
            type="text"
            className="form-input"
            style={{ width: '100%', border: 'none', background: 'transparent', padding: 0 }}
            placeholder="Search by name, IP, or location..."
            value={searchTerm}
            onChange={(e) => { setSearchTerm(e.target.value); setPage(1); }}
          />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Type:</span>
          <select
            className="form-select"
            style={{ padding: '6px 12px', fontSize: '0.85rem' }}
            value={typeFilter}
            onChange={(e) => { setTypeFilter(e.target.value); setPage(1); }}
          >
            <option value="ALL">All Types</option>
            <option value="SWITCH">Switch</option>
            <option value="MEDIA_CONVERTER">Media Converter</option>
            <option value="ROUTER">Roteador</option>
            <option value="RADIO">Radio Link</option>
            <option value="FIREWALL">Firewall</option>
            <option value="SERVER">Servidor</option>
            <option value="OTHER">Outro</option>
          </select>
        </div>
      </div>

      {/* Table Container */}
      <div className="glass-card data-grid-card">
        {filteredDevices.length === 0 ? (
          <div style={{ padding: '48px 24px', textAlign: 'center', color: 'var(--text-muted)' }}>
            <Server size={44} style={{ marginBottom: '16px', opacity: 0.4 }} />
            <h4 style={{ color: 'var(--text-main)', fontSize: '1rem', marginBottom: '6px' }}>No devices found</h4>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-dim)', maxWidth: '400px', margin: '0 auto' }}>
              {devices.length === 0
                ? canManageDevices ? 'Start by clicking the "+ Add Device" button above to register your first switch or radio.' : 'No devices are currently available.'
                : 'No devices match the applied filters.'}
            </p>
          </div>
        ) : (
          <table className="custom-table">
            <thead>
              <tr>
                <th>Device</th>
                <th>Type</th>
                <th>IP Address</th>
                <th>Location</th>
                <th>Gateway / Link</th>
                <th>Status</th>
                <th>ICMP Diagnostics</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {visibleDevices.map((d) => (
                <tr key={d.id}>
                  <td>
                    <button className="device-name-link" onClick={() => navigate(`/devices/${d.id}?from=devices`)} title="Open device metrics"><DeviceIcon icon={icons.find(i => i.id === d.icon_id)} size={18} />{d.name}</button>
                    {d.model && <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>{d.manufacturer} {d.model}</div>}
                  </td>
                  <td>
                    <span style={{
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      padding: '3px 8px',
                      borderRadius: '6px',
                      background: 'var(--surface-subtle)',
                      border: '1px solid var(--border-color)',
                      color: 'var(--text-main)',
                    }}>
                      {d.device_type}
                    </span>
                  </td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem' }}>{d.ip_address || '—'}</td>
                  <td>{d.location || '—'}</td>
                  <td>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', color: 'var(--text-main)' }}>
                      {d.gateway_ip_address || devices.find((item) => item.id === primaryLinkFor(d)?.source_device_id)?.ip_address || '—'}
                    </div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>
                      Primary: {devices.find((item) => item.id === (d.gateway_device_id || primaryLinkFor(d)?.source_device_id))?.name || 'Not assigned'}
                    </div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>
                      Secondary: {devices.find((item) => item.id === secondaryLinkFor(d)?.source_device_id)?.name || 'Not assigned'}
                    </div>
                  </td>
                  <td>
                    <span className={`badge badge-${d.status?.toLowerCase() || 'unknown'}`}>
                      {d.status}
                    </span>
                  </td>
                  <td>
                    <button
                      className="btn btn-secondary"
                      style={{ padding: '4px 10px', fontSize: '0.75rem', gap: '4px' }}
                      disabled={pingingId === d.id}
                      onClick={() => handleTestPing(d)}
                    >
                      <RefreshCw size={12} className={pingingId === d.id ? 'spin' : ''} />
                      {pingResult[d.id] ? (
                        pingResult[d.id].is_up ? (
                          <span style={{ color: '#10b981' }}>{pingResult[d.id].latency}</span>
                        ) : (
                          <span style={{ color: '#ef4444' }}>No Response</span>
                        )
                      ) : (
                        'Test Ping'
                      )}
                    </button>
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '8px' }}>
                      <button className="btn btn-secondary" style={{ padding: '5px 10px', fontSize: '0.75rem' }} onClick={() => navigate(`/devices/${d.id}?from=devices`)} title="View Metrics"><Activity size={14} /> Metrics</button>
                      {canManageDevices && <button
                        className="btn btn-secondary"
                        style={{ padding: '5px 10px', fontSize: '0.75rem' }}
                        onClick={() => handleOpenEdit(d)}
                        title="Edit Device"
                      >
                        <Edit3 size={14} /> Edit
                      </button>}
                      {canManageDevices && <button
                        className="btn btn-danger"
                        style={{ padding: '5px 10px', fontSize: '0.75rem' }}
                        onClick={() => setDeleteTarget({ id: d.id, name: d.name })}
                        title="Delete Device"
                      >
                        <Trash2 size={14} /> Delete
                      </button>}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Pagination page={page} pageSize={PAGE_SIZE} total={filteredDevices.length} count={visibleDevices.length} onPageChange={setPage}/>

      {/* Professional Modal Form */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title={editingId ? 'Edit Network Device' : 'Register New Device'}
        subtitle="Enter the device's technical information for monitoring integration"
        icon={Server}
        maxWidth="720px"
      >
        <form onSubmit={handleSubmit}>
          {/* Section 1: Identification */}
          <div style={{ marginBottom: '20px' }}>
            <h4 style={{ fontSize: '0.85rem', fontWeight: 600, color: '#3b82f6', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '12px' }}>
              1. Basic Identification
            </h4>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Device Name *</label>
                <input
                  className="form-input"
                  type="text"
                  required
                  placeholder="Ex: SWITCH_OCC_CORE"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Device Type *</label>
                <select
                  className="form-select"
                  value={formData.device_type}
                  onChange={(e) => setFormData({ ...formData, device_type: e.target.value })}
                >
                  <option value="SWITCH">Layer 2/3 Switch</option>
                  <option value="MEDIA_CONVERTER">Media Converter (Optical converter)</option>
                  <option value="ROUTER">Roteador Core/Borda</option>
                  <option value="RADIO">Radio Link (Microwaves)</option>
                  <option value="FIREWALL">Firewall / Security Appliance</option>
                  <option value="SERVER">Servidor / Host</option>
                  <option value="OTHER">Outro Dispositivo</option>
                </select>
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Device icon</label>
                <select className="form-select" value={formData.icon_id} onChange={(e) => setFormData({ ...formData, icon_id: e.target.value })}>
                  <option value="">Automatic by type</option>
                  {icons.map((icon) => <option key={icon.id} value={icon.id}>{icon.category} — {icon.name}</option>)}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Group</label>
                <input className="form-input" value={formData.group_name} onChange={(e) => setFormData({ ...formData, group_name: e.target.value })} placeholder="Ex: DMZ, Core, Filial Norte" />
              </div>
            </div>
          </div>

          {/* Section 2: Network & Location */}
          <div style={{ marginBottom: '20px' }}>
            <h4 style={{ fontSize: '0.85rem', fontWeight: 600, color: '#3b82f6', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '12px' }}>
              2. Addressing and Location
            </h4>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label">IP Address (Management)</label>
                <input
                  className="form-input"
                  type="text"
                  placeholder="Ex: 10.10.0.1"
                  value={formData.ip_address}
                  onChange={(e) => setFormData({ ...formData, ip_address: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Subnet (CIDR)</label>
                <input
                  className="form-input"
                  type="text"
                  placeholder="Ex: 10.10.0.0/24"
                  value={formData.network}
                  onChange={(e) => setFormData({ ...formData, network: e.target.value })}
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">Connectivity</label>
              <select className="form-select" value={formData.connectivity_mode} onChange={(e) => setFormData({ ...formData, connectivity_mode: e.target.value, gateway_device_id: '' })}>
                <option value="SINGLE" disabled={editingHasSecondaryLink}>Single gateway / primary link</option>
                <option value="REDUNDANT">Primary and secondary links</option>
              </select>
              <small className="field-hint">Redundant registration creates the device and both links in one atomic operation.</small>
            </div>

            {formData.connectivity_mode === 'REDUNDANT' && <div className="device-redundancy-config">
              <div className="form-group">
                <label className="form-label">Upstream redundancy group *</label>
                <select className="form-select" required value={formData.redundancy_group_id} onChange={(e) => setFormData({ ...formData, redundancy_group_id: e.target.value })}>
                  <option value="">Select a device redundancy group</option>
                  {deviceRedundancyGroups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
                </select>
                {!deviceRedundancyGroups.length && <small className="field-hint">Create a DEVICE redundancy group first, with primary and secondary upstream devices.</small>}
              </div>
              {selectedRedundancyGroup && <div className="redundancy-path-preview">
                <div><span>Primary path</span><strong>{selectedRedundancyGroup.primary_device.name}</strong><small>{selectedRedundancyGroup.primary_device.ip_address || 'No IP address'}</small></div>
                <div><span>Secondary path</span><strong>{selectedRedundancyGroup.secondary_device.name}</strong><small>{selectedRedundancyGroup.secondary_device.ip_address || 'No IP address'}</small></div>
              </div>}
              <div className="form-row">
                <div className="form-group"><label className="form-label">Link type</label><select className="form-select" value={formData.link_type} onChange={(e) => setFormData({ ...formData, link_type: e.target.value })}><option value="OTHER">Other</option><option value="FIBER">Fiber</option><option value="ETHERNET">Ethernet</option><option value="RADIO">Radio</option><option value="VPN">VPN</option></select></div>
                <div className="form-group"><label className="form-label">Link check interval (seconds)</label><input className="form-input" type="number" min="1" required value={formData.link_monitoring_interval} onChange={(e) => setFormData({ ...formData, link_monitoring_interval: e.target.value })}/></div>
              </div>
              <label className="check-line"><input type="checkbox" checked={formData.links_are_critical} onChange={(e) => setFormData({ ...formData, links_are_critical: e.target.checked })}/>Treat both connectivity paths as critical</label>
            </div>}

            {formData.connectivity_mode !== 'REDUNDANT' && <div className="form-row">
              <div className="form-group">
                <label className="form-label">Gateway IP</label>
                <input
                  className="form-input"
                  type="text"
                  placeholder="Ex: 10.10.0.254"
                  value={formData.gateway_ip_address}
                  onChange={(e) => setFormData({ ...formData, gateway_ip_address: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Gateway Device</label>
                <select
                  className="form-select"
                  value={formData.gateway_device_id}
                  onChange={(e) => setFormData({ ...formData, gateway_device_id: e.target.value })}
                >
                  <option value="">Not assigned</option>
                  {devices
                    .filter((d) => d.id !== editingId)
                    .map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name} {d.ip_address ? `(${d.ip_address})` : ''}
                      </option>
                    ))}
                </select>
              </div>
            </div>}

            {formData.connectivity_mode !== 'REDUNDANT' && <div className="form-group">
              <label className="form-label">Primary Link</label>
              <select
                className="form-select"
                value={formData.primary_link_id}
                disabled={!editingId}
                onChange={(e) => setFormData({ ...formData, primary_link_id: e.target.value })}
              >
                <option value="">{editingId ? 'Not assigned' : 'Available after registering the device'}</option>
                {links
                  .filter((l) => editingId && (l.source_device_id === editingId || l.destination_device_id === editingId))
                  .map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.name} ({l.priority})
                    </option>
                  ))}
              </select>
            </div>}

            <div className="form-group">
              <label className="form-label">Physical Location / Rack</label>
              <input
                className="form-input"
                type="text"
                placeholder="Ex: Sala OCC - Rack 02 - U14"
                value={formData.location}
                onChange={(e) => setFormData({ ...formData, location: e.target.value })}
              />
            </div>
          </div>

          {/* Section 3: Hardware Details */}
          <div style={{ marginBottom: '24px' }}>
            <h4 style={{ fontSize: '0.85rem', fontWeight: 600, color: '#3b82f6', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '12px' }}>
              3. Hardware & Monitoring Details
            </h4>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Manufacturer</label>
                <input
                  className="form-input"
                  type="text"
                  placeholder="Ex: Cisco, TP-Link, Mikrotik"
                  value={formData.manufacturer}
                  onChange={(e) => setFormData({ ...formData, manufacturer: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Model</label>
                <input
                  className="form-input"
                  type="text"
                  placeholder="Ex: Catalyst 9300 / MC220L"
                  value={formData.model}
                  onChange={(e) => setFormData({ ...formData, model: e.target.value })}
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">Role / Notes</label>
              <input
                className="form-input"
                type="text"
                placeholder="E.g.: Fiber-link concentrator for the northern segment"
                value={formData.function}
                onChange={(e) => setFormData({ ...formData, function: e.target.value })}
              />
            </div>
          </div>

          {/* Buttons Footer */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '12px', borderTop: '1px solid var(--border-color)', paddingTop: '16px' }}>
            <button type="button" className="btn btn-secondary" onClick={() => setIsModalOpen(false)}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              {saving ? 'Saving…' : editingId ? 'Update Device' : formData.connectivity_mode === 'REDUNDANT' ? 'Register Device & Both Links' : 'Register Device'}
            </button>
          </div>
        </form>
      </Modal>

      {/* In-App Delete Confirmation Modal */}
      <ConfirmModal
        isOpen={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        onConfirm={executeDelete}
        title="Delete Device"
        message={
          deleteTarget
            ? `Are you sure you want to delete the device "${deleteTarget.name}"? This will also remove its associated links, history, and redundancy settings.`
            : ''
        }
      />
    </div>
  );
}
