import { get, patch, post } from '@/services/api';
import type { Alert } from '@/utils/types';

// Lightweight event bus so the unread badge (Sidebar) can refresh after alerts are
// marked read elsewhere — even when the route doesn't change (e.g. on /alerts itself).
const ALERTS_CHANGED_EVENT = 'alerts:changed';

export const notifyAlertsChanged = () => {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(ALERTS_CHANGED_EVENT));
  }
};

export const onAlertsChanged = (handler: () => void) => {
  if (typeof window === 'undefined') return () => {};
  window.addEventListener(ALERTS_CHANGED_EVENT, handler);
  return () => window.removeEventListener(ALERTS_CHANGED_EVENT, handler);
};

export const getAlerts = (unread?: boolean) =>
  get<Alert[]>('/alerts/', unread ? { params: { unread: true } } : undefined);

export const markAlertRead = async (id: string, isRead = true) => {
  const result = await patch<Alert>(`/alerts/${id}`, { is_read: isRead });
  notifyAlertsChanged();
  return result;
};

export const markAllAlertsRead = async () => {
  const result = await post<number>('/alerts/mark-all-read');
  notifyAlertsChanged();
  return result;
};

export const getUnreadCount = () => get<{ count: number }>('/alerts/unread-count');
