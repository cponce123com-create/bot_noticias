import { useState, useEffect } from 'react';
import { Eye, ThumbsUp, Search, ChevronDown, ChevronUp } from 'lucide-react';
import { getNews, getSources, getCategories, approveNews } from '../lib/api';
import { useToast } from '../hooks/useToast';
import { formatDate, truncate, cn } from '../lib/utils';
import DataTable from '../components/DataTable';
import StatusBadge from '../components/StatusBadge';
import Modal from '../components/Modal';

interface NewsItem {
  id: number;
  title: string;
  content?: string;
  summary?: string;
  source_name?: string;
  source_id?: number;
  category_name?: string;
  category_id?: number;
  status: string;
  url?: string;
  created_at: string;
  published_at?: string;
}

interface SelectOption {
  id: number;
  name: string;
}

export default function NewsList() {
  const [news, setNews] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [filterStatus, setFilterStatus] = useState('');
  const [filterSource, setFilterSource] = useState('');
  const [filterCategory, setFilterCategory] = useState('');
  const [sources, setSources] = useState<SelectOption[]>([]);
  const [categories, setCategories] = useState<SelectOption[]>([]);
  const [viewNews, setViewNews] = useState<NewsItem | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const { toast } = useToast();

  const loadNews = async () => {
    setLoading(true);
    try {
      const data = await getNews({
        status: filterStatus || undefined,
        source_id: filterSource ? parseInt(filterSource) : undefined,
        category_id: filterCategory ? parseInt(filterCategory) : undefined,
        page,
        per_page: 15,
      });
      setNews(data.items || data.data || data.news || []);
      setTotalPages(
        data.total_pages ||
          data.pages ||
          Math.ceil((data.total || 0) / 15) ||
          1
      );
    } catch (err) {
      console.error('Error cargando noticias:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    Promise.all([
      getSources({ per_page: 100 }),
      getCategories(),
    ]).then(([srcData, catData]) => {
      setSources(
        (srcData.items || srcData.data || srcData.sources || []).map(
          (s: { id: number; name: string }) => ({ id: s.id, name: s.name })
        )
      );
      setCategories(
        (catData.items || catData.data || catData.categories || catData || []).map(
          (c: { id: number; name: string }) => ({ id: c.id, name: c.name })
        )
      );
    });
  }, []);

  useEffect(() => {
    loadNews();
  }, [page, filterStatus, filterSource, filterCategory]);

  const handleApprove = async (id: number) => {
    try {
      await approveNews(id);
      loadNews();
    } catch (err) {
      toast('Error al aprobar la noticia', 'error');
      console.error('Error aprobando noticia:', err);
    }
  };

  const statuses = [
    { value: '', label: 'Todos los estados' },
    { value: 'pending', label: 'Pendiente' },
    { value: 'approved', label: 'Aprobado' },
    { value: 'published', label: 'Publicado' },
    { value: 'rejected', label: 'Rechazado' },
    { value: 'draft', label: 'Borrador' },
  ];

  const columns = [
    {
      key: 'title',
      header: 'Título',
      render: (item: NewsItem) => (
        <div className="max-w-md">
          <button
            onClick={() =>
              setExpandedId(expandedId === item.id ? null : item.id)
            }
            className="text-left"
          >
            <span className="font-medium text-gray-900 hover:text-primary-600 transition-colors">
              {truncate(item.title, 80)}
            </span>
          </button>
          {expandedId === item.id && item.content && (
            <div className="mt-2 p-3 bg-gray-50 rounded-lg text-xs text-gray-600 whitespace-pre-wrap max-h-40 overflow-y-auto">
              {item.content}
            </div>
          )}
        </div>
      ),
    },
    {
      key: 'source_name',
      header: 'Fuente',
      render: (item: NewsItem) => (
        <span className="text-gray-500">{item.source_name || '—'}</span>
      ),
    },
    {
      key: 'category_name',
      header: 'Categoría',
      render: (item: NewsItem) =>
        item.category_name ? (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-accent-50 text-accent-700">
            {item.category_name}
          </span>
        ) : (
          <span className="text-gray-400">—</span>
        ),
    },
    {
      key: 'status',
      header: 'Estado',
      render: (item: NewsItem) => <StatusBadge status={item.status} />,
    },
    {
      key: 'created_at',
      header: 'Fecha',
      sortable: true,
      render: (item: NewsItem) => (
        <span className="text-gray-500 text-xs">{formatDate(item.created_at)}</span>
      ),
    },
    {
      key: 'actions',
      header: 'Acciones',
      className: 'text-right',
      render: (item: NewsItem) => (
        <div className="flex items-center justify-end gap-1">
          <button
            onClick={() => setViewNews(item)}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
            title="Ver detalle"
          >
            <Eye className="w-4 h-4" />
          </button>
          {item.status === 'pending' && (
            <button
              onClick={() => handleApprove(item.id)}
              className="p-1.5 rounded-lg text-green-500 hover:text-green-700 hover:bg-green-50 transition-colors"
              title="Aprobar"
            >
              <ThumbsUp className="w-4 h-4" />
            </button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Noticias</h1>
        <div className="text-sm text-gray-500">
          {news.length} noticia(s)
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <select
          value={filterStatus}
          onChange={(e) => {
            setFilterStatus(e.target.value);
            setPage(1);
          }}
          className="select-field py-2 w-40"
        >
          {statuses.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
          <select
            value={filterSource}
            onChange={(e) => {
              setFilterSource(e.target.value);
              setPage(1);
            }}
            className="select-field pl-9 py-2 w-44"
          >
            <option value="">Todas las fuentes</option>
            {sources.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
        <select
          value={filterCategory}
          onChange={(e) => {
            setFilterCategory(e.target.value);
            setPage(1);
          }}
          className="select-field py-2 w-44"
        >
          <option value="">Todas las categorías</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </div>

      <DataTable
        columns={columns}
        data={news}
        keyExtractor={(item) => item.id}
        loading={loading}
        emptyMessage="No se encontraron noticias"
        page={page}
        totalPages={totalPages}
        onPageChange={setPage}
      />

      {/* View Detail Modal */}
      <Modal
        isOpen={viewNews !== null}
        onClose={() => setViewNews(null)}
        title="Detalle de noticia"
        size="lg"
        footer={
          <button
            onClick={() => setViewNews(null)}
            className="btn-secondary"
          >
            Cerrar
          </button>
        }
      >
        {viewNews && (
          <div className="space-y-4">
            <div>
              <h3 className="text-lg font-semibold text-gray-900">
                {viewNews.title}
              </h3>
            </div>
            <div className="flex flex-wrap gap-4 text-sm text-gray-500">
              <div>
                <span className="font-medium">Fuente:</span>{' '}
                {viewNews.source_name || '—'}
              </div>
              <div>
                <span className="font-medium">Categoría:</span>{' '}
                {viewNews.category_name || '—'}
              </div>
              <div>
                <StatusBadge status={viewNews.status} />
              </div>
              <div>
                <span className="font-medium">Creado:</span>{' '}
                {formatDate(viewNews.created_at)}
              </div>
              {viewNews.published_at && (
                <div>
                  <span className="font-medium">Publicado:</span>{' '}
                  {formatDate(viewNews.published_at)}
                </div>
              )}
            </div>
            {viewNews.summary && (
              <div>
                <h4 className="text-sm font-medium text-gray-700 mb-1">
                  Resumen
                </h4>
                <p className="text-sm text-gray-600 bg-gray-50 p-3 rounded-lg">
                  {viewNews.summary}
                </p>
              </div>
            )}
            {viewNews.content && (
              <div>
                <h4 className="text-sm font-medium text-gray-700 mb-1">
                  Contenido completo
                </h4>
                <div className="text-sm text-gray-600 bg-gray-50 p-3 rounded-lg max-h-60 overflow-y-auto whitespace-pre-wrap">
                  {viewNews.content}
                </div>
              </div>
            )}
            {viewNews.url && (
              <div>
                <a
                  href={viewNews.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary-600 hover:text-primary-700 text-sm font-medium"
                >
                  Ver fuente original →
                </a>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
