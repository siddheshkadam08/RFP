export interface ApiEnvelope<T> {
  success: boolean;
  data: T;
  meta?: Record<string, unknown> | null;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: 'admin' | 'analyst' | 'manager' | 'sales_user' | 'viewer' | string;
  is_active: boolean;
  last_login?: string | null;
  created_at: string;
  updated_at?: string;
  avatar_url?: string | null;
}

export type UserResponse = User;

export interface TokenResponse {
  token: string;
  user: User;
}

export interface Opportunity {
  id: string;
  title: string;
  description?: string | null;
  summary?: string | null;
  region?: string | null;
  country?: string | null;
  category?: string | null;
  institution?: string | null;
  standards: string[];
  score?: number | null;
  status: string;
  owner_id?: string | null;
  source_id?: string | null;
  notes?: string | null;
  tags: string[];
  published_at?: string | null;
  deadline?: string | null;
  created_at: string;
  updated_at: string;
  budget?: string | null;
  scope?: string | null;
  score_breakdown?: Record<string, number>;
  ai_summary?: string | null;
  ai_reasoning?: string | null;
  source_url?: string | null;
  document_id?: string | null;
}

export interface OpportunityDetail extends Opportunity {}

export interface Source {
  id: string;
  name: string;
  url: string;
  source_type: string;
  frequency: string;
  domain?: string | null;
  country?: string | null;
  region?: string | null;
  tags: string[];
  is_active: boolean;
  status?: 'active' | 'paused' | 'error';
  last_crawled_at?: string | null;
  success_rate?: number;
  created_at: string;
  updated_at: string;
}

export interface Alert {
  id: string;
  type: string;
  title: string;
  message: string;
  severity?: 'low' | 'medium' | 'high' | 'critical';
  opportunity_id?: string | null;
  is_read: boolean;
  metadata?: Record<string, unknown> | null;
  created_at: string;
}

export interface Report {
  id: string;
  title?: string;
  type: 'weekly' | 'monthly' | 'custom' | string;
  status: string;
  parameters?: Record<string, unknown> | null;
  summary?: string | null;
  file_url?: string | null;
  pdf_url?: string | null;
  generated_by?: string | null;
  created_at: string;
  updated_at?: string;
  completed_at?: string | null;
}

export interface CommentUser {
  id: string;
  full_name: string;
}

export interface Comment {
  id: string;
  content: string;
  user: CommentUser;
  created_at: string;
}

export interface ChatCitation {
  title?: string;
  url?: string;
  snippet?: string;
  opportunity_id?: string;
  source_url?: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
  citations?: ChatCitation[];
  confidence?: number;
  session_id?: string;
}

export interface ChatResponse {
  answer: string;
  citations: ChatCitation[];
  confidence: number;
  session_id: string;
}

export interface ChatSessionSummary {
  id: string;
  title: string;
  updated_at: string | null;
  message_count: number;
}

export interface ChatSessionDetail {
  id: string;
  title: string;
  updated_at: string | null;
  messages: ChatMessage[];
}

export interface DashboardSummary {
  total_opportunities: number;
  high_priority: number;
  new_this_week: number;
  active_rfps: number;
  regions_covered: number;
  crawl_success_rate: number;
}

export interface TrendData {
  period: string;
  count: number;
}

export interface HeatmapData {
  region: string;
  country: string;
  count: number;
}

export interface SearchResult {
  id: string;
  opportunity_id: string;
  title: string;
  score?: number | null;
  relevance_score?: number | null;
  snippet?: string | null;
  summary?: string | null;
  country?: string | null;
  region?: string | null;
  category?: string | null;
  institution?: string | null;
  status?: string | null;
  source_url?: string | null;
}

export interface SearchResponse {
  items: SearchResult[];
  total: number;
  page: number;
  page_size: number;
}

export interface SearchFilters {
  regions?: string[];
  countries?: string[];
  categories?: string[];
  standards?: string[];
  score_min?: number;
  score_max?: number;
  status?: string[];
  date_from?: string;
  date_to?: string;
  query?: string;
  mode?: 'keyword' | 'semantic' | 'hybrid';
  sort_by?: string;
  sort_dir?: 'asc' | 'desc';
  page?: number;
  page_size?: number;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages?: number;
}
