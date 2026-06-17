import { Bot, History, Settings2, Shield } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import Badge from '@/components/common/Badge';
import EmptyState from '@/components/common/EmptyState';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import { get, getApiErrorMessage, patch } from '@/services/api';
import type { User } from '@/utils/types';

interface AuditLogEntry {
  id: string;
  actor: string;
  action: string;
  target: string;
  created_at: string;
}

const AdminPage = () => {
  const [activeTab, setActiveTab] = useState<'users' | 'ai' | 'system'>('users');
  const [users, setUsers] = useState<User[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogEntry[]>([]);
  const [auditFilter, setAuditFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const loadAdminData = async () => {
      setLoading(true);
      setError('');

      try {
        const [usersResponse, auditResponse] = await Promise.all([
          get<User[]>('/admin/users'),
          get<AuditLogEntry[]>('/admin/audit-logs'),
        ]);
        setUsers(usersResponse);
        setAuditLogs(auditResponse);
      } catch (loadError) {
        setError(getApiErrorMessage(loadError, 'Unable to load admin data.'));
      } finally {
        setLoading(false);
      }
    };

    void loadAdminData();
  }, []);

  const filteredAuditLogs = useMemo(
    () => auditLogs.filter((item) => `${item.actor} ${item.action} ${item.target}`.toLowerCase().includes(auditFilter.toLowerCase())),
    [auditFilter, auditLogs],
  );

  const updateRole = async (userId: string, role: string) => {
    try {
      const updatedUser = await patch<User>(`/admin/users/${userId}`, { role });
      setUsers((current) => current.map((user) => (user.id === userId ? updatedUser : user)));
    } catch (roleError) {
      setError(getApiErrorMessage(roleError, 'Unable to update user role.'));
    }
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Admin Panel</h1>
          <p className="text-sm text-slate-500">Manage user access, AI controls, and operational audit visibility.</p>
        </div>

        <div className="inline-flex rounded-2xl bg-slate-100 p-1">
          {[
            { label: 'Users', value: 'users' as const },
            { label: 'AI Settings', value: 'ai' as const },
            { label: 'System', value: 'system' as const },
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
      </div>

      {error ? <div className="mt-5 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div> : null}

      <div className="mt-6">
        {loading ? (
          <LoadingSpinner label="Loading admin workspace..." />
        ) : activeTab === 'users' ? (
          users.length ? (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead>
                  <tr className="text-left text-slate-500">
                    {['Name', 'Email', 'Role', 'Status', 'Last Login'].map((column) => (
                      <th key={column} className="pb-3 font-medium">
                        {column}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {users.map((user) => (
                    <tr key={user.id} className="text-slate-700">
                      <td className="py-4 pr-4 font-medium text-slate-900">{user.full_name}</td>
                      <td className="py-4 pr-4">{user.email}</td>
                      <td className="py-4 pr-4">
                        <select
                          value={user.role}
                          onChange={(event) => void updateRole(user.id, event.target.value)}
                          className="rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-blue-500"
                        >
                          {['admin', 'manager', 'analyst', 'viewer'].map((role) => (
                            <option key={role} value={role}>
                              {role}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="py-4 pr-4">
                        <Badge text={user.is_active ? 'Active' : 'Inactive'} variant={user.is_active ? 'success' : 'neutral'} />
                      </td>
                      <td className="py-4">{user.last_login ? new Date(user.last_login).toLocaleString() : 'Never'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState icon={Shield} title="No users found" description="User accounts will appear here once authentication provisioning is connected." />
          )
        ) : activeTab === 'ai' ? (
          <div className="grid gap-5 xl:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
              <div className="flex items-center gap-3">
                <div className="rounded-xl bg-blue-50 p-2 text-blue-600">
                  <Bot className="h-5 w-5" />
                </div>
                <h2 className="text-lg font-semibold text-slate-900">Model Configuration</h2>
              </div>
              <dl className="mt-4 space-y-3 text-sm text-slate-600">
                <div className="flex items-center justify-between gap-4">
                  <dt>Primary model</dt>
                  <dd className="font-medium text-slate-900">GPT-4 / Claude</dd>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <dt>Retrieval strategy</dt>
                  <dd className="font-medium text-slate-900">Hybrid semantic + keyword</dd>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <dt>Confidence threshold</dt>
                  <dd className="font-medium text-slate-900">0.72</dd>
                </div>
              </dl>
            </div>

            <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-5">
              <div className="flex items-center gap-3">
                <div className="rounded-xl bg-slate-100 p-2 text-slate-700">
                  <Settings2 className="h-5 w-5" />
                </div>
                <h2 className="text-lg font-semibold text-slate-900">Prompt Templates</h2>
              </div>
              <p className="mt-4 text-sm leading-7 text-slate-600">
                Prompt template management will surface reusable evaluation, summarization, and regional comparison prompts here.
              </p>
            </div>
          </div>
        ) : (
          <div className="space-y-5">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">Audit Log Viewer</h2>
                <p className="text-sm text-slate-500">Filter operational changes across users, AI settings, and system events.</p>
              </div>
              <input
                value={auditFilter}
                onChange={(event) => setAuditFilter(event.target.value)}
                placeholder="Filter audit logs"
                className="w-full max-w-sm rounded-xl border border-slate-200 px-4 py-2.5 text-sm outline-none focus:border-blue-500"
              />
            </div>

            {filteredAuditLogs.length ? (
              <div className="space-y-3">
                {filteredAuditLogs.map((entry) => (
                  <div key={entry.id} className="flex items-start gap-4 rounded-2xl border border-slate-200 p-4">
                    <div className="rounded-xl bg-slate-100 p-3 text-slate-700">
                      <History className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-slate-900">{entry.actor}</p>
                      <p className="mt-1 text-sm text-slate-600">{entry.action} — {entry.target}</p>
                      <p className="mt-2 text-xs text-slate-500">{new Date(entry.created_at).toLocaleString()}</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState icon={History} title="No audit events found" description="Audit entries will appear here when administrative actions are recorded." />
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default AdminPage;
