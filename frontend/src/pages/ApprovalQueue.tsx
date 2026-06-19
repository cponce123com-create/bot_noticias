import { useState, useEffect } from 'react';
import {
  CheckCircle,
  XCircle,
  Edit3,
  Save,
  X,
  Inbox,
  Loader2,
} from 'lucide-react';
import { getApprovalQueue, approveNews, approveAllNews, rejectNews, scrapeNow } from '../lib/api';
import { useToast } from '../hooks/useToast';
import { formatDate, truncate, cn } from '../lib/utils';
import StatusBadge from '../components/StatusBadge';
import Modal from '../components/Modal';

interface PendingNews {
  id: number;
  title: string;
  content?: string;
  summary?: string;
  source_name?: string;
  category_name?: string;
  category_id?: number;
  status: string;
  created_at: string;
}

export default function ApprovalQueue() {
  const [items, setItems] = useState<PendingNews[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [editItem, setEditItem] = useState<PendingNews | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [editSummary, setEditSummary] = useState('');
  const [editCategory, setEditCategory] = useState('');
  const [processing, setProcessing] = useState<number | null>(null);
  const [approvingAll, setApprovingAll] = useState(false);
  const [scrapingNow, setScrapingNow] = useState(false);
  const { toast } = useToast();

  const loadItems = async () => {
    setLoading(true);
    try {
      const data = await getApprovalQueue({ page, per_page: 12 });
      setItems(data.items || data.data || data.news || []);
      setTotalPages(
        data.total_pages ||
          data.pages ||
          Math.ceil((data.total || 0) / 12) ||
          1
      );
    } catch (err) {
      console.error('Error cargando cola de aprobación:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadItems();
  }, [page]);

  const handleApprove = async (item: PendingNews) => {
    setProcessing(item.id);
    try {
      await approveNews(item.id);
      loadItems();
    } catch (err) {
      console.error('Error aprobando noticia:', err);
    } finally {
      setProcessing(null);
    }
  };

  const handleReject = async (id: number) => {
    setProcessing(id);
    try {
      await rejectNews(id);
      loadItems();
    } catch (err) {
      console.error('Error rechazando noticia:', err);
    } finally {
      setProcessing(null);
    }
  };

  const handleApproveAll = async () => {
    setApprovingAll(true);
    try {
      const result = await approveAllNews();
      toast(`Se aprobaron ${result.approved} noticias`, 'success');
      loadItems();
    } catch (err) {
      toast('Error al aprobar todas las noticias', 'error');
      console.error('Error aprobando todas:', err);
    } finally {
      setApprovingAll(false);
    }
  };

  const handleScrapeNow = async () => {
    setScrapingNow(true);
    try {
      const result = await scrapeNow();
      toast(result.message || 'Scraping completado', 'success');
      loadItems();
    } catch (err) {
      toast('Error al ejecutar scraping', 'error');
      console.error('Error en scraping manual:', err);
    } finally {
      setScrapingNow(false);
    }
  };

  const handleEditApprove = async () => {
    if (!editItem) return;
    setProcessing(editItem.id);
    try {
      await approveNews(editItem.id, {
        title: editTitle || undefined,
        summary: editSummary || undefined,
        category_id: editCategory ? parseInt(editCategory) : undefined,
      });
      setEditItem(null);
      loadItems();
      toast('Noticia aprobada correctamente', 'success');
    } catch (err) {
      toast('Error al guardar los cambios', 'error');
      console.error('Error guardando cambios:', err);
    } finally {
      setProcessing(null);
    }
  };

  const openEdit = (item: PendingNews) => {
    setEditItem(item);
    setEditTitle(item.title);
    setEditSummary(item.summary || item.content || '');
    setEditCategory(String(item.category_id || ''));
  };

  if (loading) {
    return (
      <div>
        <div className="page-header">
          <h1 className="page-title">Cola de aprobación</h1>
        </div>
        <div className="flex justify-center py-20">
          <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Cola de aprobación</h1>
        <div className="flex items-center gap-3">
          <button
            onClick={handleScrapeNow}
            disabled={scrapingNow}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 transition-colors disabled:opacity-50"
          >
            {scrapingNow ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Loader2 className="w-3.5 h-3.5" />
            )}
            {scrapingNow ? 'Scrapeando...' : 'Scrapear ahora'}
          </button>
          {items.length > 0 && (
          <button
            onClick={handleApproveAll}
            disabled={approvingAll}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white bg-green-600 hover:bg-green-700 transition-colors disabled:opacity-50"
          >
            {approvingAll ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <CheckCircle className="w-3.5 h-3.5" />
            )}
            Aprobar todo ({items.length})
          </button>
          )}          <div className="text-sm text-gray-500">
            {items.length} noticia(s) pendiente(s)
          </div>
        </div>
      </div>

      {items.length === 0 ? (
        <div className="card p-16">
          <div className="flex flex-col items-center justify-center text-center">
            <div className="w-24 h-24 bg-green-50 rounded-full flex items-center justify-center mb-4">
              <CheckCircle className="w-12 h-12 text-green-400" />
            </div>
            <h3 className="text-lg font-semibold text-gray-900 mb-1">
              ¡Todo al día!
            </h3>
            <p className="text-gray-500 text-sm max-w-md">
              No hay noticias pendientes de aprobación. Todas las noticias han
              sido revisadas.
            </p>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {items.map((item) => (
            <div
              key={item.id}
              className="card-hover p-5 flex flex-col animate-slide-up"
            >
              {/* Header */}
              <div className="flex items-start justify-between gap-3 mb-3">
                <h3 className="text-sm font-semibold text-gray-900 leading-snug line-clamp-2 flex-1">
                  {truncate(item.title, 120)}
                </h3>
                <StatusBadge status={item.status} className="flex-shrink-0" />
              </div>

              {/* Meta info */}
              <div className="flex flex-wrap items-center gap-2 mb-3 text-xs text-gray-500">
                {item.source_name && (
                  <>
                    <span className="font-medium text-gray-600">
                      {item.source_name}
                    </span>
                    <span>·</span>
                  </>
                )}
                {item.category_name && (
                  <>
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-accent-50 text-accent-700">
                      {item.category_name}
                    </span>
                    <span>·</span>
                  </>
                )}
                <span>{formatDate(item.created_at)}</span>
              </div>

              {/* Summary preview */}
              {(item.summary || item.content) && (
                <p className="text-xs text-gray-500 line-clamp-3 mb-4 flex-1">
                  {truncate(item.summary || item.content || '', 200)}
                </p>
              )}

              {/* Actions */}
              <div className="flex items-center gap-2 pt-3 border-t border-gray-100 mt-auto">
                <button
                  onClick={() => handleApprove(item)}
                  disabled={processing === item.id}
                  className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium text-white bg-green-600 hover:bg-green-700 transition-colors disabled:opacity-50"
                >
                  {processing === item.id ? (
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <CheckCircle className="w-3.5 h-3.5" />
                  )}
                  Aprobar
                </button>
                <button
                  onClick={() => openEdit(item)}
                  disabled={processing === item.id}
                  className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium text-accent-700 bg-accent-50 hover:bg-accent-100 transition-colors disabled:opacity-50"
                >
                  <Edit3 className="w-3.5 h-3.5" />
                  Editar
                </button>
                <button
                  onClick={() => handleReject(item.id)}
                  disabled={processing === item.id}
                  className="inline-flex items-center justify-center p-2 rounded-lg text-xs font-medium text-red-600 bg-red-50 hover:bg-red-100 transition-colors disabled:opacity-50"
                  title="Rechazar"
                >
                  <XCircle className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 mt-6">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="btn-secondary !py-1.5 !px-3 text-sm disabled:opacity-30"
          >
            Anterior
          </button>
          <span className="text-sm text-gray-500">
            Página {page} de {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="btn-secondary !py-1.5 !px-3 text-sm disabled:opacity-30"
          >
            Siguiente
          </button>
        </div>
      )}

      {/* Edit Modal */}
      <Modal
        isOpen={editItem !== null}
        onClose={() => setEditItem(null)}
        title="Editar y aprobar noticia"
        size="lg"
        footer={
          <>
            <button
              onClick={() => setEditItem(null)}
              className="btn-secondary"
            >
              Cancelar
            </button>
            <button
              onClick={handleEditApprove}
              disabled={processing !== null}
              className="btn-success"
            >
              {processing !== null ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Save className="w-4 h-4" />
              )}
              Guardar y aprobar
            </button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="label">Título</label>
            <input
              type="text"
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              className="input-field"
            />
          </div>
          <div>
            <label className="label">Resumen / Contenido</label>
            <textarea
              value={editSummary}
              onChange={(e) => setEditSummary(e.target.value)}
              className="input-field"
              rows={5}
            />
          </div>
          <div>
            <label className="label">Categoría ID</label>
            <input
              type="text"
              value={editCategory}
              onChange={(e) => setEditCategory(e.target.value)}
              className="input-field"
              placeholder="ID de categoría (opcional)"
            />
          </div>
        </div>
      </Modal>
    </div>
  );
}
