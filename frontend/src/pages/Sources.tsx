import { useState, useEffect } from 'react';
import {
  Plus,
  Edit2,
  Trash2,
  Play,
  Pause,
  Search,
  Filter,
} from 'lucide-react';
import { getSources, createSource, updateSource, deleteSource, pauseSource, activateSource } from '../lib/api';
import { useToast } from '../hooks/useToast';
import { formatDate, cn } from '../lib/utils';
import DataTable from '../components/DataTable';
import StatusBadge from '../components/StatusBadge';
import Modal from '../components/Modal';

interface Source {
  id: number;
  name: string;
  source_type: string;
  country: string;
  status: string;
  priority: number;
  last_fetched_at: string;
  language: string;
  config: Record<string, unknown>;
  fetch_interval: number;
  auto_publish: boolean;
  requires_approval: boolean;
}

interface SourceForm {
  name: string;
  type: string;
  config: string;
  country: string;
  language: string;
  fetch_interval: number;
  priority: number;
  auto_publish: boolean;
  requires_approval: boolean;
}

const emptyForm: SourceForm = {
  name: '',
  type: 'rss',
  config: JSON.stringify({ url: '' }, null, 2),
  country: '',
  language: 'es',
  fetch_interval: 30,
  priority: 5,
  auto_publish: false,
  requires_approval: true,
};

const sourceTypes = [
  { value: 'rss', label: 'RSS' },
  { value: 'web', label: 'Web Scraper' },
  { value: 'telegram', label: 'Telegram' },
  { value: 'twitter', label: 'Twitter/X' },
  { value: 'youtube', label: 'YouTube' },
];

