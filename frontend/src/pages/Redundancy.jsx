import React, { useEffect, useState } from 'react';
import { Plus, Trash2, Edit3, GitFork, Search } from 'lucide-react';
import api from '../api/client';
import Modal from '../components/Modal';
import ConfirmModal from '../components/ConfirmModal';
import { getApiErrorMessage } from '../utils/errors';
import Pagination from '../components/Pagination';

const PAGE_SIZE = 25;

const emptyForm = {
  name: '',
  description: '',
  redundancy_type: 'DEVICE',
  primary_link_id: '',
  secondary_link_id: '',
  primary_device_id: '',
  secondary_device_id: '',
  service_check_type: 'NONE',
  service_check_target: '',
  service_check_port: '',
};

export default function Redundancy({ user }) {
  const canManageRedundancy = user?.role === 'ADMINISTRATOR';
  const [groups, setGroups] = useState([]);
  const [links, setLinks] = useState([]);
  const [devices, setDevices] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [page, setPage] = useState(1);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [formData, setFormData] = useState(emptyForm);

  const fetchData = async () => {
    try {
      const [groupRes, linkRes, deviceRes] = await Promise.all([
        api.get('/redundancy-groups'),
        api.get('/links'),
        api.get('/devices'),
      ]);
      setGroups(groupRes.data);
      setLinks(linkRes.data);
      setDevices(deviceRes.data);
    } catch (err) {
      console.error('Failed to load redundancy:', err);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const openAdd = () => {
    setEditingId(null);
    setFormData({
      ...emptyForm,
      primary_device_id: devices[0]?.id || '',
      secondary_device_id: devices[1]?.id || '',
    });
    setIsModalOpen(true);
  };

  const openEdit = (group) => {
    setEditingId(group.id);
    setFormData({
      ...emptyForm,
      name: group.name || '',
      description: group.description || '',
      redundancy_type: group.redundancy_type || 'LINK',
      primary_link_id: group.primary_link_id || '',
      secondary_link_id: group.secondary_link_id || '',
      primary_device_id: group.primary_device_id || '',
      secondary_device_id: group.secondary_device_id || '',
      service_check_type: group.service_check_type || 'NONE',
      service_check_target: group.service_check_target || '',
      service_check_port: group.service_check_port || '',
    });
    setIsModalOpen(true);
  };

  const handleTypeChange = (redundancyType) => {
    setFormData((current) => ({
      ...current,
      redundancy_type: redundancyType,
      primary_link_id: redundancyType === 'LINK' ? (current.primary_link_id || links[0]?.id || '') : '',
      secondary_link_id: redundancyType === 'LINK' ? (current.secondary_link_id || links[1]?.id || '') : '',
      primary_device_id: redundancyType === 'DEVICE' ? (current.primary_device_id || devices[0]?.id || '') : '',
      secondary_device_id: redundancyType === 'DEVICE' ? (current.secondary_device_id || devices[1]?.id || '') : '',
    }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    const isDeviceGroup = formData.redundancy_type === 'DEVICE';
    const primaryId = isDeviceGroup ? formData.primary_device_id : formData.primary_link_id;
    const secondaryId = isDeviceGroup ? formData.secondary_device_id : formData.secondary_link_id;
    if (!primaryId || !secondaryId) {
      alert(`Select both redundant ${isDeviceGroup ? 'devices' : 'links'}.`);
      return;
    }
    if (String(primaryId) === String(secondaryId)) {
      alert('The primary and secondary units must be different.');
      return;
    }

    const payload = {
      name: formData.name,
      description: formData.description || null,
      redundancy_type: formData.redundancy_type,
      primary_link_id: !isDeviceGroup ? Number(formData.primary_link_id) : null,
      secondary_link_id: !isDeviceGroup ? Number(formData.secondary_link_id) : null,
      primary_device_id: isDeviceGroup ? Number(formData.primary_device_id) : null,
      secondary_device_id: isDeviceGroup ? Number(formData.secondary_device_id) : null,
      service_check_type: formData.service_check_type,
      service_check_target: formData.service_check_target || null,
      service_check_port: formData.service_check_port ? Number(formData.service_check_port) : null,
    };

    try {
      if (editingId) {
        await api.put(`/redundancy-groups/${editingId}`, payload);
      } else {
        await api.post('/redundancy-groups', payload);
      }
      setIsModalOpen(false);
      await fetchData();
    } catch (err) {
      alert(`Error saving redundancy group:\n${getApiErrorMessage(err)}`);
    }
  };

  const executeDelete = async () => {
    if (!deleteTarget) return;
    try {
      await api.delete(`/redundancy-groups/${deleteTarget.id}`);
      await fetchData();
    } catch (err) {
      alert(`Error deleting redundancy group:\n${getApiErrorMessage(err)}`);
    } finally {
      setDeleteTarget(null);
    }
  };

  const deviceName = (id) => devices.find((item) => item.id === id)?.name || `Device #${id}`;
  const linkName = (id) => links.find((item) => item.id === id)?.name || `Link #${id}`;
  const targetName = (group, side) => group.redundancy_type === 'DEVICE'
    ? deviceName(group[`${side}_device_id`])
    : linkName(group[`${side}_link_id`]);
  const filteredGroups = groups.filter((group) =>
    group.name.toLowerCase().includes(searchTerm.toLowerCase())
    || group.description?.toLowerCase().includes(searchTerm.toLowerCase()));
  const visibleGroups = filteredGroups.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  useEffect(() => { setPage(current => Math.min(current, Math.max(1, Math.ceil(filteredGroups.length / PAGE_SIZE)))); }, [filteredGroups.length]);

  const targetSelect = (side, label) => {
    const isDeviceGroup = formData.redundancy_type === 'DEVICE';
    const field = `${side}_${isDeviceGroup ? 'device' : 'link'}_id`;
    const options = isDeviceGroup ? devices : links;
    return (
      <div className="form-group">
        <label className="form-label">{label} *</label>
        <select
          className="form-select"
          required
          value={formData[field]}
          onChange={(event) => setFormData({ ...formData, [field]: event.target.value })}
        >
          <option value="">Select...</option>
          {options.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name} {isDeviceGroup ? `(${item.ip_address || 'sem IP'})` : `(${item.status})`}
            </option>
          ))}
        </select>
      </div>
    );
  };

  return (
    <div className="data-page">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px', gap: '16px', flexWrap: 'wrap' }}>
        <div>
          <h2 style={{ fontSize: '1.35rem', color: '#fff', fontWeight: 700 }}>Redundancy Groups</h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginTop: '2px' }}>
            Protect services with redundant devices or alternate link paths.
          </p>
        </div>
        {canManageRedundancy && <button className="btn btn-primary" onClick={openAdd} style={{ padding: '10px 20px' }}>
          <Plus size={18} /> Create Group
        </button>}
      </div>

      <div className="glass-card" style={{ padding: '14px 18px', marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '12px' }}>
        <Search size={18} color="var(--text-dim)" />
        <input className="form-input" style={{ width: '100%', border: 'none', background: 'transparent', padding: 0 }} placeholder="Search groups..." value={searchTerm} onChange={(event) => { setSearchTerm(event.target.value); setPage(1); }} />
      </div>

      <div className="glass-card data-grid-card">
        {filteredGroups.length === 0 ? (
          <div style={{ padding: '48px 24px', textAlign: 'center', color: 'var(--text-muted)' }}>
            <GitFork size={44} style={{ marginBottom: '16px', opacity: 0.4 }} />
            <h4 style={{ color: '#fff', marginBottom: '6px' }}>No groups registered</h4>
            <p>Create redundancy between two devices, even if they do not have links yet.</p>
          </div>
        ) : (
          <table className="custom-table">
            <thead><tr><th>Group</th><th>Type</th><th>Primary</th><th>Secondary</th><th>Service</th><th>Status</th>{canManageRedundancy&&<th style={{ textAlign: 'right' }}>Actions</th>}</tr></thead>
            <tbody>{visibleGroups.map((group) => (
              <tr key={group.id}>
                <td><div style={{ fontWeight: 600, color: '#fff' }}>{group.name}</div>{group.description && <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>{group.description}</div>}</td>
                <td>{group.redundancy_type === 'DEVICE' ? 'Devices' : 'Links'}</td>
                <td>{targetName(group, 'primary')}</td>
                <td>{targetName(group, 'secondary')}</td>
                <td>{group.service_check_type || 'NONE'}</td>
                <td><span className={`badge badge-${group.status?.toLowerCase() || 'unknown'}`}>{group.status}</span></td>
                {canManageRedundancy&&<td style={{ textAlign: 'right' }}><div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                  <button className="btn btn-secondary" style={{ padding: '5px 10px', fontSize: '0.75rem' }} onClick={() => openEdit(group)}><Edit3 size={14} /> Edit</button>
                  <button className="btn btn-danger" style={{ padding: '5px 10px', fontSize: '0.75rem' }} onClick={() => setDeleteTarget({ id: group.id, name: group.name })}><Trash2 size={14} /> Delete</button>
                </div></td>}
              </tr>
            ))}</tbody>
          </table>
        )}
      </div>

      <Pagination page={page} pageSize={PAGE_SIZE} total={filteredGroups.length} count={visibleGroups.length} onPageChange={setPage}/>

      <Modal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} title={editingId ? 'Edit Redundancy Group' : 'Register Redundancy Group'} subtitle="Define the two units protecting the same service" icon={GitFork} maxWidth="720px">
        <form onSubmit={handleSubmit}>
          <div className="form-group"><label className="form-label">Group Name *</label><input className="form-input" required placeholder="Ex: REDUNDANCIA_DMZ" value={formData.name} onChange={(event) => setFormData({ ...formData, name: event.target.value })} /></div>
          <div className="form-group"><label className="form-label">Description</label><input className="form-input" placeholder="Ex: Pair of switches protecting the DMZ" value={formData.description} onChange={(event) => setFormData({ ...formData, description: event.target.value })} /></div>

          <div className="form-group">
            <label className="form-label">Redundancy Mode *</label>
            <select className="form-select" value={formData.redundancy_type} onChange={(event) => handleTypeChange(event.target.value)}>
              <option value="DEVICE">Devices — does not require registered links</option>
              <option value="LINK">Links — primary and secondary path</option>
            </select>
            <div style={{ marginTop: '6px', fontSize: '0.76rem', color: 'var(--text-dim)' }}>
              {formData.redundancy_type === 'DEVICE' ? 'Use for pairs such as SW DMZ 01 e SW DMZ 02.' : 'Use when two different links serve the same service.'}
            </div>
          </div>

          <div className="form-row">{targetSelect('primary', 'Primary Unit')}{targetSelect('secondary', 'Secondary Unit')}</div>

          <div className="form-row">
            <div className="form-group"><label className="form-label">Service Check</label><select className="form-select" value={formData.service_check_type} onChange={(event) => setFormData({ ...formData, service_check_type: event.target.value })}><option value="NONE">None</option><option value="ICMP">ICMP</option><option value="TCP">TCP</option><option value="HTTP">HTTP</option><option value="HTTPS">HTTPS</option></select></div>
            <div className="form-group"><label className="form-label">Port</label><input className="form-input" type="number" min="1" max="65535" disabled={!['TCP', 'HTTP', 'HTTPS'].includes(formData.service_check_type)} value={formData.service_check_port} onChange={(event) => setFormData({ ...formData, service_check_port: event.target.value })} /></div>
          </div>
          <div className="form-group"><label className="form-label">Service Target</label><input className="form-input" disabled={formData.service_check_type === 'NONE'} placeholder="Service IP, hostname, or URL" value={formData.service_check_target} onChange={(event) => setFormData({ ...formData, service_check_target: event.target.value })} /></div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', borderTop: '1px solid var(--border-color)', paddingTop: '16px' }}><button type="button" className="btn btn-secondary" onClick={() => setIsModalOpen(false)}>Cancel</button><button type="submit" className="btn btn-primary">{editingId ? 'Update Group' : 'Register Group'}</button></div>
        </form>
      </Modal>

      <ConfirmModal isOpen={Boolean(deleteTarget)} onClose={() => setDeleteTarget(null)} onConfirm={executeDelete} title="Delete Redundancy Group" message={deleteTarget ? `Are you sure you want to delete the group "${deleteTarget.name}"?` : ''} />
    </div>
  );
}
