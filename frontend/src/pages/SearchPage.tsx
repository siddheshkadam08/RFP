import { ChevronLeft, ChevronRight, Search, Sparkles } from 'lucide-react';
import { FormEvent, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import Badge, { formatStatusLabel, getScoreVariant } from '@/components/common/Badge';
import EmptyState from '@/components/common/EmptyState';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import { getApiErrorMessage } from '@/services/api';
import { getOpportunityOptions, type OpportunityOptions } from '@/services/opportunities';
import { runSearch as searchApi, type SearchMode } from '@/services/search';
import type { SearchResult } from '@/utils/types';

const emptyOptions: OpportunityOptions = { categories: [], statuses: [], regions: [], countries: [], standards: [] };

const PAGE_SIZE = 12;

const tabs: Array<{ label: string; value: SearchMode; hint?: string }> = [
  { label: 'Keyword', value: 'keyword' },
  { label: 'Semantic', value: 'semantic', hint: 'beta' },
  { label: 'Hybrid', value: 'hybrid', hint: 'beta' },
];

const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

// Wraps query terms found in `text` with a highlighted <mark>.
const Highlight = ({ text, query }: { text: string; query: string }) => {
  const terms = query
    .trim()
    .split(/\s+/)
    .filter((term) => term.length > 1)
    .map(escapeRegExp);

  if (!text || terms.length === 0) {
    return <>{text}</>;
  }

  const splitter = new RegExp(`(${terms.join('|')})`, 'gi');
  const matcher = new RegExp(`^(?:${terms.join('|')})$`, 'i');

  return (
    <>
      {text.split(splitter).map((part, index) =>
        matcher.test(part) ? (
          <mark key={index} className="rounded bg-yellow-100 px-0.5 text-slate-900">
            {part}
          </mark>
        ) : (
          <span key={index}>{part}</span>
        ),
      )}
    </>
  );
};

const SearchPage = () => {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState<SearchMode>('hybrid');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [options, setOptions] = useState<OpportunityOptions>(emptyOptions);
  const [region, setRegion] = useState('');
  const [category, setCategory] = useState('');
  const [status, setStatus] = useState('');

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const rangeStart = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const rangeEnd = Math.min(page * PAGE_SIZE, total);

  useEffect(() => {
    const loadOptions = async () => {
      try {
        setOptions(await getOpportunityOptions());
      } catch {
        // filters are optional; leave empty if the endpoint is unavailable
      }
    };
    void loadOptions();
  }, []);

  const runSearch = async (searchQuery: string, searchMode: SearchMode, searchPage = 1) => {
    if (!searchQuery.trim()) {
      setResults([]);
      setTotal(0);
      setPage(1);
      return;
    }

    setLoading(true);
    setError('');

    const filters = {
      ...(region ? { regions: [region] } : {}),
      ...(category ? { categories: [category] } : {}),
      ...(status ? { status: [status] } : {}),
    };

    try {
      const response = await searchApi(searchMode, searchQuery.trim(), searchPage, PAGE_SIZE, filters);
      setResults(response.items ?? []);
      setTotal(response.total ?? 0);
      setPage(searchPage);
    } catch (searchError) {
      setError(getApiErrorMessage(searchError, 'Unable to run search.'));
      setResults([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  };

  // Query/mode/filter changes reset back to page 1 (debounced).
  useEffect(() => {
    if (!query.trim()) {
      return;
    }

    const timer = window.setTimeout(() => {
      void runSearch(query, mode, 1);
    }, 400);

    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, query, region, category, status]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void runSearch(query, mode, 1);
  };

  const goToPage = (nextPage: number) => {
    if (loading || nextPage < 1 || nextPage > totalPages) {
      return;
    }
    void runSearch(query, mode, nextPage);
  };

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="mx-auto max-w-4xl space-y-6">
          <div className="text-center">
            <div className="mx-auto inline-flex rounded-2xl bg-blue-50 p-3 text-blue-600">
              <Sparkles className="h-7 w-7" />
            </div>
            <h1 className="mt-4 text-3xl font-semibold text-slate-900">Search the global opportunity graph</h1>
            <p className="mt-2 text-sm text-slate-500">Blend keyword precision with semantic retrieval to surface the best-fit opportunities faster.</p>
          </div>

          <form className="space-y-4" onSubmit={handleSubmit}>
            <div className="flex items-center gap-3 rounded-2xl border border-slate-200 px-5 py-4 focus-within:border-blue-500 focus-within:ring-4 focus-within:ring-blue-100">
              <Search className="h-5 w-5 text-slate-400" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Try: digital health tenders in Southeast Asia"
                className="w-full border-none bg-transparent text-base text-slate-900 outline-none placeholder:text-slate-400"
              />
            </div>

            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="inline-flex rounded-2xl bg-slate-100 p-1">
                {tabs.map((tab) => (
                  <button
                    key={tab.value}
                    type="button"
                    onClick={() => setMode(tab.value)}
                    className={[
                      'rounded-xl px-4 py-2 text-sm font-medium transition',
                      mode === tab.value ? 'bg-white text-blue-600 shadow-sm' : 'text-slate-600',
                    ].join(' ')}
                  >
                    {tab.label}
                    {tab.hint ? <span className="ml-1 text-[10px] uppercase tracking-wide text-slate-400">{tab.hint}</span> : null}
                  </button>
                ))}
              </div>

              <button
                type="submit"
                className="rounded-2xl bg-blue-600 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-blue-600/20 transition hover:bg-blue-700"
              >
                Search
              </button>
            </div>

            <div className="flex flex-wrap gap-3">
              <select
                value={region}
                onChange={(event) => setRegion(event.target.value)}
                className="rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-700 outline-none focus:border-blue-500"
              >
                <option value="">All regions</option>
                {options.regions.map((value) => (
                  <option key={value} value={value}>
                    {value}
                  </option>
                ))}
              </select>
              <select
                value={category}
                onChange={(event) => setCategory(event.target.value)}
                className="rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-700 outline-none focus:border-blue-500"
              >
                <option value="">All categories</option>
                {options.categories.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <select
                value={status}
                onChange={(event) => setStatus(event.target.value)}
                className="rounded-xl border border-slate-200 px-3 py-2 text-sm text-slate-700 outline-none focus:border-blue-500"
              >
                <option value="">All statuses</option>
                {options.statuses.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </form>
        </div>
      </section>

      {error ? <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div> : null}

      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Results</h2>
            <p className="text-sm text-slate-500">
              {total > 0 ? `Showing ${rangeStart}–${rangeEnd} of ${total} matches` : 'No matches found'}
            </p>
          </div>
        </div>

        {loading ? (
          <LoadingSpinner label="Searching opportunities..." />
        ) : results.length ? (
          <>
          <div className="space-y-4">
            {results.map((result) => (
              <button
                key={result.id}
                type="button"
                onClick={() => navigate(`/opportunities/${result.id}`)}
                className="w-full rounded-2xl border border-slate-200 p-5 text-left transition hover:border-blue-200 hover:bg-blue-50/40"
              >
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div>
                    <h3 className="text-lg font-semibold text-slate-900">
                      <Highlight text={result.title} query={query} />
                    </h3>
                    <p className="mt-2 text-sm leading-7 text-slate-600">
                      <Highlight
                        text={result.snippet || result.summary || 'No result snippet is currently available for this opportunity.'}
                        query={query}
                      />
                    </p>
                    <div className="mt-4 flex flex-wrap gap-2 text-xs font-medium text-slate-500">
                      <span className="rounded-full bg-slate-100 px-3 py-1">{result.country ?? 'Unknown country'}</span>
                      <span className="rounded-full bg-slate-100 px-3 py-1">{result.region ?? 'Unknown region'}</span>
                      <span className="rounded-full bg-slate-100 px-3 py-1">{result.category ? formatStatusLabel(result.category) : 'Uncategorized'}</span>
                      {typeof result.relevance_score === 'number' ? (
                        <span className="rounded-full bg-blue-50 px-3 py-1 text-blue-700">{Math.round(result.relevance_score * 100)}% match</span>
                      ) : null}
                    </div>
                  </div>
                  <Badge text={`Score ${result.score ?? 0}`} variant={getScoreVariant(result.score)} size="md" />
                </div>
              </button>
            ))}
          </div>

          {totalPages > 1 ? (
            <div className="mt-6 flex items-center justify-between border-t border-slate-100 pt-4">
              <p className="text-sm text-slate-500">
                Page {page} of {totalPages}
              </p>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => goToPage(page - 1)}
                  disabled={page <= 1 || loading}
                  className="inline-flex items-center gap-1 rounded-xl border border-slate-200 px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <ChevronLeft className="h-4 w-4" />
                  Previous
                </button>
                <button
                  type="button"
                  onClick={() => goToPage(page + 1)}
                  disabled={page >= totalPages || loading}
                  className="inline-flex items-center gap-1 rounded-xl border border-slate-200 px-3 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Next
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          ) : null}
          </>
        ) : (
          <EmptyState
            icon={Search}
            title="No search results yet"
            description="Enter a query to explore opportunities by keyword, semantic meaning, or a hybrid approach."
          />
        )}
      </section>
    </div>
  );
};

export default SearchPage;
