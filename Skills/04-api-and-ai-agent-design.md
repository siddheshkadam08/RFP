# 04 — API & AI Agent Design

## 1. API Principles
RESTful · JSON · JWT auth · versioned (`/api/v1`) · pagination · structured errors · idempotency for scheduled jobs.

## 2. Standard Response Envelope
```json
// success
{ "success": true, "data": {}, "meta": {} }
// error
{ "success": false, "error": { "code": "INVALID_REQUEST", "message": "Missing region filter" } }
```
Pagination `meta`: `{ "page": 1, "page_size": 50, "total": 100 }`.

## 3. Authentication
| Method | Path | Notes |
|---|---|---|
| POST | `/auth/login` | `{email,password}` → `{token, user}` |
| POST | `/auth/sso` | Azure AD OIDC exchange |
| POST | `/auth/refresh` | refresh token → new access token |
| GET  | `/auth/me` | current user + role |

## 4. Dashboard
| Method | Path | Returns |
|---|---|---|
| GET | `/dashboard/summary` | `{total_opportunities, high_priority, new_this_week, regions_covered}` |
| GET | `/dashboard/trends` | weekly trend series |
| GET | `/dashboard/heatmap` | geography aggregation |

## 5. Opportunities
| Method | Path | Notes |
|---|---|---|
| POST | `/opportunities/search` | filters: `regions[], score_min, status[], category[], date_range, page, page_size` |
| GET  | `/opportunities/{id}` | full detail incl. source citations, history |
| PATCH| `/opportunities/{id}` | editable: status, owner, notes (writes `opportunity_history`) |
| POST | `/opportunities/{id}/comments` | add comment |

## 6. Sources
`GET /sources` · `POST /sources` (`{name,url,frequency,regulator_id,type}`) · `PATCH /sources/{id}` · `POST /sources/{id}/crawl` (manual trigger).

## 7. Reports
`GET /reports` · `POST /reports/generate` (`{type:"weekly|monthly|custom", params}`) · `GET /reports/{id}/download` (xlsx/pdf).

## 8. Alerts
`GET /alerts` · `PATCH /alerts/{id}` (read/unread).

## 9. Search
`POST /search/keyword` (`{query}`) · `POST /search/semantic` (`{query}`) · `POST /search/hybrid` (`{query, filters}`).

## 10. AI Copilot
| Method | Path | Notes |
|---|---|---|
| POST | `/ai/chat` | `{session_id, message}` → `{answer, citations[], confidence}` |
| POST | `/ai/summarize` | summarize a document |
| POST | `/ai/qna` | grounded Q&A |

## 11. Admin (admin-only)
user management · prompt configs · model configs · scheduler configs · AI cost tracking · feature flags.

All endpoints enforce RBAC server-side and write to `audit_logs`.

---

## 12. AI Architecture

### 12.1 Principles
Explainable · auditable · cost-optimized · resilient · deterministic where needed (scoring uses temperature 0 + fixed rubric).

### 12.2 Azure OpenAI integration (only AI dependency)
- **Generation/vision:** `gpt-4o` deployment (config: `AZURE_OPENAI_GPT_DEPLOYMENT`)
- **Embeddings:** `text-embedding-3-large` (config: `AZURE_OPENAI_EMBED_DEPLOYMENT`), 3072-dim
- **OCR:** scanned pages rendered to images → gpt-4o vision → text
- Single client wrapper `core/ai/azure_openai.py`; retry with backoff; per-call token/cost logging to `audit_logs`.

### 12.3 Pluggable extraction interface
`DocumentExtractor` protocol with methods `extract_text(file)`, `extract_tables(file)`, `ocr(image)`. Default impl uses native parsers for digital docs and Azure OpenAI vision for scanned. This isolates the one OCR gap left by dropping Document Intelligence.

## 13. LangGraph Orchestration

### 13.1 Ingestion graph (per document)
```
[detect_relevance] → (relevant?) → [extract_fields] → [classify_category]
      → [score_opportunity] → [persist_opportunity] → [emit_alerts]
                  ↘ (not relevant) → [discard + log]
```
- **detect_relevance** — binary classify against IRIS SupTech/RegTech scope; returns reason.
- **extract_fields** — structured JSON: title, summary, country, regulator, budget, deadline.
- **classify_category** — one of the §1.7 categories.
- **score_opportunity** — rubric below; temperature 0.
- **persist_opportunity** — upsert; write `opportunity_history` on change.
- **emit_alerts** — new/high-score/deadline triggers.

Every node records: prompt version, model deployment, input chunk ids, output, token cost.

### 13.2 Copilot graph (RAG)
```
[rewrite_query] → [hybrid_retrieve] → [rerank] → [generate_grounded_answer] → [attach_citations]
```
Refuse to answer if retrieval returns no evidence above threshold (FR-COPILOT-003).

## 14. Scoring Rubric (0–100, explainable)
| Dimension | Weight | Signal |
|---|---|---|
| Relevance to SupTech/RegTech | 30 | category match, keyword density |
| Stage / urgency | 20 | pre-RFP signal vs live tender vs deadline proximity |
| Budget / value | 20 | stated/implied budget |
| Strategic fit (region/account) | 15 | priority region/regulator tags |
| Standards alignment | 15 | mentions of XBRL/SDMX/ISO 20022/DPM |

Score is the weighted sum; the per-dimension breakdown is stored and shown in the UI for explainability. Thresholds: ≥80 High, 50–79 Medium, <50 Low.

> Scoring **weights and thresholds are starting points** — calibrate against labeled opportunities. Accuracy is earned through evaluation, not fixed by this table.
