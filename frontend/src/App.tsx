import { Routes, Route, Navigate, NavLink } from 'react-router-dom';
import { useAuth, useRequireAuth } from './hooks/useAuth';
import {
  LayoutDashboard,
  Radio,
  Newspaper,
  ClipboardCheck,
  Tags,
  Settings,
  LogOut,
  Menu,
  X,
  ChevronDown,
} from 'lucide-react';
import { cn } from './lib/utils';
import { useState } from 'react';
import Dashboard from './pages/Dashboard';
import Sources from './pages/Sources';
import NewsList from './pages/NewsList';
import ApprovalQueue from './pages/ApprovalQueue';
import Categories from './pages/Categories';
import SettingsPage from './pages/Settings';
import Login from './pages/Login';

const navItems = [
  { path: '/', label: 'Panel', icon: LayoutDashboard },
  { path: '/sources', label: 'Fuentes', icon: Radio },
  { path: '/news', label: 'Noticias', icon: Newspaper },
  { path: '/approval', label: 'Aprobación', icon: ClipboardCheck },
  { path: '/categories', label: 'Categorías', icon: Tags },
  { path: '/settings', label: 'Configuración', icon: Settings },
];

function Layout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="min-h-screen flex">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-20 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          'fixed top-0 left-0 z-30 h-full w-64 bg-white border-r border-gray-200 flex flex-col transition-transform duration-300 lg:translate-x-0',
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        {/* Logo */}
        <div className="flex items-center gap-3 px-5 py-5 border-b border-gray-100">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-primary-600 to-primary-800 flex items-center justify-center shadow-sm">
            <Newspaper className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="font-bold text-base text-gray-900">Noticiando.pe</h1>
            <p className="text-[10px] text-gray-400 font-medium">Panel admin</p>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === '/'}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150',
                  isActive
                    ? 'bg-primary-50 text-primary-700 border-l-[3px] border-primary-600 shadow-sm'
                    : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900 border-l-[3px] border-transparent'
                )
              }
            >
              <item.icon className="w-5 h-5 flex-shrink-0" />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        {/* Bot info */}
        <div className="px-4 py-3 border-t border-gray-100">
          <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-50">
            <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            <div className="text-xs text-gray-500">
              <span className="font-medium text-gray-700">Bot:</span>{' '}
              @noticiando_pe_bot
            </div>
          </div>
        </div>
      </aside>

      {/* Main content area */}
      <div className="flex-1 flex flex-col lg:pl-64">
        {/* Top navbar */}
        <header className="sticky top-0 z-10 bg-white/80 backdrop-blur-md border-b border-gray-200">
          <div className="flex items-center justify-between px-4 lg:px-6 py-3">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="lg:hidden p-2 rounded-lg text-gray-500 hover:bg-gray-100 transition-colors"
              >
                {sidebarOpen ? (
                  <X className="w-5 h-5" />
                ) : (
                  <Menu className="w-5 h-5" />
                )}
              </button>
              <div className="hidden lg:block">
                <p className="text-sm text-gray-500">Bienvenido,</p>
                <p className="text-sm font-semibold text-gray-900">
                  {user?.name || user?.email || 'Admin'}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={logout}
                className="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-gray-600 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
              >
                <LogOut className="w-4 h-4" />
                <span className="hidden sm:inline">Cerrar sesión</span>
              </button>
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 p-4 lg:p-6">{children}</main>
      </div>
    </div>
  );
}

function ProtectedLayout() {
  const { loading } = useRequireAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="flex flex-col items-center gap-3">
          <div className="w-10 h-10 border-4 border-primary-600 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-gray-500">Cargando...</p>
        </div>
      </div>
    );
  }

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/sources" element={<Sources />} />
        <Route path="/news" element={<NewsList />} />
        <Route path="/approval" element={<ApprovalQueue />} />
        <Route path="/categories" element={<Categories />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/*" element={<ProtectedLayout />} />
    </Routes>
  );
}
