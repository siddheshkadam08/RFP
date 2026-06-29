import { ArrowDownUp, ChevronLeft, ChevronRight, Download, Filter, Landmark, Search } from 'lucide-react';
import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import Badge, { formatStatusLabel, getStatusBadgeClass } from '@/components/common/Badge';
import EmptyState from '@/components/common/EmptyState';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import { getApiErrorMessage } from '@/services/api';
import { exportOpportunities, getOpportunityOptions, searchOpportunities, type OpportunityOptions } from '@/services/opportunities';
import { scoreBand as scoreBandLabel } from '@/utils/score';
import type { Opportunity, PaginatedResponse, SearchFilters } from '@/utils/types';

const labelize = (value: string) => value.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());

// Fallback until GET /opportunities/options resolves. Values MUST match the backend
// (OpportunityCategory / OpportunityStatus enums, geo regions, standards taxonomy).
const fallbackOptions: OpportunityOptions = {
  categories: ['suptech', 'regtech', 'analytics', 'risk', 'taxonomy', 'reporting', 'deposit_insurance', 'data_collection', 'workflow', 'validation'].map(
    (value) => ({ value, label: labelize(value) }),
  ),
  statuses: ['signal_detected', 'under_review', 'qualified', 'active', 'pursuing', 'closed_won', 'closed_lost', 'archived'].map((value) => ({
    value,
    label: labelize(value),
  })),
  regions: ['North America', 'Latin America & Caribbean', 'Europe', 'Middle East & North Africa', 'Sub-Saharan Africa', 'Asia Pacific', 'South Asia', 'Global'],
  countries: [],
  standards: ['XBRL', 'iXBRL', 'XBRL-CSV', 'XBRL-JSON', 'SDMX', 'ISO 20022', 'DPM', 'Taxonomies'],
};

const defaultFilters: SearchFilters = {
  query: '',
  regions: [],
  countries: [],
  categories: [],
  standards: [],
  status: [],
  page: 1,
  page_size: 12,
};

const sortOptions = [
  { value: 'updated_at', label: 'Recently updated' },
  { value: 'score', label: 'Score' },
  { value: 'title', label: 'Title' },
  { value: 'country', label: 'Country' },
  { value: 'status', label: 'Status' },
];

const getMultiSelectValues = (event: ChangeEvent<HTMLSelectElement>) =>
  Array.from(event.target.selectedOptions, (option) => option.value);

// Shared sidebar field styling.
const labelClass = 'block space-y-1.5 text-xs font-medium text-slate-600';
const fieldClass =
  'w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100';
const multiClass = 'min-h-24 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-900 outline-none focus:border-blue-500';

// Score-badge color band (spec doc04 §14: >=80 high, 50-79 medium, <50 low).
const scoreBand = (score?: number | null) =>
  ({
    high: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
    medium: 'bg-amber-50 text-amber-700 ring-amber-200',
    low: 'bg-rose-50 text-rose-700 ring-rose-200',
  })[scoreBandLabel(score)];

