import api, { get, patch, post } from '@/services/api';
import type {
  Comment,
  Opportunity,
  OpportunityDetail,
  PaginatedResponse,
  SearchFilters,
} from '@/utils/types';

export type OpportunityOptions = {
  categories: { value: string; label: string }[];
  statuses: { value: string; label: string }[];
  regions: string[];
  countries: string[];
  standards: string[];
};

export const searchOpportunities = (filters: SearchFilters) =>
  post<PaginatedResponse<Opportunity>>('/opportunities/search', filters);

export const getOpportunityOptions = () => get<OpportunityOptions>('/opportunities/options');

// Download the filtered opportunities as .xlsx. Goes through the axios client (not the
// json `post` wrapper) so the Bearer token is sent and the blob isn't envelope-unwrapped.
export const exportOpportunities = async (filters: SearchFilters): Promise<Blob> => {
  const response = await api.post('/opportunities/export', filters, { responseType: 'blob' });
  return response.data as Blob;
};

export const getOpportunity = (id: string) =>
  get<OpportunityDetail>(`/opportunities/${id}`);

export const updateOpportunity = (id: string, data: Partial<OpportunityDetail>) =>
  patch<OpportunityDetail>(`/opportunities/${id}`, data);

export const addComment = (id: string, content: string) =>
  post<Comment>(`/opportunities/${id}/comments`, { content });

export const getComments = (id: string) =>
  get<Comment[]>(`/opportunities/${id}/comments`);
