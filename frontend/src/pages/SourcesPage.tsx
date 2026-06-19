import { Globe, Loader2, PencilLine, Plus, Radar, Save, X } from 'lucide-react';
import { FormEvent, useEffect, useMemo, useState } from 'react';

import EmptyState from '@/components/common/EmptyState';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import { get, getApiErrorMessage, patch, post } from '@/services/api';
import type { Source } from '@/utils/types';

type SourceOptions = {
  source_types: string[];
  frequencies: string[];
  domains: string[];
  regions: string[];
  countries: string[];
  country_regions: Record<string, string>;
};

// Result of POST /sources/detect-location.
type DetectResult = {
  country?: string | null;
  region?: string | null;
  method?: string;
};

// Used until GET /sources/options resolves. Kept in sync with the backend
// SourceType / CrawlFrequency / SourceDomain enums and SOURCE_REGIONS list.
const fallbackOptions: SourceOptions = {
  source_types: [
    'regulator_website',
    'tender_portal',
    'procurement_system',
    'government_website',
    'press_release',
    'rss_feed',
    'pdf',
    'annual_report',
    'news_feed',
    'funding_portal',
    'other',
  ],
  frequencies: ['hourly', 'daily', 'weekly', 'monthly'],
  domains: [
    'central_bank',
    'deposit_insurer',
    'business_registry',
    'capital_market',
    'stock_exchange',
    'tax_authority',
    'statistical_body',
    'local_government',
    'other',
  ],
  regions: [
    'North America',
    'Latin America & Caribbean',
    'Europe',
    'Middle East & North Africa',
    'Sub-Saharan Africa',
    'Asia Pacific',
    'South Asia',
    'Global',
  ],
  // Small resilient fallback; the full list arrives from GET /sources/options.
  countries: [
    'United States',
    'Canada',
    'United Kingdom',
    'Germany',
    'France',
    'India',
    'Singapore',
    'Australia',
    'United Arab Emirates',
    'Saudi Arabia',
    'Nigeria',
    'South Africa',
    'Kenya',
    'Brazil',
    'Japan',
    'China',
  ],
  country_regions: {
    'United States': 'North America',
    Canada: 'North America',
    'United Kingdom': 'Europe',
    Germany: 'Europe',
    France: 'Europe',
    India: 'South Asia',
    Singapore: 'Asia Pacific',
    Australia: 'Asia Pacific',
    'United Arab Emirates': 'Middle East & North Africa',
    'Saudi Arabia': 'Middle East & North Africa',
    Nigeria: 'Sub-Saharan Africa',
    'South Africa': 'Sub-Saharan Africa',
    Kenya: 'Sub-Saharan Africa',
    Brazil: 'Latin America & Caribbean',
    Japan: 'Asia Pacific',
    China: 'Asia Pacific',
  },
};

// Turn an enum-style value ("regulator_website") into a label ("Regulator Website").
const humanize = (value: string) => value.replace(/[_-]+/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());

// Shared modal-form styling.
const fieldClass =
  'w-full rounded-xl border border-slate-200 px-3 py-2.5 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100';
const labelClass = 'block space-y-2 text-sm font-medium text-slate-700';
const sectionClass = 'text-xs font-semibold uppercase tracking-wider text-slate-400';

const emptySourceForm = {
  name: '',
  url: '',
  source_type: '',
  frequency: 'daily',
  domain: '',
  country: '',
  region: '',
};

// Shape returned by POST /sources/{id}/crawl (the ingest summary).
type CrawlSummary = {
  status?: string;
  relevant?: boolean;
  reason?: string;
  error?: string;
  documents_created?: number;
  opportunities_created?: number;
  score?: number;
};

