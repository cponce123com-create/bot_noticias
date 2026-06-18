import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return new Intl.DateTimeFormat('es-PE', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

export function truncate(text: string, length: number = 100): string {
  if (text.length <= length) return text;
  return text.substring(0, length) + '...';
}

export function getStatusColor(status: string): string {
  const colors: Record<string, string> = {
    active: 'success',
    published: 'success',
    approved: 'success',
    paused: 'warning',
    pending: 'warning',
    draft: 'gray',
    rejected: 'danger',
    inactive: 'danger',
    error: 'danger',
  };
  return colors[status] || 'gray';
}

export function getStatusText(status: string): string {
  const texts: Record<string, string> = {
    active: 'Activo',
    published: 'Publicado',
    approved: 'Aprobado',
    paused: 'Pausado',
    pending: 'Pendiente',
    draft: 'Borrador',
    rejected: 'Rechazado',
    inactive: 'Inactivo',
    error: 'Error',
    processing: 'Procesando',
    fetched: 'Obtenido',
  };
  return texts[status] || status;
}