const OpportunityExplorerPage = () => {
  const navigate = useNavigate();
  const [draftFilters, setDraftFilters] = useState<SearchFilters>(defaultFilters);
  const [filters, setFilters] = useState<SearchFilters>(defaultFilters);
  const [results, setResults] = useState<PaginatedResponse<Opportunity> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [options, setOptions] = useState<OpportunityOptions>(fallbackOptions);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    const loadOptions = async () => {
      try {
        const response = await getOpportunityOptions();
        setOptions({ ...fallbackOptions, ...response });
      } catch {
        // Keep the fallback options if the endpoint is unavailable.
      }
    };

    void loadOptions();
  }, []);

  useEffect(() => {
    const loadOpportunities = async () => {
      setLoading(true);
      setError('');

      try {
        const response = await searchOpportunities(filters);
        setResults(response);
      } catch (loadError) {
        setError(getApiErrorMessage(loadError, 'Unable to fetch opportunities.'));
      } finally {
        setLoading(false);
      }
    };

    void loadOpportunities();
  }, [filters]);

  const totalPages = useMemo(() => {
    if (!results) {
      return 1;
    }

    return Math.max(1, Math.ceil(results.total / results.page_size));
  }, [results]);

  const applyFilters = (event?: FormEvent) => {
    event?.preventDefault();
    setFilters((current) => ({ ...draftFilters, sort_by: current.sort_by, sort_dir: current.sort_dir, page: 1, page_size: current.page_size ?? 12 }));
  };

  const clearFilters = () => {
    setDraftFilters(defaultFilters);
    setFilters({ ...defaultFilters });
  };

  const goToPage = (page: number) => {
    setFilters((current) => ({ ...current, page }));
  };

  const setSortField = (sortKey: string) => {
    setFilters((current) => ({ ...current, sort_by: sortKey, page: 1 }));
  };

  const toggleSortDir = () => {
    setFilters((current) => ({ ...current, sort_dir: current.sort_dir === 'asc' ? 'desc' : 'asc', page: 1 }));
  };

  const handleExport = async () => {
    setExporting(true);
    setError('');

    try {
      const blob = await exportOpportunities({ ...filters, page: 1, page_size: 10000 });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'opportunities.xlsx';
      link.click();
      URL.revokeObjectURL(url);
    } catch (exportError) {
      setError(getApiErrorMessage(exportError, 'Unable to export opportunities.'));
    } finally {
      setExporting(false);
    }
  };

  const total = results?.total ?? 0;

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Opportunity Explorer</h1>
          <p className="text-sm text-slate-500">{loading ? 'Loading…' : `${total} opportunit${total === 1 ? 'y' : 'ies'} matched`}</p>
        </div>
        <button
          type="button"
          onClick={handleExport}
          disabled={exporting}
          className="inline-flex items-center gap-2 self-start rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Download className="h-4 w-4" />
          {exporting ? 'Exporting…' : 'Export Excel'}
        </button>
      </div>

      {error ? <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div> : null}

      <div className="grid gap-6 xl:grid-cols-[300px_minmax(0,1fr)]">
        {/* Filters sidebar */}
        <form
          onSubmit={applyFilters}
          className="space-y-4 self-start rounded-2xl border border-slate-200 bg-white p-5 shadow-sm xl:sticky xl:top-6"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Filter className="h-4 w-4 text-slate-400" />
              Filters
            </div>
            <button type="button" onClick={clearFilters} className="text-xs font-medium text-blue-600 transition hover:text-blue-700">
              Clear all
            </button>
          </div>

          <div className="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-100">
            <Search className="h-4 w-4 text-slate-400" />
            <input
              value={draftFilters.query ?? ''}
              onChange={(event) => setDraftFilters((current) => ({ ...current, query: event.target.value }))}
              placeholder="Search title…"
              className="w-full border-none bg-transparent text-sm text-slate-900 outline-none placeholder:text-slate-400"
            />
          </div>

          <label className={labelClass}>
            <span>Region</span>
            <select
              value={draftFilters.regions?.[0] ?? ''}
              onChange={(event) => setDraftFilters((current) => ({ ...current, regions: event.target.value ? [event.target.value] : [] }))}
              className={fieldClass}
            >
              <option value="">All regions</option>
              {options.regions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>

          <label className={labelClass}>
            <span>Country</span>
            <select
              value={draftFilters.countries?.[0] ?? ''}
              onChange={(event) => setDraftFilters((current) => ({ ...current, countries: event.target.value ? [event.target.value] : [] }))}
              className={fieldClass}
            >
              <option value="">All countries</option>
              {options.countries.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>

          <label className={labelClass}>
            <span>Category</span>
            <select
              multiple
              value={draftFilters.categories ?? []}
              onChange={(event) => setDraftFilters((current) => ({ ...current, categories: getMultiSelectValues(event) }))}
              className={multiClass}
            >
              {options.categories.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className={labelClass}>
            <span>Status</span>
            <select
              multiple
              value={draftFilters.status ?? []}
              onChange={(event) => setDraftFilters((current) => ({ ...current, status: getMultiSelectValues(event) }))}
              className={multiClass}
            >
              {options.statuses.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <div className="grid grid-cols-2 gap-3">
            <label className={labelClass}>
              <span>Score ≥</span>
              <input
                type="number"
                min={0}
                max={100}
                value={draftFilters.score_min ?? ''}
                onChange={(event) => setDraftFilters((current) => ({ ...current, score_min: event.target.value ? Number(event.target.value) : undefined }))}
                className={fieldClass}
              />
            </label>
            <label className={labelClass}>
              <span>Score ≤</span>
              <input
                type="number"
                min={0}
                max={100}
                value={draftFilters.score_max ?? ''}
                onChange={(event) => setDraftFilters((current) => ({ ...current, score_max: event.target.value ? Number(event.target.value) : undefined }))}
                className={fieldClass}
              />
            </label>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className={labelClass}>
              <span>From</span>
              <input
                type="date"
                value={draftFilters.date_from ?? ''}
                onChange={(event) => setDraftFilters((current) => ({ ...current, date_from: event.target.value || undefined }))}
                className={fieldClass}
              />
            </label>
            <label className={labelClass}>
              <span>To</span>
              <input
                type="date"
                value={draftFilters.date_to ?? ''}
                onChange={(event) => setDraftFilters((current) => ({ ...current, date_to: event.target.value || undefined }))}
                className={fieldClass}
              />
            </label>
          </div>

          <label className={labelClass}>
            <span>Standards</span>
            <select
              multiple
              value={draftFilters.standards ?? []}
              onChange={(event) => setDraftFilters((current) => ({ ...current, standards: getMultiSelectValues(event) }))}
              className={multiClass}
            >
              {options.standards.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>

          <button type="submit" className="w-full rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-700">
            Apply filters
          </button>
        </form>

        {/* Results */}
        <div className="space-y-4">
          {/* Sort bar */}
          <div className="flex items-center justify-end gap-2">
            <span className="text-xs font-medium text-slate-500">Sort by</span>
            <select
              value={filters.sort_by ?? 'updated_at'}
              onChange={(event) => setSortField(event.target.value)}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-blue-500"
            >
              {sortOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={toggleSortDir}
              title={filters.sort_dir === 'asc' ? 'Ascending' : 'Descending'}
              className="inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
            >
              <ArrowDownUp className="h-4 w-4" />
              {filters.sort_dir === 'asc' ? 'Asc' : 'Desc'}
            </button>
          </div>

          {loading ? (
            <div className="rounded-2xl border border-slate-200 bg-white p-10 shadow-sm">
              <LoadingSpinner label="Loading opportunities..." />
            </div>
          ) : results?.items.length ? (
            <>
              <div className="grid gap-4 md:grid-cols-2">
                {results.items.map((opportunity) => (
                  <button
                    key={opportunity.id}
                    type="button"
                    onClick={() => navigate(`/opportunities/${opportunity.id}`)}
                    className="flex flex-col rounded-2xl border border-slate-200 bg-white p-5 text-left shadow-sm transition hover:border-blue-200 hover:shadow-md"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <Badge text={formatStatusLabel(opportunity.status)} className={getStatusBadgeClass(opportunity.status)} />
                      <div
                        className={[
                          'flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-sm font-semibold ring-1 ring-inset',
                          scoreBand(opportunity.score),
                        ].join(' ')}
                      >
                        {opportunity.score ?? 0}
                      </div>
                    </div>

                    <h3 className="mt-3 line-clamp-2 font-semibold text-slate-900">{opportunity.title}</h3>
                    <p className="mt-2 line-clamp-2 text-sm text-slate-500">
                      {opportunity.summary || opportunity.ai_summary || opportunity.description || 'No summary available.'}
                    </p>

                    <div className="mt-4 flex flex-wrap gap-2 text-xs">
                      {opportunity.category ? (
                        <span className="rounded-full bg-blue-50 px-2.5 py-1 font-medium text-blue-700">{formatStatusLabel(opportunity.category)}</span>
                      ) : null}
                      {opportunity.country ? <span className="rounded-full bg-slate-100 px-2.5 py-1 text-slate-600">{opportunity.country}</span> : null}
                      {opportunity.region ? <span className="rounded-full bg-slate-100 px-2.5 py-1 text-slate-600">{opportunity.region}</span> : null}
                    </div>

                    <div className="mt-4 flex items-center justify-between gap-3 border-t border-slate-100 pt-3 text-xs text-slate-400">
                      <span className="inline-flex min-w-0 items-center gap-1.5">
                        <Landmark className="h-3.5 w-3.5 shrink-0" />
                        <span className="truncate">{opportunity.institution ?? 'Unknown regulator'}</span>
                      </span>
                      <span className="shrink-0">{new Date(opportunity.updated_at).toLocaleDateString()}</span>
                    </div>
                  </button>
                ))}
              </div>

              <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white px-5 py-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
                <p className="text-sm text-slate-500">
                  Page {results.page} of {totalPages}
                </p>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => goToPage(Math.max(1, (results.page ?? 1) - 1))}
                    disabled={(results.page ?? 1) <= 1}
                    className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <ChevronLeft className="h-4 w-4" />
                    Previous
                  </button>
                  <button
                    type="button"
                    onClick={() => goToPage(Math.min(totalPages, (results.page ?? 1) + 1))}
                    disabled={(results.page ?? 1) >= totalPages}
                    className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Next
                    <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </>
          ) : (
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <EmptyState
                icon={Search}
                title="No opportunities found"
                description="Try broadening your filters or adjusting score thresholds to uncover more matches."
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default OpportunityExplorerPage;
