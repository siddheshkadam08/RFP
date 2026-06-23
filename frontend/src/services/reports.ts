import api, { get, post } from '@/services/api';
import type { Report } from '@/utils/types';

export const listReports = () => get<Report[]>('/reports/');

export const generateReport = (
  type: 'weekly' | 'monthly' | 'custom',
  parameters: Record<string, unknown> = {},
) => post<Report>('/reports/generate', { type, parameters });

// Streams the report file (xlsx or pdf) via the authed axios instance (blob) and
// triggers a browser download.
export const downloadReport = async (id: string, filename: string, format: 'xlsx' | 'pdf' = 'xlsx') => {
  const response = await api.get(`/reports/${id}/download`, {
    params: { format },
    responseType: 'blob',
  });
  const url = window.URL.createObjectURL(response.data as Blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
};
