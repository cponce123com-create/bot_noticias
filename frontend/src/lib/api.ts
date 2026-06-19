import axios from 'axios';

// URL base: VITE_API_URL > mismo origen > fallback hardcoded
const API_URL = import.meta.env.VITE_API_URL
  ? `${import.meta.env.VITE_API_URL}/api/v1`
  : `${window.location.origin}/api/v1`;

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
});

export default api;

// Token en memoria (no localStorage) - se pierde al recargar, segura contra XSS
let _accessToken: string | null = null;

export function setAccessToken(token: string | null) {
  _accessToken = token;
}

export function getAccessToken(): string | null {
  return _accessToken;
}

api.interceptors.request.use(
  (config) => {
    if (_accessToken) {
      config.headers.Authorization = `Bearer ${_accessToken}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      const { status, data } = error.response;
      const detail = data?.detail || data?.message || '';

      switch (status) {
        case 401:
          _accessToken = null;
          api.post('/auth/logout').catch(() => {});
          // No usar window.location.href: eso causa page load completo y 404 en static sites.
          // useRequireAuth en hooks/useAuth.tsx redirige via React Router automaticamente.
          break;
        case 404:
          console.warn(`[API 404] Recurso no encontrado: ${error.config?.url}`, detail);
          break;
        case 409:
          console.warn(`[API 409] Conflicto: ${detail}`);
          break;
        case 422:
          console.warn(`[API 422] Error de validación:`, data?.detail || data);
          break;
        case 500:
          console.error(`[API 500] Error interno del servidor:`, detail);
          break;
        default:
          console.error(`[API ${status}] Error inesperado:`, detail);
      }
    } else if (error.request) {
      // Network error (no response received)
      console.error('[API] Error de red: no se pudo conectar con el servidor.', error.message);
    } else {
      console.error('[API] Error al realizar la solicitud:', error.message);
    }
    return Promise.reject(error);
  }
);

// Auth
export async function login(email: string, password: string) {
  const response = await api.post('/auth/login', { email, password });
  return response.data;
}

export async function getMe() {
  const response = await api.get('/auth/me');
  return response.data;
}

// Sources
export async function getSources(params?: {
  type?: string;
  country?: string;
  page?: number;
  per_page?: number;
}) {
  const response = await api.get('/sources', { params });
  return response.data;
}

export async function getSource(id: number) {
  const response = await api.get(`/sources/${id}`);
  return response.data;
}

export async function createSource(data: {
  name: string;
  type: string;
  config: Record<string, unknown>;
  country?: string;
  language?: string;
  fetch_interval?: number;
  priority?: number;
  auto_publish?: boolean;
  requires_approval?: boolean;
}) {
  const response = await api.post('/sources', data);
  return response.data;
}

export async function updateSource(
  id: number,
  data: Partial<{
    name: string;
    type: string;
    config: Record<string, unknown>;
    country: string;
    language: string;
    fetch_interval: number;
    priority: number;
    auto_publish: boolean;
    requires_approval: boolean;
    status: string;
  }>
) {
  const response = await api.put(`/sources/${id}`, data);
  return response.data;
}

export async function deleteSource(id: number) {
  const response = await api.delete(`/sources/${id}`);
  return response.data;
}

export async function pauseSource(id: number) {
  const response = await api.post(`/sources/${id}/pause`);
  return response.data;
}

export async function activateSource(id: number) {
  const response = await api.post(`/sources/${id}/activate`);
  return response.data;
}

// Categories
export async function getCategories() {
  const response = await api.get('/categories');
  return response.data;
}

export async function createCategory(data: {
  name: string;
  slug: string;
  description?: string;
  color?: string;
}) {
  const response = await api.post('/categories', data);
  return response.data;
}

export async function updateCategory(
  id: number,
  data: Partial<{
    name: string;
    slug: string;
    description: string;
    color: string;
  }>
) {
  const response = await api.put(`/categories/${id}`, data);
  return response.data;
}

export async function deleteCategory(id: number) {
  const response = await api.delete(`/categories/${id}`);
  return response.data;
}

// News
export async function getNews(params?: {
  status?: string;
  source_id?: number;
  category_id?: number;
  page?: number;
  per_page?: number;
}) {
  const response = await api.get('/news', { params });
  return response.data;
}

export async function getNewsItem(id: number) {
  const response = await api.get(`/news/${id}`);
  return response.data;
}

// Approval Queue
export async function getApprovalQueue(params?: {
  page?: number;
  per_page?: number;
}) {
  const response = await api.get('/news/approval-queue', { params });
  return response.data;
}

export async function approveNews(
  id: number,
  data?: { title?: string; summary?: string; category_id?: number }
) {
  const response = await api.post(`/news/${id}/approve`, data);
  return response.data;
}

export async function rejectNews(id: number, reason?: string) {
  const response = await api.post(`/news/${id}/reject`, { reason });
  return response.data;
}

export async function approveAllNews() {
  const response = await api.post('/news/approve-all');
  return response.data;
}

// Stats
export async function getStats() {
  const response = await api.get('/stats');
  return response.data;
}

// Settings (System Config)
export async function getSystemConfig() {
  const response = await api.get('/system-config');
  return response.data;
}

export async function updateSystemConfig(
  key: string,
  value: string | number | boolean
) {
  const response = await api.put(`/system-config/${key}`, { value });
  return response.data;
}

// Telegram Channels
export async function getTelegramChannels() {
  const response = await api.get('/telegram-channels');
  return response.data;
}

export async function createTelegramChannel(data: {
  name: string;
  channel_id: string;
  is_active?: boolean;
}) {
  const response = await api.post('/telegram-channels', data);
  return response.data;
}

export async function deleteTelegramChannel(id: number) {
  const response = await api.delete(`/telegram-channels/${id}`);
  return response.data;
}

export async function scrapeNow() {
  const response = await api.post('/news/scrape-now');
  return response.data;
}

export default api;
