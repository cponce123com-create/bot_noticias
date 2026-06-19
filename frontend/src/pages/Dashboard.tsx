import { useState, useEffect } from 'react';
import {
  Globe,
  Radio,
  Newspaper,
  Send,
  TrendingUp,
  Clock,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { getStats, getNews } from '../lib/api';
import { useToast } from '../hooks/useToast';
import { formatDate, truncate, cn } from '../lib/utils';
import StatusBadge from '../components/StatusBadge';

interface Stats {
  total_sources: number;
  active_sources: number;
  news_today: number;
  published_today: number;
  news_by_source?: { name: string; count: number }[];
}

interface NewsItem {
  id: number;
  title: string;
  source_name?: string;
  status: string;
  created_at: string;
}

const timeRanges = [
  { value: '24h', label: 'Últimas 24h' },
  { value: '7d', label: 'Últimos 7 días' },
  { value: '30d', label: 'Últimos 30 días' },
  { value: 'all', label: 'Todo' },
];

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [recentNews, setRecentNews] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState('24h');
  const { toast } = useToast();

  useEffect(() => {
    async function loadData() {
      try {
        const [statsData, newsData] = await Promise.all([
          getStats(),
          getNews({ per_page: 10 }),
        ]);
        setStats(statsData);
        setRecentNews(newsData.items || newsData.data || newsData.news || []);
      } catch (err) {
        toast('Error al cargar el panel', 'error');
        console.error('Error cargando dashboard:', err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [timeRange]);

  const statCards = [
    {
      label: 'Fuentes totales',
      value: stats?.total_sources ?? 0,
      icon: Globe,
      color: 'bg-blue-500',
      bgColor: 'bg-blue-50 text-blue-600',
    },
    {
      label: 'Fuentes activas',
      value: stats?.active_sources ?? 0,
      icon: Radio,
      color: 'bg-green-500',
      bgColor: 'bg-green-50 text-green-600',
    },
    {
      label: 'Noticias hoy',
      value: stats?.news_today ?? 0,
      icon: Newspaper,
      color: 'bg-primary-500',
      bgColor: 'bg-primary-50 text-primary-600',
    },
    {
      label: 'Publicadas hoy',
      value: stats?.published_today ?? 0,
      icon: Send,
      color: 'bg-accent-500',
      bgColor: 'bg-accent-50 text-accent-600',
    },
  ];

  const chartData = stats?.news_by_source || [];

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Panel de control</h1>
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4 text-gray-400" />
          <div className="flex bg-gray-100 rounded-lg p-0.5">
            {timeRanges.map((range) => (
              <button
                key={range.value}
                onClick={() => setTimeRange(range.value)}
                className={cn(
                  'px-3 py-1.5 text-xs font-medium rounded-md transition-all',
                  timeRange === range.value
                    ? 'bg-white text-gray-900 shadow-sm'
                    : 'text-gray-500 hover:text-gray-700'
                )}
              >
                {range.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {statCards.map((card) => (
          <div key={card.label} className="stats-card">
            <div className={cn('stats-icon', card.bgColor)}>
              <card.icon className="w-6 h-6" />
            </div>
            <div>
              <p className="text-sm text-gray-500">{card.label}</p>
              <p className="text-2xl font-bold text-gray-900 mt-0.5">
                {loading ? (
                  <span className="inline-block w-12 h-7 bg-gray-200 rounded animate-pulse" />
                ) : (
                  card.value
                )}
              </p>
            </div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Chart */}
        <div className="lg:col-span-2 card p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900">
              Noticias por fuente
            </h2>
            <TrendingUp className="w-5 h-5 text-gray-400" />
          </div>
          {chartData.length > 0 ? (
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis
                    dataKey="name"
                    tick={{ fontSize: 12 }}
                    tickLine={false}
                    axisLine={false}
                  />
                  <YAxis
                    tick={{ fontSize: 12 }}
                    tickLine={false}
                    axisLine={false}
                  />
                  <Tooltip
                    contentStyle={{
                      borderRadius: '8px',
                      border: '1px solid #e5e7eb',
                      boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)',
                    }}
                  />
                  <Bar
                    dataKey="count"
                    fill="#D91023"
                    radius={[4, 4, 0, 0]}
                    maxBarSize={48}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="h-72 flex items-center justify-center text-gray-400 text-sm">
              No hay datos disponibles
            </div>
          )}
        </div>

        {/* Recent News */}
        <div className="card p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            Últimas noticias
          </h2>
          {recentNews.length > 0 ? (
            <div className="space-y-3">
              {recentNews.map((news) => (
                <div
                  key={news.id}
                  className="p-3 rounded-lg bg-gray-50 hover:bg-gray-100 transition-colors"
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm font-medium text-gray-900 leading-snug line-clamp-2">
                      {truncate(news.title, 80)}
                    </p>
                    <StatusBadge status={news.status} />
                  </div>
                  <div className="flex items-center gap-2 mt-2 text-xs text-gray-500">
                    {news.source_name && (
                      <>
                        <span>{news.source_name}</span>
                        <span>·</span>
                      </>
                    )}
                    <span>{formatDate(news.created_at)}</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-gray-400 text-sm">
              No hay noticias recientes
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
