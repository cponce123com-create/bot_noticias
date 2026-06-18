import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || '/api/v1';

const api = axios.create({
  baseURL: API_BASE.endsWith('/api/v1') ? API_BASE : `${API_BASE}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      window.location.href = '/login';
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

export default api;