// Turn an ingest summary into a friendly one-line message for the row.
const crawlMessage = (summary: CrawlSummary): string => {
  if (summary.status === 'failed') {
    return `Crawl failed: ${summary.error ?? 'unknown error'}`;
  }
  if (summary.status === 'skipped') {
    return 'Already crawled — no changes since last time.';
  }
  if (summary.opportunities_created && summary.opportunities_created > 0) {
    const scorePart = typeof summary.score === 'number' ? ` (score ${summary.score})` : '';
    return `✓ ${summary.opportunities_created} opportunity created${scorePart}.`;
  }
  if (summary.relevant === false) {
    return 'No relevant opportunity found on this page.';
  }
  return 'Crawl complete.';
};

const SourcesPage = () => {
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingSource, setEditingSource] = useState<Source | null>(null);
  const [formValues, setFormValues] = useState(emptySourceForm);
  const [saving, setSaving] = useState(false);
  const [options, setOptions] = useState<SourceOptions>(fallbackOptions);
  const [crawlingId, setCrawlingId] = useState<string | null>(null);
  const [crawlingAll, setCrawlingAll] = useState(false);
  const [crawlResults, setCrawlResults] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState('');
  const [detecting, setDetecting] = useState(false);
  const [detectMsg, setDetectMsg] = useState('');

  const countryOptions = useMemo(() => {
    const all = new Set(options.countries);
    if (formValues.country) {
      all.add(formValues.country);
    }
    return Array.from(all).sort((a, b) => a.localeCompare(b));
  }, [options.countries, formValues.country]);

  useEffect(() => {
    const loadOptions = async () => {
      try {
        const response = await get<SourceOptions>('/sources/options');
        setOptions({ ...fallbackOptions, ...response });
      } catch {
        // Keep the fallback options if the endpoint is unavailable.
      }
    };

    void loadOptions();
  }, []);

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
    setDetectMsg('');
    setIsModalOpen(true);
  };

  const openEditModal = (source: Source) => {
    setEditingSource(source);
    setFormValues({
      name: source.name,
      url: source.url,
      source_type: source.source_type,
      frequency: source.frequency,
      domain: source.domain ?? '',
      country: source.country ?? '',
      region: source.region ?? '',
    });
    setDetectMsg('');
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

    // Omit domain when blank — it is optional and '' is not a valid enum value.
    const payload = {
      name: formValues.name,
      url: formValues.url,
      source_type: formValues.source_type,
      frequency: formValues.frequency,
      region: formValues.region,
      ...(formValues.domain ? { domain: formValues.domain } : {}),
      ...(formValues.country ? { country: formValues.country } : {}),
    };

    try {
      if (editingSource) {
        const updated = await patch<Source>(`/sources/${editingSource.id}`, payload);
        setSources((current) => current.map((source) => (source.id === updated.id ? updated : source)));
      } else {
        const created = await post<Source>('/sources/', payload);
        setSources((current) => [created, ...current]);
      }

      closeModal();
    } catch (submitError) {
      setError(getApiErrorMessage(submitError, 'Unable to save source.'));
    } finally {
      setSaving(false);
    }
  };

  const refreshSources = async () => {
    try {
      const response = await get<Source[]>('/sources/');
      setSources(response);
    } catch {
      // Ignore refresh errors; the crawl result message is still shown.
    }
  };

  const handleCrawl = async (source: Source) => {
    setCrawlingId(source.id);
    setCrawlResults((current) => ({ ...current, [source.id]: '' }));

    try {
      const summary = await post<CrawlSummary>(`/sources/${source.id}/crawl`, {});
      setCrawlResults((current) => ({ ...current, [source.id]: crawlMessage(summary) }));
      await refreshSources();
    } catch (crawlError) {
      setCrawlResults((current) => ({ ...current, [source.id]: getApiErrorMessage(crawlError, 'Crawl failed.') }));
    } finally {
      setCrawlingId(null);
    }
  };

  const handleCrawlAll = async () => {
    setCrawlingAll(true);
    setNotice('');
    setError('');

    try {
      const summary = await post<{ sources_crawled: number; opportunities_created: number }>('/sources/crawl-all', {});
      setNotice(`Crawled ${summary.sources_crawled} source(s) — ${summary.opportunities_created} opportunity(ies) created.`);
      await refreshSources();
    } catch (crawlError) {
      setError(getApiErrorMessage(crawlError, 'Unable to crawl sources.'));
    } finally {
      setCrawlingAll(false);
    }
  };

  const handleDetect = async () => {
    if (!formValues.url) {
      setDetectMsg('Enter a URL first.');
      return;
    }
    setDetecting(true);
    setDetectMsg('Detecting…');

    try {
      const result = await post<DetectResult>('/sources/detect-location', { url: formValues.url });
      setFormValues((current) => ({
        ...current,
        country: result.country ?? current.country,
        region: result.region ?? current.region,
      }));

      if (result.country || result.region) {
        const parts = [result.country, result.region].filter(Boolean).join(' · ');
        setDetectMsg(`Detected: ${parts}${result.method === 'ai' ? ' (via AI)' : ''}`);
      } else {
        setDetectMsg('Could not detect — please pick Country/Region manually.');
      }
    } catch (detectError) {
      setDetectMsg(getApiErrorMessage(detectError, 'Detection failed.'));
    } finally {
      setDetecting(false);
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

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={handleCrawlAll}
              disabled={crawlingAll}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-70"
            >
              {crawlingAll ? <Loader2 className="h-4 w-4 animate-spin" /> : <Radar className="h-4 w-4" />}
              {crawlingAll ? 'Crawling…' : 'Crawl all'}
            </button>
            <button
              type="button"
              onClick={openCreateModal}
              className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-700"
            >
              <Plus className="h-4 w-4" />
              Add Source
            </button>
          </div>
        </div>

        {error ? <div className="mt-5 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div> : null}
        {notice ? <div className="mt-5 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{notice}</div> : null}

        <div className="mt-6">
          {loading ? (
            <LoadingSpinner label="Loading sources..." />
          ) : preparedSources.length ? (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead>
                  <tr className="text-left text-slate-500">
                    {['Name', 'URL', 'Type', 'Frequency', 'Domain', 'Country', 'Region', 'Status', 'Last Crawl', 'Success Rate', 'Actions'].map((column) => (
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
                      <td className="py-4 pr-4">{humanize(source.source_type)}</td>
                      <td className="py-4 pr-4">{humanize(source.frequency)}</td>
                      <td className="py-4 pr-4">{source.domain ? humanize(source.domain) : '—'}</td>
                      <td className="py-4 pr-4">{source.country ?? '—'}</td>
                      <td className="py-4 pr-4">{source.region ?? '—'}</td>
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
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            onClick={() => handleCrawl(source)}
                            disabled={crawlingId === source.id}
                            className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-70"
                          >
                            {crawlingId === source.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Radar className="h-4 w-4" />}
                            {crawlingId === source.id ? 'Crawling…' : 'Crawl'}
                          </button>
                          <button
                            type="button"
                            onClick={() => openEditModal(source)}
                            className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
                          >
                            <PencilLine className="h-4 w-4" />
                            Edit
                          </button>
                        </div>
                        {crawlResults[source.id] ? (
                          <p className="mt-2 max-w-xs text-xs text-slate-500">{crawlResults[source.id]}</p>
                        ) : null}
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
          <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-3xl bg-white p-6 shadow-2xl">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-50 text-blue-600">
                  <Globe className="h-5 w-5" />
                </div>
                <div>
                  <h2 className="text-xl font-semibold text-slate-900">{editingSource ? 'Edit Source' : 'Add Source'}</h2>
                  <p className="text-sm text-slate-500">Configure source metadata, coverage, and crawl cadence.</p>
                </div>
              </div>
              <button type="button" onClick={closeModal} className="rounded-xl p-2 text-slate-500 transition hover:bg-slate-100">
                <X className="h-5 w-5" />
              </button>
            </div>

            <form className="mt-6 space-y-6" onSubmit={handleSubmit}>
              {/* Source details */}
              <div className="space-y-4">
                <p className={sectionClass}>Source details</p>
                <label className={labelClass}>
                  <span>Name</span>
                  <input
                    value={formValues.name}
                    onChange={(event) => setFormValues((current) => ({ ...current, name: event.target.value }))}
                    className={fieldClass}
                    placeholder="e.g. SEC Press Releases"
                    required
                  />
                </label>
                <div className="space-y-2">
                  <label className={labelClass}>
                    <span>URL</span>
                    <input
                      type="url"
                      value={formValues.url}
                      onChange={(event) => setFormValues((current) => ({ ...current, url: event.target.value }))}
                      className={fieldClass}
                      placeholder="https://…"
                      required
                    />
                  </label>
                  <div className="flex flex-wrap items-center gap-3">
                    <button
                      type="button"
                      onClick={handleDetect}
                      disabled={detecting || !formValues.url}
                      className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-70"
                    >
                      {detecting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Globe className="h-3.5 w-3.5" />}
                      Detect country &amp; region from URL
                    </button>
                    {detectMsg ? <span className="text-xs text-slate-500">{detectMsg}</span> : null}
                  </div>
                </div>
              </div>

              {/* Classification */}
              <div className="space-y-4 border-t border-slate-100 pt-5">
                <p className={sectionClass}>Classification</p>
                <div className="grid gap-4 sm:grid-cols-2">
                  <label className={labelClass}>
                    <span>Type</span>
                    <select
                      value={formValues.source_type}
                      onChange={(event) => setFormValues((current) => ({ ...current, source_type: event.target.value }))}
                      className={fieldClass}
                      required
                    >
                      <option value="" disabled>
                        Select type
                      </option>
                      {options.source_types.map((value) => (
                        <option key={value} value={value}>
                          {humanize(value)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className={labelClass}>
                    <span>
                      Domain <span className="font-normal text-slate-400">(optional)</span>
                    </span>
                    <select
                      value={formValues.domain}
                      onChange={(event) => setFormValues((current) => ({ ...current, domain: event.target.value }))}
                      className={fieldClass}
                    >
                      <option value="">Select domain</option>
                      {options.domains.map((value) => (
                        <option key={value} value={value}>
                          {humanize(value)}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              </div>

              {/* Coverage */}
              <div className="space-y-4 border-t border-slate-100 pt-5">
                <p className={sectionClass}>Coverage</p>
                <div className="grid gap-4 sm:grid-cols-2">
                  <label className={labelClass}>
                    <span>
                      Country <span className="font-normal text-slate-400">(optional)</span>
                    </span>
                    <select
                      value={formValues.country}
                      onChange={(event) => {
                        const value = event.target.value;
                        setFormValues((current) => ({
                          ...current,
                          country: value,
                          region: options.country_regions[value] ?? current.region,
                        }));
                      }}
                      className={fieldClass}
                    >
                      <option value="">Select country</option>
                      {countryOptions.map((value) => (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className={labelClass}>
                    <span>Region</span>
                    <select
                      value={formValues.region}
                      onChange={(event) => setFormValues((current) => ({ ...current, region: event.target.value }))}
                      className={fieldClass}
                      required
                    >
                      <option value="" disabled>
                        Select region
                      </option>
                      {options.regions.map((value) => (
                        <option key={value} value={value}>
                          {value}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              </div>

              {/* Crawl schedule */}
              <div className="space-y-4 border-t border-slate-100 pt-5">
                <p className={sectionClass}>Crawl schedule</p>
                <label className={labelClass}>
                  <span>Frequency</span>
                  <select
                    value={formValues.frequency}
                    onChange={(event) => setFormValues((current) => ({ ...current, frequency: event.target.value }))}
                    className={fieldClass}
                    required
                  >
                    {options.frequencies.map((value) => (
                      <option key={value} value={value}>
                        {humanize(value)}
                      </option>
                    ))}
                  </select>
                  <span className="block text-xs font-normal text-slate-400">How often this source is checked for new opportunities.</span>
                </label>
              </div>

              {/* Actions */}
              <div className="flex justify-end gap-3 border-t border-slate-100 pt-5">
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
                  {saving ? 'Saving…' : 'Save Source'}
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