export default function Sources() {
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingSource, setEditingSource] = useState<Source | null>(null);
  const [form, setForm] = useState<SourceForm>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [searchType, setSearchType] = useState('');
  const [searchCountry, setSearchCountry] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);
  const { toast } = useToast();

  const loadSources = async () => {
    setLoading(true);
    try {
      const data = await getSources({
        type: searchType || undefined,
        country: searchCountry || undefined,
        page,
        per_page: 15,
      });
      setSources(data.items || data.data || data.sources || []);
      setTotalPages(data.total_pages || data.pages || Math.ceil((data.total || 0) / 15) || 1);
    } catch (err) {
      console.error('Error cargando fuentes:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSources();
  }, [page, searchType, searchCountry]);

  const openCreate = () => {
    setEditingSource(null);
    setForm(emptyForm);
    setModalOpen(true);
  };

  const openEdit = (source: Source) => {
    setEditingSource(source);
    setForm({
      name: source.name,
      type: source.source_type,
      config: JSON.stringify(source.config, null, 2),
      country: source.country || '',
      language: source.language || 'es',
      fetch_interval: source.fetch_interval || 30,
      priority: source.priority || 5,
      auto_publish: source.auto_publish || false,
      requires_approval: source.requires_approval ?? true,
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      let configObj: Record<string, unknown>;
      try {
        configObj = JSON.parse(form.config);
      } catch {
        alert('Error: La configuración no es un JSON válido');
        setSaving(false);
        return;
      }

      const data = {
        name: form.name,
        type: form.type,
        config: configObj,
        country: form.country || undefined,
        language: form.language || undefined,
        fetch_interval: form.fetch_interval,
        priority: form.priority,
        auto_publish: form.auto_publish,
        requires_approval: form.requires_approval,
      };

      if (editingSource) {
        await updateSource(editingSource.id, data);
      } else {
        await createSource(data);
      }

      setModalOpen(false);
      loadSources();
    } catch (err) {
      console.error('Error guardando fuente:', err);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteSource(id);
      setDeleteConfirm(null);
      loadSources();
    } catch (err) {
      console.error('Error eliminando fuente:', err);
    }
  };

  const handleToggleStatus = async (source: Source) => {
    try {
      if (source.status === 'active') {
        await pauseSource(source.id);
      } else {
        await activateSource(source.id);
      }
      loadSources();
      toast('Estado actualizado', 'success');
    } catch (err) {
      toast('Error al cambiar el estado de la fuente', 'error');
      console.error('Error cambiando estado:', err);
    }
  };

  const columns = [
    {
      key: 'name',
      header: 'Nombre',
      sortable: true,
      render: (item: Source) => (
        <span className="font-medium text-gray-900">{item.name}</span>
      ),
    },
    {
      key: 'source_type',
      header: 'Tipo',
      render: (item: Source) => (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-accent-50 text-accent-700 uppercase">
          {item.source_type}
        </span>
      ),
    },
    {
      key: 'country',
      header: 'País',
      render: (item: Source) => item.country || '—',
    },
    {
      key: 'status',
      header: 'Estado',
      render: (item: Source) => <StatusBadge status={item.status} />,
    },
    {
      key: 'priority',
      header: 'Prioridad',
      sortable: true,
      render: (item: Source) => (
        <span className={cn(
          'font-mono text-sm',
          item.priority >= 8 ? 'text-red-600 font-bold' :
          item.priority >= 5 ? 'text-yellow-600' : 'text-gray-500'
        )}>
          {item.priority}
        </span>
      ),
    },
    {
      key: 'last_fetched_at',
      header: 'Últ. obtención',
      render: (item: Source) =>
        item.last_fetched_at ? formatDate(item.last_fetched_at) : 'Nunca',
    },
    {
      key: 'actions',
      header: 'Acciones',
      className: 'text-right',
      render: (item: Source) => (
        <div className="flex items-center justify-end gap-1">
          <button
            onClick={() => handleToggleStatus(item)}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
            title={item.status === 'active' ? 'Pausar' : 'Activar'}
          >
            {item.status === 'active' ? (
              <Pause className="w-4 h-4" />
            ) : (
              <Play className="w-4 h-4" />
            )}
          </button>
          <button
            onClick={() => openEdit(item)}
            className="p-1.5 rounded-lg text-blue-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
            title="Editar"
          >
            <Edit2 className="w-4 h-4" />
          </button>
          <button
            onClick={() => setDeleteConfirm(item.id)}
            className="p-1.5 rounded-lg text-red-400 hover:text-red-600 hover:bg-red-50 transition-colors"
            title="Eliminar"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      ),
    },
  ];

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Fuentes de noticias</h1>
        <button onClick={openCreate} className="btn-primary">
          <Plus className="w-4 h-4" />
          Añadir fuente
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <div className="relative">
          <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <select
            value={searchType}
            onChange={(e) => { setSearchType(e.target.value); setPage(1); }}
            className="select-field pl-9 pr-8 py-2 w-40"
          >
            <option value="">Todos los tipos</option>
            {sourceTypes.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </div>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            value={searchCountry}
            onChange={(e) => { setSearchCountry(e.target.value); setPage(1); }}
            placeholder="Filtrar por país..."
            className="input-field pl-9 py-2 w-48"
          />
        </div>
      </div>

      <DataTable
        columns={columns}
        data={sources}
        keyExtractor={(item) => item.id}
        loading={loading}
        emptyMessage="No hay fuentes configuradas. ¡Añade tu primera fuente!"
        page={page}
        totalPages={totalPages}
        onPageChange={setPage}
      />

      {/* Create/Edit Modal */}
      <Modal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editingSource ? 'Editar fuente' : 'Nueva fuente'}
        size="lg"
        footer={
          <>
            <button
              onClick={() => setModalOpen(false)}
              className="btn-secondary"
            >
              Cancelar
            </button>
            <button onClick={handleSave} disabled={saving} className="btn-primary">
              {saving ? 'Guardando...' : editingSource ? 'Actualizar' : 'Crear'}
            </button>
          </>
        }
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="label">Nombre *</label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="input-field"
              placeholder="Nombre de la fuente"
              required
            />
          </div>
          <div>
            <label className="label">Tipo *</label>
            <select
              value={form.type}
              onChange={(e) => setForm({ ...form, type: e.target.value })}
              className="select-field"
            >
              {sourceTypes.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">País</label>
            <input
              type="text"
              value={form.country}
              onChange={(e) => setForm({ ...form, country: e.target.value })}
              className="input-field"
              placeholder="PE"
            />
          </div>
          <div>
            <label className="label">Idioma</label>
            <input
              type="text"
              value={form.language}
              onChange={(e) => setForm({ ...form, language: e.target.value })}
              className="input-field"
              placeholder="es"
            />
          </div>
          <div>
            <label className="label">Intervalo (minutos)</label>
            <input
              type="number"
              value={form.fetch_interval}
              onChange={(e) =>
                setForm({ ...form, fetch_interval: parseInt(e.target.value) || 30 })
              }
              className="input-field"
              min={1}
            />
          </div>
          <div>
            <label className="label">Prioridad (1-10)</label>
            <input
              type="number"
              value={form.priority}
              onChange={(e) =>
                setForm({ ...form, priority: parseInt(e.target.value) || 5 })
              }
              className="input-field"
              min={1}
              max={10}
            />
          </div>
          <div className="md:col-span-2">
            <label className="label">Configuración (JSON)</label>
            <textarea
              value={form.config}
              onChange={(e) => setForm({ ...form, config: e.target.value })}
              className="input-field font-mono text-xs"
              rows={6}
            />
          </div>
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={form.auto_publish}
                onChange={(e) =>
                  setForm({ ...form, auto_publish: e.target.checked })
                }
                className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
              />
              <span className="text-sm text-gray-700">Publicación automática</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={form.requires_approval}
                onChange={(e) =>
                  setForm({ ...form, requires_approval: e.target.checked })
                }
                className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
              />
              <span className="text-sm text-gray-700">Requiere aprobación</span>
            </label>
          </div>
        </div>
      </Modal>

      {/* Delete Confirmation */}
      <Modal
        isOpen={deleteConfirm !== null}
        onClose={() => setDeleteConfirm(null)}
        title="Confirmar eliminación"
        size="sm"
        footer={
          <>
            <button
              onClick={() => setDeleteConfirm(null)}
              className="btn-secondary"
            >
              Cancelar
            </button>
            <button
              onClick={() => deleteConfirm && handleDelete(deleteConfirm)}
              className="btn-danger"
            >
              Eliminar
            </button>
          </>
        }
      >
        <p className="text-sm text-gray-600">
          ¿Estás seguro de que deseas eliminar esta fuente? Esta acción no se puede
          deshacer.
        </p>
      </Modal>
    </div>
  );
}
