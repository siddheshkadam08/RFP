# 05 — Reporting, Notifications & Security

> Deployment/DevOps intentionally excluded — owned by the DevOps team.

## 1. Reporting Engine
**Objective:** generate business-ready intelligence reports automatically for leadership review, sales planning, regional strategy, pipeline analysis, standards-adoption tracking.

### 1.1 Report Types
**Weekly Intelligence** (auto, default Mon 08:00): new opportunities · high-priority · region trends · standards trends · AI executive summary.
**Monthly Strategic:** opportunity growth · top regulators · market movement · adoption trends · regional analysis.
**Custom:** user filters — region, regulator, score, category, date range.

### 1.2 Generation Workflow
```
Scheduler Trigger → Fetch Opportunity Data → Aggregate Metrics → Generate Charts
→ AI Summary (Azure OpenAI) → Excel/PDF Export → Store Report (external drive) → Notify
```

### 1.3 Excel Export (mandatory)
Workbook sheets:
1. **Executive Summary** — KPI summary, trends, charts, AI summary
2. **New Opportunities** — ID, Title, Country, Region, Regulator, Category, Score, Status, Budget, Deadline
3. **Active Opportunities** — full active pipeline
4. **Regional Summary** — metrics by region
5. **Standards Summary** — mentions of XBRL, SDMX, ISO 20022, DPM
6. **Closed Opportunities** — Won/Lost/Archived

Formatting: frozen headers · autofilters · conditional formatting · charts · pivot summaries · hyperlinks to source docs.
Conditional formatting: Score ≥80 → High (green) · 50–79 → Medium (amber) · <50 → Low (grey).
Implementation: `openpyxl`. (See the project's xlsx skill when generating the actual workbook.)

### 1.4 PDF Reports
Executive-shareable: summary · charts · key insights · AI narrative. Implementation: HTML template → PDF.

## 2. Notification Engine

### 2.1 Channels
Email · Microsoft Teams (webhook) · in-app (`alerts` table) · outbound webhook · SMS (future).

### 2.2 Types & Triggers
- **Opportunity alerts** — new opportunity detected · score increase · status change
- **Deadline alerts** — 14 days · 7 days · 24 hours before `deadline`
- **AI alerts** — regional spike · anomaly detection · crawl failure

### 2.3 Delivery rules
Per-user channel preferences; deduplicate within a window; all sends logged to `audit_logs`.

## 3. Security

### 3.1 RBAC Matrix
| Feature | Admin | Analyst | Sales | Viewer |
|---|---|---|---|---|
| View Dashboard | Yes | Yes | Yes | Yes |
| Edit Opportunities | Yes | Yes | Yes | No |
| Manage Users | Yes | No | No | No |
| Change Prompts | Yes | No | No | No |

Enforced at the API layer via a dependency that checks role permissions; UI mirrors but does not replace it.

### 3.2 Controls
- JWT access + refresh; Azure AD OIDC for SSO.
- Passwords bcrypt-hashed; secrets only via `.env` (never committed).
- All mutating actions write `audit_logs`.
- Input validation via Pydantic at every endpoint.
- PII minimization: store only what KPIs require.

## 4. Configuration (`.env` contract)
```
DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/rfp
REDIS_URL=redis://localhost:6379/0
STORAGE_ROOT=/mnt/external-drive/rfp-data       # external hard drive mount
JWT_SECRET=...
JWT_ACCESS_TTL=28800
AZURE_OPENAI_ENDPOINT=...
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_GPT_DEPLOYMENT=gpt-4o
AZURE_OPENAI_EMBED_DEPLOYMENT=text-embedding-3-large
AZURE_OPENAI_API_VERSION=2024-xx-xx             # confirm current version
AZURE_AD_TENANT_ID=...
AZURE_AD_CLIENT_ID=...
```

## 5. Logging
- Structured JSON logs to file (rotating).
- Levels: request/response (INFO), AI calls with token cost (INFO), errors (ERROR), audit (separate `audit_logs` table).
- Correlation id per request, propagated to Celery tasks.

## 6. Storage Abstraction
`StorageProvider` interface: `save(bytes, path) → uri`, `open(path) → stream`, `delete(path)`, `exists(path)`.
v1 implementation: `LocalDiskStorage` rooted at `STORAGE_ROOT` (external drive). Swappable later without touching callers.
