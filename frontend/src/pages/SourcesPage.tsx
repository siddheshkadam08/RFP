import { Globe, PencilLine, Plus, Save, X } from 'lucide-react';
import { FormEvent, useEffect, useMemo, useState } from 'react';

import EmptyState from '@/components/common/EmptyState';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import { get, getApiErrorMessage, patch, post } from '@/services/api';
import type { Source } from '@/utils/types';

const emptySourceForm = {
  name: '',
  url: '',
  source_type: 'website',
  frequency: 'daily',
};

const SourcesPage = () => {
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingSource, setEditingSource] = useState<Source | null>(null);
  const [formValues, setFormValues] = useState(emptySourceForm);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const loadSources = async () => {
      setLoading(true);
      setError('');

      try {
        const response = await get<Source[]>('/sources/');
        setSources(response);
      } catch (loadError) {
        setError(getApiErrorMessage(loadError, 'Unable to load sources.'));
      } finally {
        setLoading(false);
      }
    };

    void loadSources();
  }, []);

  const openCreateModal = () => {
    setEditingSource(null);
    setFormValues(emptySourceForm);
    setIsModalOpen(true);
  };

  const openEditModal = (source: Source) => {
    setEditingSource(source);
    setFormValues({
      name: source.name,
      url: source.url,
      source_type: source.source_type,
      frequency: source.frequency,
    });
    setIsModalOpen(true);
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setEditingSource(null);
    setFormValues(emptySourceForm);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError('');

    try {
      if (editingSource) {
        const updated = await patch<Source>(`/sources/${editingSource.id}`, formValues);
        setSources((current) => current.map((source) => (source.id === updated.id ? updated : source)));
      } else {
        const created = await post<Source>('/sources/', formValues);
        setSources((current) => [created, ...current]);
      }

      closeModal();
    } catch (submitError) {
      setError(getApiErrorMessage(submitError, 'Unable to save source.'));
    } finally {
      setSaving(false);
    }
  };

  const preparedSources = useMemo(
    () =>
      sources.map((source) => ({
        ...source,
        status: source.status ?? (source.is_active ? 'active' : 'paused'),
        success_rate: source.success_rate ?? 0,
      })),
    [sources],
  );

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h1 className="text-xl font-semibold text-slate-900">Source Management</h1>
            <p className="text-sm text-slate-500">Manage source coverage, crawl cadence, and quality metrics across your monitoring footprint.</p>
          </div>

          <button
            type="button"
            onClick={openCreateModal}
            className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-700"
          >
            <Plus className="h-4 w-4" />
            Add Source
          </button>
        </div>

        {error ? <div className="mt-5 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div> : null}

        <div className="mt-6">
          {loading ? (
            <LoadingSpinner label="Loading sources..." />
          ) : preparedSources.length ? (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead>
                  <tr className="text-left text-slate-500">
                    {['Name', 'URL', 'Type', 'Frequency', 'Status', 'Last Crawl', 'Success Rate', 'Actions'].map((column) => (
                      <th key={column} className="pb-3 font-medium">
                        {column}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {preparedSources.map((source) => (
                    <tr key={source.id} className="text-slate-700">
                      <td className="py-4 pr-4 font-medium text-slate-900">{source.name}</td>
                      <td className="py-4 pr-4 text-blue-600">{source.url}</td>
                      <td className="py-4 pr-4 capitalize">{source.source_type}</td>
                      <td className="py-4 pr-4 capitalize">{source.frequency}</td>
                      <td className="py-4 pr-4">
                        <span
                          className={[
                            'inline-flex rounded-full px-3 py-1 text-xs font-medium ring-1 ring-inset',
                            source.status === 'active'
                              ? 'bg-emerald-50 text-emerald-700 ring-emerald-200'
                              : source.status === 'paused'
                                ? 'bg-amber-50 text-amber-700 ring-amber-200'
                                : 'bg-rose-50 text-rose-700 ring-rose-200',
                          ].join(' ')}
                        >
                          {source.status}
                        </span>
                      </td>
                      <td className="py-4 pr-4">{source.last_crawled_at ? new Date(source.last_crawled_at).toLocaleString() : 'Never'}</td>
                      <td className="py-4 pr-4">
                        <div className="w-40">
                          <div className="h-2 rounded-full bg-slate-100">
                            <div className="h-2 rounded-full bg-blue-600" style={{ width: `${Math.min(source.success_rate ?? 0, 100)}%` }} />
                          </div>
                          <p className="mt-2 text-xs text-slate-500">{(source.success_rate ?? 0).toFixed(0)}%</p>
                        </div>
                      </td>
                      <td className="py-4">
                        <button
                          type="button"
                          onClick={() => openEditModal(source)}
                          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
                        >
                          <PencilLine className="h-4 w-4" />
                          Edit
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState icon={Globe} title="No sources configured" description="Add a source to start monitoring procurement portals, regulators, and multilateral institutions." />
          )}
        </div>
      </section>

      {isModalOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 px-4">
          <div className="w-full max-w-xl rounded-3xl bg-white p-6 shadow-2xl">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-xl font-semibold text-slate-900">{editingSource ? 'Edit Source' : 'Add Source'}</h2>
                <p className="text-sm text-slate-500">Configure source metadata and crawl cadence.</p>
              </div>
              <button type="button" onClick={closeModal} className="rounded-xl p-2 text-slate-500 transition hover:bg-slate-100">
                <X className="h-5 w-5" />
              </button>
            </div>

            <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
              <label className="block space-y-2 text-sm font-medium text-slate-700">
                <span>Name</span>
                <input
                  value={formValues.name}
                  onChange={(event) => setFormValues((current) => ({ ...current, name: event.target.value }))}
                  className="w-full rounded-xl border border-slate-200 px-3 py-2.5 outline-none focus:border-blue-500"
                  required
                />
              </label>
              <label className="block space-y-2 text-sm font-medium text-slate-700">
                <span>URL</span>
                <input
                  type="url"
                  value={formValues.url}
                  onChange={(event) => setFormValues((current) => ({ ...current, url: event.target.value }))}
                  className="w-full rounded-xl border border-slate-200 px-3 py-2.5 outline-none focus:border-blue-500"
                  required
                />
              </label>
              <div className="grid gap-4 sm:grid-cols-2">
                <label className="block space-y-2 text-sm font-medium text-slate-700">
                  <span>Type</span>
                  <select
                    value={formValues.source_type}
                    onChange={(event) => setFormValues((current) => ({ ...current, source_type: event.target.value }))}
                    className="w-full rounded-xl border border-slate-200 px-3 py-2.5 outline-none focus:border-blue-500"
                  >
                    <option value="website">Website</option>
                    <option value="api">API</option>
                    <option value="portal">Portal</option>
                    <option value="newsletter">Newsletter</option>
                  </select>
                </label>
                <label className="block space-y-2 text-sm font-medium text-slate-700">
                  <span>Frequency</span>
                  <select
                    value={formValues.frequency}
                    onChange={(event) => setFormValues((current) => ({ ...current, frequency: event.target.value }))}
                    className="w-full rounded-xl border border-slate-200 px-3 py-2.5 outline-none focus:border-blue-500"
                  >
                    <option value="hourly">Hourly</option>
                    <option value="daily">Daily</option>
                    <option value="weekly">Weekly</option>
                    <option value="monthly">Monthly</option>
                  </select>
                </label>
              </div>

              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={closeModal}
                  className="rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-70"
                >
                  <Save className="h-4 w-4" />
                  {saving ? 'Saving...' : 'Save Source'}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default SourcesPage;
