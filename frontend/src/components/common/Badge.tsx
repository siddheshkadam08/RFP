import { HTMLAttributes } from 'react';

import { scoreBand } from '@/utils/score';

export type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'neutral';
export type BadgeSize = 'sm' | 'md';

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  text: string;
  variant?: BadgeVariant;
  size?: BadgeSize;
}

const variantClasses: Record<BadgeVariant, string> = {
  success: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  warning: 'bg-amber-50 text-amber-700 ring-amber-200',
  danger: 'bg-rose-50 text-rose-700 ring-rose-200',
  info: 'bg-blue-50 text-blue-700 ring-blue-200',
  neutral: 'bg-slate-100 text-slate-700 ring-slate-200',
};

const sizeClasses: Record<BadgeSize, string> = {
  sm: 'px-2.5 py-1 text-xs',
  md: 'px-3 py-1.5 text-sm',
};

export const getScoreVariant = (score?: number | null): BadgeVariant => {
  const variants: Record<ReturnType<typeof scoreBand>, BadgeVariant> = {
    high: 'success',
    medium: 'warning',
    low: 'danger',
  };
  return variants[scoreBand(score)];
};

export const getStatusBadgeClass = (status: string) => {
  const normalized = status.toLowerCase();

  const classes: Record<string, string> = {
    signal_detected: 'bg-slate-100 text-slate-700 ring-slate-200',
    under_review: 'bg-blue-50 text-blue-700 ring-blue-200',
    qualified: 'bg-indigo-50 text-indigo-700 ring-indigo-200',
    active: 'bg-green-50 text-green-700 ring-green-200',
    pursuing: 'bg-orange-50 text-orange-700 ring-orange-200',
    closed_won: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
    closed_lost: 'bg-rose-50 text-rose-700 ring-rose-200',
    archived: 'bg-slate-100 text-slate-700 ring-slate-200',
  };

  return classes[normalized] ?? classes.signal_detected;
};

export const formatStatusLabel = (status: string) =>
  status
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');

const Badge = ({ text, variant = 'neutral', size = 'sm', className = '', ...rest }: BadgeProps) => (
  <span
    className={[
      'inline-flex items-center rounded-full font-medium ring-1 ring-inset',
      variantClasses[variant],
      sizeClasses[size],
      className,
    ].join(' ')}
    {...rest}
  >
    {text}
  </span>
);

export default Badge;
