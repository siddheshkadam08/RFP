# 02 — Functional Requirements & UI/UX Specification

Conventions: `FR-<MODULE>-<NNN>`. "System shall…" = mandatory. Each FR is testable.

## 1.1 Authentication
**Objective:** secure enterprise access with RBAC.
Login methods: username/password (optional), **SSO via Azure AD**, OAuth (future), MFA support.

- **FR-AUTH-001** System shall support secure login (JWT, bcrypt-hashed local passwords).
- **FR-AUTH-002** System shall support SSO authentication via Azure AD (OIDC).
- **FR-AUTH-003** System shall enforce role-based access control (RBAC).
- **FR-AUTH-004** System shall expire sessions (configurable TTL; default 8h access, refresh token 30d).
- **FR-AUTH-005** System shall log all login activity to `audit_logs`.

## 1.2 User Roles & Permissions
| Role | Permissions |
|---|---|
| Admin | manage users, sources, AI config, alerts; access all data |
| Analyst | review AI findings, validate opportunities, edit metadata, generate reports |
| Sales | view opportunities, update pursuit status, comment, create watchlists |
| Viewer | read-only |

- **FR-ROLE-001** System shall enforce the permission matrix above at the API layer (not just UI).

## 1.3 Source Discovery
**Objective:** discover and manage opportunity sources.
Source types: regulator websites, tender portals, procurement systems, government & ministry websites, press releases, RSS, PDFs, annual reports, strategic plans, news feeds, funding-agency portals.

- **FR-SOURCE-001** Admin shall add a new source.
- **FR-SOURCE-002** System shall schedule crawl frequency: hourly, daily, weekly, monthly.
- **FR-SOURCE-003** System shall detect source failures (HTTP errors, empty content, structure change).
- **FR-SOURCE-004** System shall support source tagging: country, regulator, type, priority.

## 1.4 Crawling Engine
**Objective:** fetch content automatically.
Supported formats: HTML, PDF, DOCX, XLSX, CSV, XML, ZIP, scanned images.

- **FR-CRAWL-001** System shall crawl scheduled sources.
- **FR-CRAWL-002** System shall retry on failure: 3 attempts, exponential backoff.
- **FR-CRAWL-003** System shall detect content changes via checksum, hash, AI similarity.
- **FR-CRAWL-004** System shall avoid duplicate documents (checksum dedupe before storage).
- **FR-CRAWL-005** System shall respect robots.txt and per-source rate limits.

> Implementation note: crawler quality is empirical and per-source. Spec defines behavior + interface; tuning is ongoing.

## 1.5 Document Processing
**Objective:** convert raw documents into structured content.
Capabilities: text extraction, table extraction, **OCR via Azure OpenAI vision** (scanned PDFs/images), metadata extraction, language detection, translation support.

- **FR-DOC-001** System shall extract text from HTML/PDF/DOCX/XLSX/CSV/XML.
- **FR-DOC-002** For scanned PDFs/images, system shall extract text using Azure OpenAI vision (gpt-4o multimodal).
- **FR-DOC-003** System shall detect document language.
- **FR-DOC-004** System shall store the original file on the external-drive storage and record `blob_path` + `checksum`.
- **FR-DOC-005** System shall chunk text and generate embeddings (`text-embedding-3-large`, 3072-dim) into `document_embeddings`.

## 1.6 AI Opportunity Intelligence
- **FR-AI-001** System shall detect whether a document signals a relevant opportunity (relevance classification).
- **FR-AI-002** System shall extract structured opportunity fields (title, category, country, regulator, budget, deadline, summary).
- **FR-AI-003** System shall classify opportunity category (§1.7 of doc 01).
- **FR-AI-004** System shall score opportunities 0–100 with an explainable rubric (see doc 04 §13).
- **FR-AI-005** Every AI output shall be auditable: prompt version, model deployment, source chunk citations.

## 1.7 Search
- **FR-SEARCH-001** Keyword search (Postgres `pg_trgm` / full-text).
- **FR-SEARCH-002** Semantic search (pgvector cosine over embeddings).
- **FR-SEARCH-003** Hybrid search (reciprocal-rank fusion of keyword + semantic).

## 1.8 AI Copilot
- **FR-COPILOT-001** System shall answer natural-language questions over the opportunity/document corpus with citations and a confidence score.
- **FR-COPILOT-002** System shall persist chat sessions/messages (`chat_sessions`, `chat_messages`).
- **FR-COPILOT-003** Copilot answers shall be grounded (RAG) — no answer without retrieved evidence.

## 1.9 Reporting (summary; full spec in doc 05)
- **FR-REPORT-001** Weekly intelligence report, auto-generated.
- **FR-REPORT-002** Monthly strategic report.
- **FR-REPORT-003** Custom report by region/regulator/score/category/date range.
- **FR-REPORT-004** Excel export (mandatory) and PDF export.

## 1.10 Notifications (summary; full spec in doc 05)
- **FR-NOTIFY-001** Channels: Email, MS Teams, in-app, webhook (SMS future).
- **FR-NOTIFY-002** Triggers: new/changed opportunity, deadline windows, AI anomalies, crawl failures.

## 1.11 UI/UX (screens detailed in doc 07)
Pages: Dashboard, Opportunities (Explorer), Opportunity Detail, Search, Reports, Copilot, Alerts, Sources, Admin.
- **FR-UI-001** All list views shall support filter, sort, paginate, and Excel export.
- **FR-UI-002** UI shall reflect RBAC (hide/disable unauthorized actions) — enforcement is server-side.
