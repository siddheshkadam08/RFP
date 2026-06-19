import { post } from '@/services/api';
import type { SearchResponse } from '@/utils/types';

export type SearchMode = 'keyword' | 'semantic' | 'hybrid';

export type SearchRequestFilters = {
  regions?: string[];
  categories?: string[];
  status?: string[];
};

// Routes to the real /search/{mode} endpoints (keyword/semantic/hybrid), which each
// return a paginated { items, total, page, page_size }. Optional region/category/status filters.
export const runSearch = (
  mode: SearchMode,
  query: string,
  page = 1,
  pageSize = 12,
  filters?: SearchRequestFilters,
) => post<SearchResponse>(`/search/${mode}`, { query, page, page_size: pageSize, ...(filters ?? {}) });
