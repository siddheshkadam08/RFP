import { AlertCircle, Bell, BellDot, CheckCheck, ShieldAlert } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import Badge from '@/components/common/Badge';
import EmptyState from '@/components/common/EmptyState';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import { getApiErrorMessage } from '@/services/api';
import { getAlerts, markAlertRead, markAllAlertsRead } from '@/services/alerts';
import type { Alert } from '@/utils/types';

const AlertsPage = () => {
  const [activeTab, setActiveTab] = useState<'unread' | 'all'>('unread');
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const loadAlerts = async () => {
      setLoading(true);
      setError('');

      try {
        const response = await getAlerts();
        setAlerts(response);
      } catch (loadError) {
        setError(getApiErrorMessage(loadError, 'Unable to load alerts.'));
      } finally {
        setLoading(false);
      }
    };

    void loadAlerts();
  }, []);

  const visibleAlerts = useMemo(
    () => (activeTab === 'unread' ? alerts.filter((alert) => !alert.is_read) : alerts),
    [activeTab, alerts],
  );

  const markAllRead = async () => {
    setError('');
    setAlerts((current) => current.map((alert) => ({ ...alert, is_read: true })));
    try {
      await markAllAlertsRead();
    } catch (markError) {
      setError(getApiErrorMessage(markError, 'Unable to mark all alerts as read.'));
    }
  };

  const markRead = async (alertId: string) => {
    setError('');
    setAlerts((current) => current.map((alert) => (alert.id === alertId ? { ...alert, is_read: true } : alert)));
    try {
      await markAlertRead(alertId, true);
    } catch (markError) {
      setError(getApiErrorMessage(markError, 'Unable to update the alert.'));
    }
  };

  const getAlertIcon = (type: string) => {
    if (type.includes('priority')) return ShieldAlert;
    if (type.includes('system')) return AlertCircle;
    return BellDot;
  };

  const getSeverityVariant = (severity?: Alert['severity']) => {
    if (severity === 'critical' || severity === 'high') return 'danger';
    if (severity === 'medium') return 'warning';
    if (severity === 'low') return 'info';
    return 'neutral';
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Alerts</h1>
          <p className="text-sm text-slate-500">Review critical signals, score changes, and ingestion events as they happen.</p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="inline-flex rounded-2xl bg-slate-100 p-1">
            {[
              { label: 'Unread', value: 'unread' as const },
              { label: 'All', value: 'all' as const },
            ].map((tab) => (
              <button
                key={tab.value}
                type="button"
                onClick={() => setActiveTab(tab.value)}
                className={[
                  'rounded-xl px-4 py-2 text-sm font-medium transition',
                  activeTab === tab.value ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-600',
                ].join(' ')}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <button
            type="button"
            onClick={() => void markAllRead()}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
          >
            <CheckCheck className="h-4 w-4" />
            Mark all read
          </button>
        </div>
      </div>

      {error ? <div className="mt-5 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div> : null}

      <div className="mt-6">
        {loading ? (
          <LoadingSpinner label="Loading alerts..." />
        ) : visibleAlerts.length ? (
          <div className="space-y-3">
            {visibleAlerts.map((alert) => {
              const Icon = getAlertIcon(alert.type);

              return (
                <button
                  key={alert.id}
                  type="button"
                  onClick={() => {
                    if (!alert.is_read) void markRead(alert.id);
                  }}
                  className={[
                    'flex w-full items-start gap-4 rounded-2xl border px-5 py-4 text-left transition',
                    alert.is_read ? 'border-slate-200 bg-white' : 'border-blue-200 bg-blue-50/40',
                  ].join(' ')}
                >
                  <div className={['rounded-xl p-3', alert.is_read ? 'bg-slate-100 text-slate-600' : 'bg-white text-blue-600'].join(' ')}>
                    <Icon className="h-5 w-5" />
                  </div>
                  <div className="flex-1">
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                      <div>
                        <p className="text-sm font-semibold text-slate-900">{alert.title || alert.message}</p>
                        <p className="mt-1 text-sm leading-6 text-slate-600">{alert.message}</p>
                      </div>
                      <div className="flex items-center gap-3">
                        <Badge text={alert.severity ?? 'info'} variant={getSeverityVariant(alert.severity)} />
                        <span className="text-xs text-slate-500">{new Date(alert.created_at).toLocaleString()}</span>
                      </div>
                    </div>
                    <div className="mt-3 flex items-center gap-2 text-xs font-medium text-slate-500">
                      <Bell className="h-4 w-4" />
                      {alert.is_read ? 'Read' : 'Unread'}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        ) : (
          <EmptyState icon={Bell} title="No alerts to review" description="Unread alerts will appear here when new signals, score shifts, or source issues are detected." />
        )}
      </div>
    </div>
  );
};

export default AlertsPage;
