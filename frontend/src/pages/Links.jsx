import React, { useEffect, useState } from 'react';
import { Plus, Trash2, Edit3, Network, Search, ArrowRight } from 'lucide-react';
import api from '../api/client';
import Modal from '../components/Modal';
import ConfirmModal from '../components/ConfirmModal';
import { getApiErrorMessage } from '../utils/errors';

export default function Links() {
  const [links, setLinks] = useState([]);
  const [devices, setDevices] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);

  const initialFormState = {
    name: '',
    description: '',
    source_device_id: '',
    destination_device_id: '',
    link_type: 'FIBER',
    priority: 'PRIMARY',
    is_critical: true,
    monitoring_interval: 5,
  };

  const [formData, setFormData] = useState(initialFormState);

  const fetchData = async () => {
    try {
      const [linkRes, devRes] = await Promise.all([
        api.get('/links'),
        api.get('/devices'),
      ]);
      setLinks(linkRes.data);
      setDevices(devRes.data);
    } catch (err) {
      console.error('Failed to fetch links or devices:', err);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleOpenAdd = () => {
    setEditingId(null);
    setFormData({
      ...initialFormState,
      source_device_id: devices.length > 0 ? devices[0].id : '',
      destination_device_id: devices.length > 1 ? devices[1].id : '',
    });
    setIsModalOpen(true);
  };

  const handleOpenEdit = (link) => {
    setEditingId(link.id);
    setFormData({
      name: link.name || '',
      description: link.description || '',
      source_device_id: link.source_device_id || '',
      destination_device_id: link.destination_device_id || '',
      link_type: link.link_type || 'FIBER',
      priority: link.priority || 'PRIMARY',
      is_critical: link.is_critical ?? true,
      monitoring_interval: link.monitoring_interval || 5,
    });
    setIsModalOpen(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.source_device_id || !formData.destination_device_id) {
      alert('Select the source and destination devices.');
      return;
    }

    try {
      const payload = {
        ...formData,
        source_device_id: Number(formData.source_device_id),
        destination_device_id: Number(formData.destination_device_id),
        monitoring_interval: Number(formData.monitoring_interval),
      };

      if (editingId) {
        await api.put(`/links/${editingId}`, payload);
      } else {
        await api.post('/links', payload);
      }

      setIsModalOpen(false);
      fetchData();
    } catch (err) {
      alert('Error saving link:\n' + getApiErrorMessage(err));
    }
  };

  const executeDelete = async () => {
    if (!deleteTarget) return;
    try {
      await api.delete(`/links/${deleteTarget.id}`);
      fetchData();
    } catch (err) {
      alert('Error deleting link:\n' + getApiErrorMessage(err));
    } finally {
      setDeleteTarget(null);
    }
  };

  const getDeviceName = (id) => {
    const dev = devices.find((d) => d.id === id);
    return dev ? `${dev.name} (${dev.ip_address || 'Sem IP'})` : `ID #${id}`;
  };

  const filteredLinks = links.filter((link) =>
    link.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    getDeviceName(link.source_device_id).toLowerCase().includes(searchTerm.toLowerCase()) ||
    getDeviceName(link.destination_device_id).toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h2 style={{ fontSize: '1.35rem', color: '#fff', fontWeight: 700, letterSpacing: '-0.01em' }}>
            Communication Links
          </h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginTop: '2px' }}>
            Configure physical and logical channels between monitored devices.
          </p>
        </div>

        <button className="btn btn-primary" onClick={handleOpenAdd} style={{ padding: '10px 20px', fontSize: '0.9rem' }}>
          <Plus size={18} /> Create New Link
        </button>
      </div>

      <div className="glass-card" style={{ padding: '14px 18px', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '12px' }}>
        <Search size={18} color="var(--text-dim)" />
        <input
          type="text"
          className="form-input"
          style={{ width: '100%', border: 'none', background: 'transparent', padding: 0 }}
          placeholder="Search links by name or endpoint devices..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />
      </div>

      <div className="glass-card" style={{ overflow: 'hidden' }}>
        {filteredLinks.length === 0 ? (
          <div style={{ padding: '48px 24px', textAlign: 'center', color: 'var(--text-muted)' }}>
            <Network size={44} style={{ marginBottom: '16px', opacity: 0.4 }} />
            <h4 style={{ color: '#fff', fontSize: '1rem', marginBottom: '6px' }}>No links registered</h4>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-dim)', maxWidth: '440px', margin: '0 auto' }}>
              Register links between devices to build the topology map.
            </p>
          </div>
        ) : (
          <table className="custom-table">
            <thead>
              <tr>
                <th>Link Name</th>
                <th>Meio</th>
                <th>Source and Destination</th>
                <th>Priority</th>
                <th>Interval</th>
                <th>Status</th>
                <th style={{ textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredLinks.map((link) => (
                <tr key={link.id}>
                  <td>
                    <div style={{ fontWeight: 600, color: '#fff' }}>{link.name}</div>
                    {link.description && <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>{link.description}</div>}
                  </td>
                  <td>
                    <span style={{
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      padding: '3px 8px',
                      borderRadius: '6px',
                      background: 'rgba(59, 130, 246, 0.1)',
                      border: '1px solid rgba(59, 130, 246, 0.3)',
                      color: '#3b82f6',
                    }}>
                      {link.link_type}
                    </span>
                  </td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.85rem', flexWrap: 'wrap' }}>
                      <span style={{ color: 'var(--text-main)', fontWeight: 500 }}>{getDeviceName(link.source_device_id)}</span>
                      <ArrowRight size={14} color="var(--text-dim)" />
                      <span style={{ color: 'var(--text-main)', fontWeight: 500 }}>{getDeviceName(link.destination_device_id)}</span>
                    </div>
                  </td>
                  <td style={{ fontSize: '0.85rem' }}>{link.priority}</td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.85rem' }}>{link.monitoring_interval}s</td>
                  <td>
                    <span className={`badge badge-${link.status?.toLowerCase() || 'unknown'}`}>
                      {link.status}
                    </span>
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '8px' }}>
                      <button className="btn btn-secondary" style={{ padding: '5px 10px', fontSize: '0.75rem' }} onClick={() => handleOpenEdit(link)}>
                        <Edit3 size={14} /> Edit
                      </button>
                      <button className="btn btn-danger" style={{ padding: '5px 10px', fontSize: '0.75rem' }} onClick={() => setDeleteTarget({ id: link.id, name: link.name })}>
                        <Trash2 size={14} /> Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title={editingId ? 'Edit Link' : 'Register New Link'}
        subtitle="Connect two monitored devices to track availability"
        icon={Network}
        maxWidth="720px"
      >
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: '20px' }}>
            <h4 style={{ fontSize: '0.85rem', fontWeight: 600, color: '#3b82f6', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '12px' }}>
              1. Link Identification
            </h4>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Link Name *</label>
                <input
                  className="form-input"
                  type="text"
                  required
                  placeholder="Ex: LINK_OCC_TO_CCP_FIBER"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Media Type *</label>
                <select
                  className="form-select"
                  required
                  value={formData.link_type}
                  onChange={(e) => setFormData({ ...formData, link_type: e.target.value })}
                >
                  <option value="FIBER">Fiber Optic</option>
                  <option value="ETHERNET">Ethernet / Copper Cable</option>
                  <option value="RADIO">Radio Link</option>
                  <option value="VPN">VPN / Virtual Tunnel</option>
                  <option value="OTHER">Outro</option>
                </select>
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">Description</label>
              <input
                className="form-input"
                type="text"
                placeholder="E.g.: Primary fiber between OCC and CCP"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              />
            </div>
          </div>

          <div style={{ marginBottom: '20px' }}>
            <h4 style={{ fontSize: '0.85rem', fontWeight: 600, color: '#3b82f6', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '12px' }}>
              2. Endpoint Devices
            </h4>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Source Device *</label>
                <select
                  className="form-select"
                  required
                  value={formData.source_device_id}
                  onChange={(e) => setFormData({ ...formData, source_device_id: e.target.value })}
                >
                  <option value="">Select the source...</option>
                  {devices.map((device) => (
                    <option key={device.id} value={device.id}>
                      {device.name} ({device.ip_address || 'Sem IP'})
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Destination Device *</label>
                <select
                  className="form-select"
                  required
                  value={formData.destination_device_id}
                  onChange={(e) => setFormData({ ...formData, destination_device_id: e.target.value })}
                >
                  <option value="">Select the destination...</option>
                  {devices.map((device) => (
                    <option key={device.id} value={device.id}>
                      {device.name} ({device.ip_address || 'Sem IP'})
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          <div style={{ marginBottom: '24px' }}>
            <h4 style={{ fontSize: '0.85rem', fontWeight: 600, color: '#3b82f6', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '12px' }}>
              3. Priority and Monitoring
            </h4>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Priority *</label>
                <select
                  className="form-select"
                  required
                  value={formData.priority}
                  onChange={(e) => setFormData({ ...formData, priority: e.target.value })}
                >
                  <option value="PRIMARY">Primary</option>
                  <option value="SECONDARY">Secondary</option>
                </select>
              </div>

              <div className="form-group">
                <label className="form-label">Monitoring Interval (s)</label>
                <input
                  className="form-input"
                  type="number"
                  min="1"
                  value={formData.monitoring_interval}
                  onChange={(e) => setFormData({ ...formData, monitoring_interval: e.target.value })}
                />
              </div>
            </div>

            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              <input
                type="checkbox"
                checked={formData.is_critical}
                onChange={(e) => setFormData({ ...formData, is_critical: e.target.checked })}
              />
              Critical link for operations
            </label>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '12px', borderTop: '1px solid var(--border-color)', paddingTop: '16px' }}>
            <button type="button" className="btn btn-secondary" onClick={() => setIsModalOpen(false)}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary">
              {editingId ? 'Update Link' : 'Register Link'}
            </button>
          </div>
        </form>
      </Modal>

      <ConfirmModal
        isOpen={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        onConfirm={executeDelete}
        title="Delete Link"
        message={deleteTarget ? `Are you sure you want to delete the link "${deleteTarget.name}"?` : ''}
      />
    </div>
  );
}
