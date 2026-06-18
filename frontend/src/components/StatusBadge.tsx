import { cn, getStatusColor, getStatusText } from '../lib/utils';

interface StatusBadgeProps {
  status: string;
  className?: string;
}

export default function StatusBadge({ status, className }: StatusBadgeProps) {
  const colorType = getStatusColor(status);

  const colorClasses: Record<string, string> = {
    success: 'bg-green-100 text-green-800',
    warning: 'bg-yellow-100 text-yellow-800',
    danger: 'bg-red-100 text-red-800',
    info: 'bg-blue-100 text-blue-800',
    gray: 'bg-gray-100 text-gray-800',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium',
        colorClasses[colorType] || colorClasses.gray,
        className
      )}
    >
      <span
        className={cn(
          'w-1.5 h-1.5 rounded-full mr-1.5',
          colorType === 'success' && 'bg-green-500',
          colorType === 'warning' && 'bg-yellow-500',
          colorType === 'danger' && 'bg-red-500',
          colorType === 'info' && 'bg-blue-500',
          colorType === 'gray' && 'bg-gray-500'
        )}
      />
      {getStatusText(status)}
    </span>
  );
}
