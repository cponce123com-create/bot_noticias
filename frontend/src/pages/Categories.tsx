import { useState, useEffect } from 'react';
import { Plus, Edit2, Trash2, Palette } from 'lucide-react';
import { getCategories, createCategory, updateCategory, deleteCategory } from '../lib/api';
import { cn } from '../lib/utils';
import Modal from '../components/Modal';

interface Category {
  id: number;
  name: string;
  slug: string;
  description?: string;
  color: string;
  news_count?: number;
}

interface CategoryForm {
  name: string;
  slug: string;
  description: string;
  color: string;
}

const emptyForm: CategoryForm = {
  name: '',
  slug: '',
  description: '',
  color: '#D91023',
};

const presetColors = [
  '#D91023', '#1A237E', '#0D47A1', '#1565C0', '#1976D2',
  '#00838F', '#00695C', '#2E7D32', '#558B2F', '#F9A825',
  '#E65100', '#BF360C', '#4A148C', '#6A1B9A', '#37474F',
];

export default function Categories() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingCat, setEditingCat] = useState<Category | null>(null);
  const [form, setForm] = useState<CategoryForm>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);

  const loadCategories = async () => {
    setLoading(true);
    try {
      const data = await getCategories();
      const list = data.items || data.data || data.categories || data;
      setCategories(Array.isArray(list) ? list : []);
    } catch (err) {
      console.error('Error cargando categorías:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCategories();
  }, []);

  const openCreate = () => {
    setEditingCat(null);
    setForm(emptyForm);
    setModalOpen(true);
  };

  const openEdit = (cat: Category) => {
    setEditingCat(cat);
    setForm({
      name: cat.name,
      slug: cat.slug,
      description: cat.description || '',
      color: cat.color || '#D91023',
    });
    setModalOpen(true);
  };

  const handleSave = async () => {
    if (!form.name.trim() || !form.slug.trim()) {
      alert('Nombre y slug son requeridos');
      return;
    }
    setSaving(true);
    try {
      const data = {
        name: form.name,
        slug: form.slug,
        description: form.description || undefined,
        color: form.color,
      };
      if (editingCat) {
        await updateCategory(editingCat.id, data);
      } else {
        await createCategory(data);
      }
      setModalOpen(false);
      loadCategories();
    } catch (err) {
      console.error('Error guardando categoría:', err);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deleteCategory(id);
      setDeleteConfirm(null);
      loadCategories();
    } catch (err) {
      console.error('Error eliminando categoría:', err);
    }
  };

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Categorías</h1>
        <button onClick={openCreate} className="btn-primary">
          <Plus className="w-4 h-4" />
          Nueva categoría
        </button>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="card p-5 animate-pulse">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 rounded-lg bg-gray-200" />
                <div className="flex-1">
                  <div className="h-4 bg-gray-200 rounded w-24 mb-1" />
                  <div className="h-3 bg-gray-200 rounded w-16" />
                </div>
              </div>
              <div className="h-3 bg-gray-200 rounded w-full" />
            </div>
          ))}
        </div>
      ) : categories.length === 0 ? (
        <div className="card p-12 text-center">
          <Palette className="w-16 h-16 text-gray-300 mx-auto mb-4" />
          <p className="text-gray-500 text-sm">
            No hay categorías. ¡Crea tu primera categoría!
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {categories.map((cat) => (
            <div
              key={cat.id}
              className="card-hover p-5 group animate-slide-up"
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div
                    className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0"
                    style={{ backgroundColor: cat.color || '#D91023' }}
                  >
                    <span className="text-white font-bold text-sm">
                      {cat.name.charAt(0).toUpperCase()}
                    </span>
                  </div>
                  <div>
                    <h3 className="font-semibold text-gray-900">{cat.name}</h3>
                    <p className="text-xs text-gray-500 font-mono">{cat.slug}</p>
                  </div>
                </div>
                <div className="flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button
                    onClick={() => openEdit(cat)}
                    className="p-1.5 rounded-lg text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors"
                    title="Editar"
                  >
                    <Edit2 className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setDeleteConfirm(cat.id)}
                    className="p-1.5 rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                    title="Eliminar"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
              {cat.description && (
                <p className="text-sm text-gray-500 line-clamp-2 mb-3">
                  {cat.description}
                </p>
              )}
              <div className="flex items-center gap-2 text-xs text-gray-400">
                <span
                  className="inline-block w-2 h-2 rounded-full"
                  style={{ backgroundColor: cat.color || '#D91023' }}
                />
                <span>
                  {cat.news_count !== undefined
                    ? `${cat.news_count} noticia(s)`
                    : ''}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create/Edit Modal */}
      <Modal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editingCat ? 'Editar categoría' : 'Nueva categoría'}
        size="md"
        footer={
          <>
            <button
              onClick={() => setModalOpen(false)}
              className="btn-secondary"
            >
              Cancelar
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="btn-primary"
            >
              {saving
                ? 'Guardando...'
                : editingCat
                ? 'Actualizar'
                : 'Crear'}
            </button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="label">Nombre *</label>
            <input
              type="text"
              value={form.name}
              onChange={(e) =>
                setForm({
                  ...form,
                  name: e.target.value,
                  slug: editingCat
                    ? form.slug
                    : e.target.value
                        .toLowerCase()
                        .replace(/[^a-z0-9]+/g, '-')
                        .replace(/^-|-$/g, ''),
                })
              }
              className="input-field"
              placeholder="Nombre de la categoría"
              required
            />
          </div>
          <div>
            <label className="label">Slug *</label>
            <input
              type="text"
              value={form.slug}
              onChange={(e) => setForm({ ...form, slug: e.target.value })}
              className="input-field font-mono"
              placeholder="nombre-categoria"
              required
            />
          </div>
          <div>
            <label className="label">Descripción</label>
            <textarea
              value={form.description}
              onChange={(e) =>
                setForm({ ...form, description: e.target.value })
              }
              className="input-field"
              rows={3}
              placeholder="Descripción opcional de la categoría"
            />
          </div>
          <div>
            <label className="label">Color</label>
            <div className="flex items-center gap-3 mb-2">
              <div
                className="w-8 h-8 rounded-lg border-2 border-gray-200"
                style={{ backgroundColor: form.color }}
              />
              <input
                type="text"
                value={form.color}
                onChange={(e) => setForm({ ...form, color: e.target.value })}
                className="input-field w-28 font-mono uppercase"
                placeholder="#D91023"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              {presetColors.map((color) => (
                <button
                  key={color}
                  onClick={() => setForm({ ...form, color })}
                  className={cn(
                    'w-7 h-7 rounded-lg border-2 transition-all',
                    form.color === color
                      ? 'border-gray-900 scale-110'
                      : 'border-transparent hover:scale-110'
                  )}
                  style={{ backgroundColor: color }}
                />
              ))}
            </div>
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
          ¿Estás seguro de que deseas eliminar esta categoría? Las noticias
          asociadas no se eliminarán, pero quedarán sin categoría.
        </p>
      </Modal>
    </div>
  );
}
