import React, { useEffect, useState } from 'react';
import { Plus, Trash2, Edit3, Server, Search, Radio, CheckCircle, AlertCircle, RefreshCw } from 'lucide-react';
import api from '../api/client';
import Modal from '../components/Modal';
import ConfirmModal from '../components/ConfirmModal';
import { getApiErrorMessage } from '../utils/errors';
import DeviceIcon from '../components/DeviceIcon';

export default function Devices() {
  const [devices, setDevices] = useState([]);
  const [links, setLinks] = useState([]);
  const [icons, setIcons] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [typeFilter, setTypeFilter] = useState('ALL');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [pingResult, setPingResult] = useState({});
  const [pingingId, setPingingId] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);

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
  }, []);

  const handleOpenAdd = () => {
    setEditingId(null);
    setFormData(initialFormState);
    setIsModalOpen(true);
  };

  const handleOpenEdit = (dev) => {
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
    });
    setIsModalOpen(true);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const { primary_link_id, ...deviceFields } = formData;
    const payload = {
      ...deviceFields,
      gateway_ip_address: formData.gateway_ip_address || null,
      gateway_device_id: formData.gateway_device_id ? Number(formData.gateway_device_id) : null,
      icon_id: formData.icon_id ? Number(formData.icon_id) : null,
      ...(editingId && {
        primary_link_id: primary_link_id ? Number(primary_link_id) : null,
      }),
    };
    try {
      if (editingId) {
        await api.put(`/devices/${editingId}`, payload);
      } else {
        await api.post('/devices', payload);
      }
      setIsModalOpen(false);
      await Promise.all([fetchDevices(), fetchLinks()]);
    } catch (err) {
      alert('Erro ao salvar equipamento: ' + getApiErrorMessage(err));
    }
  };

  const executeDelete = async () => {
    if (!deleteTarget) return;
    try {
      await api.delete(`/devices/${deleteTarget.id}`);
      fetchDevices();
    } catch (err) {
      alert('Erro ao excluir equipamento: ' + getApiErrorMessage(err));
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

  return (
    <div>
      {/* Action Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <h2 style={{ fontSize: '1.35rem', color: '#fff', fontWeight: 700, letterSpacing: '-0.01em' }}>
            Gerenciamento de Equipamentos de Rede
          </h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginTop: '2px' }}>
            Cadastre switches, media converters, roteadores e rádiosEnlaces monitorados em tempo real.
          </p>
        </div>

        <button className="btn btn-primary" onClick={handleOpenAdd} style={{ padding: '10px 20px', fontSize: '0.9rem' }}>
          <Plus size={18} /> Adicionar Equipamento
        </button>
      </div>

      {/* Filter Bar */}
      <div className="glass-card" style={{ padding: '14px 18px', marginBottom: '20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1, minWidth: '260px' }}>
          <Search size={18} color="var(--text-dim)" />
          <input
            type="text"
            className="form-input"
            style={{ width: '100%', border: 'none', background: 'transparent', padding: 0 }}
            placeholder="Buscar por nome, IP ou localização..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Tipo:</span>
          <select
            className="form-select"
            style={{ padding: '6px 12px', fontSize: '0.85rem' }}
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
          >
            <option value="ALL">Todos os Tipos</option>
            <option value="SWITCH">Switch</option>
            <option value="MEDIA_CONVERTER">Media Converter</option>
            <option value="ROUTER">Roteador</option>
            <option value="RADIO">Rádio Enlace</option>
            <option value="FIREWALL">Firewall</option>
            <option value="SERVER">Servidor</option>
            <option value="OTHER">Outro</option>
          </select>
        </div>
      </div>

      {/* Table Container */}
      <div className="glass-card" style={{ overflow: 'hidden' }}>
        {filteredDevices.length === 0 ? (
          <div style={{ padding: '48px 24px', textAlign: 'center', color: 'var(--text-muted)' }}>
            <Server size={44} style={{ marginBottom: '16px', opacity: 0.4 }} />
            <h4 style={{ color: '#fff', fontSize: '1rem', marginBottom: '6px' }}>Nenhum equipamento encontrado</h4>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-dim)', maxWidth: '400px', margin: '0 auto' }}>
              {devices.length === 0
                ? 'Comece clicando no botão "+ Adicionar Equipamento" acima para cadastrar seu primeiro switch ou radio.'
                : 'Nenhum equipamento corresponde aos filtros aplicados.'}
            </p>
          </div>
        ) : (
          <table className="custom-table">
            <thead>
              <tr>
                <th>Equipamento</th>
                <th>Tipo</th>
                <th>Endereço IP</th>
                <th>Localização</th>
                <th>Gateway / Link</th>
                <th>Status</th>
                <th>Diagnóstico ICMP</th>
                <th style={{ textAlign: 'right' }}>Ações</th>
              </tr>
            </thead>
            <tbody>
              {filteredDevices.map((d) => (
                <tr key={d.id}>
                  <td>
                    <div style={{ display:'flex', alignItems:'center', gap:'8px', fontWeight: 600, color: '#fff', fontSize: '0.92rem' }}><DeviceIcon icon={icons.find(i => i.id === d.icon_id)} size={18} />{d.name}</div>
                    {d.model && <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>{d.manufacturer} {d.model}</div>}
                  </td>
                  <td>
                    <span style={{
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      padding: '3px 8px',
                      borderRadius: '6px',
                      background: 'rgba(255, 255, 255, 0.06)',
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
                      {d.gateway_ip_address || '—'}
                    </div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>
                      {devices.find(dev => dev.id === d.gateway_device_id)?.name || 'Gateway não associado'}
                    </div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>
                      {links.find(link => link.id === d.primary_link_id)?.name || 'Link principal não associado'}
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
                          <span style={{ color: '#ef4444' }}>Sem Resposta</span>
                        )
                      ) : (
                        'Testar Ping'
                      )}
                    </button>
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '8px' }}>
                      <button
                        className="btn btn-secondary"
                        style={{ padding: '5px 10px', fontSize: '0.75rem' }}
                        onClick={() => handleOpenEdit(d)}
                        title="Editar Equipamento"
                      >
                        <Edit3 size={14} /> Editar
                      </button>
                      <button
                        className="btn btn-danger"
                        style={{ padding: '5px 10px', fontSize: '0.75rem' }}
                        onClick={() => setDeleteTarget({ id: d.id, name: d.name })}
                        title="Excluir Equipamento"
                      >
                        <Trash2 size={14} /> Excluir
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Professional Modal Form */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title={editingId ? 'Editar Equipamento de Rede' : 'Cadastrar Novo Equipamento'}
        subtitle="Preencha as informações técnicas do equipamento para integração no monitoramento"
        icon={Server}
        maxWidth="720px"
      >
        <form onSubmit={handleSubmit}>
          {/* Section 1: Identification */}
          <div style={{ marginBottom: '20px' }}>
            <h4 style={{ fontSize: '0.85rem', fontWeight: 600, color: '#3b82f6', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '12px' }}>
              1. Identificação Básica
            </h4>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Nome do Equipamento *</label>
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
                <label className="form-label">Tipo de Equipamento *</label>
                <select
                  className="form-select"
                  value={formData.device_type}
                  onChange={(e) => setFormData({ ...formData, device_type: e.target.value })}
                >
                  <option value="SWITCH">Switch de Camada 2/3</option>
                  <option value="MEDIA_CONVERTER">Media Converter (Conversor óptico)</option>
                  <option value="ROUTER">Roteador Core/Borda</option>
                  <option value="RADIO">Rádio Enlace (Microwaves)</option>
                  <option value="FIREWALL">Firewall / Security Appliance</option>
                  <option value="SERVER">Servidor / Host</option>
                  <option value="OTHER">Outro Dispositivo</option>
                </select>
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Ícone do equipamento</label>
                <select className="form-select" value={formData.icon_id} onChange={(e) => setFormData({ ...formData, icon_id: e.target.value })}>
                  <option value="">Automático pelo tipo</option>
                  {icons.map((icon) => <option key={icon.id} value={icon.id}>{icon.category} — {icon.name}</option>)}
                </select>
              </div>
              <div className="form-group">
                <label className="form-label">Grupo</label>
                <input className="form-input" value={formData.group_name} onChange={(e) => setFormData({ ...formData, group_name: e.target.value })} placeholder="Ex: DMZ, Core, Filial Norte" />
              </div>
            </div>
          </div>

          {/* Section 2: Network & Location */}
          <div style={{ marginBottom: '20px' }}>
            <h4 style={{ fontSize: '0.85rem', fontWeight: 600, color: '#3b82f6', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '12px' }}>
              2. Endereçamento e Localização
            </h4>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Endereço IP (Gerenciamento)</label>
                <input
                  className="form-input"
                  type="text"
                  placeholder="Ex: 10.10.0.1"
                  value={formData.ip_address}
                  onChange={(e) => setFormData({ ...formData, ip_address: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Sub-rede (CIDR)</label>
                <input
                  className="form-input"
                  type="text"
                  placeholder="Ex: 10.10.0.0/24"
                  value={formData.network}
                  onChange={(e) => setFormData({ ...formData, network: e.target.value })}
                />
              </div>
            </div>

            <div className="form-row">
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
                <label className="form-label">Equipamento Gateway</label>
                <select
                  className="form-select"
                  value={formData.gateway_device_id}
                  onChange={(e) => setFormData({ ...formData, gateway_device_id: e.target.value })}
                >
                  <option value="">Não associado</option>
                  {devices
                    .filter((d) => d.id !== editingId)
                    .map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name} {d.ip_address ? `(${d.ip_address})` : ''}
                      </option>
                    ))}
                </select>
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">Link Principal</label>
              <select
                className="form-select"
                value={formData.primary_link_id}
                disabled={!editingId}
                onChange={(e) => setFormData({ ...formData, primary_link_id: e.target.value })}
              >
                <option value="">{editingId ? 'Não associado' : 'Disponível após cadastrar o equipamento'}</option>
                {links
                  .filter((l) => editingId && (l.source_device_id === editingId || l.destination_device_id === editingId))
                  .map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.name} ({l.priority})
                    </option>
                  ))}
              </select>
            </div>

            <div className="form-group">
              <label className="form-label">Localização Física / Rack</label>
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
              3. Detalhes do Hardware & Monitoramento
            </h4>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Fabricante</label>
                <input
                  className="form-input"
                  type="text"
                  placeholder="Ex: Cisco, TP-Link, Mikrotik"
                  value={formData.manufacturer}
                  onChange={(e) => setFormData({ ...formData, manufacturer: e.target.value })}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Modelo</label>
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
              <label className="form-label">Função / Observações</label>
              <input
                className="form-input"
                type="text"
                placeholder="Ex: Concentrador dos enlaces de fibra do trecho norte"
                value={formData.function}
                onChange={(e) => setFormData({ ...formData, function: e.target.value })}
              />
            </div>
          </div>

          {/* Buttons Footer */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '12px', borderTop: '1px solid var(--border-color)', paddingTop: '16px' }}>
            <button type="button" className="btn btn-secondary" onClick={() => setIsModalOpen(false)}>
              Cancelar
            </button>
            <button type="submit" className="btn btn-primary">
              {editingId ? 'Atualizar Equipamento' : 'Cadastrar Equipamento'}
            </button>
          </div>
        </form>
      </Modal>

      {/* In-App Delete Confirmation Modal */}
      <ConfirmModal
        isOpen={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        onConfirm={executeDelete}
        title="Excluir Equipamento"
        message={
          deleteTarget
            ? `Tem certeza que deseja apagar o equipamento "${deleteTarget.name}"? Esta ação removerá também os links, histórico e redundâncias associados.`
            : ''
        }
      />
    </div>
  );
}
