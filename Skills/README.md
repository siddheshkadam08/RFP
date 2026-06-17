# RFP & Opportunity Intelligence System — Build-Ready Specification (v3)

AI-powered global RFP & opportunity intelligence platform for IRIS SupTech/RegTech business development.

## What this is
A **build-ready specification set**: detailed enough that a developer or coding agent can implement the full application (UI → API → AI → database → reports) from these documents. These are specs, not the running system — see "Honest scope" below.

## Locked architecture decisions (v1)
| Concern | Decision |
|---|---|
| AI provider | **Azure OpenAI only** — no other Azure service |
| Generation model | Azure OpenAI `gpt-4o` (configurable deployment name) |
| Embedding model | Azure OpenAI `text-embedding-3-large` → **3072-dim** |
| OCR / scanned docs | **Azure OpenAI vision** (gpt-4o multimodal) — no Document Intelligence |
| Database | **Local PostgreSQL 16+** with `pgvector` |
| Object storage | **Local external hard drive** (filesystem path), abstracted behind a storage interface |
| Cache / queue | Local Redis |
| Background jobs | Celery (Redis broker) |
| Deployment / infra | **Out of scope** — owned by DevOps team. No hosting/CI/CD content in these specs. |

## Document map
| File | Purpose |
|---|---|
| `01-executive-summary.md` | Why: problem, solution, goals, KPIs, users, scope |
| `02-functional-requirements.md` | What: numbered FRs + UI/UX per module |
| `03-architecture-and-database.md` | Structure: services, stack, full PostgreSQL schema (16 tables) |
| `04-api-and-ai-agent-design.md` | Behavior: REST endpoints, LangGraph agents, Azure OpenAI integration |
| `05-reporting-notifications-security.md` | Outputs: Excel/PDF reports, notifications, RBAC, config, logging |
| `06-engineering-backlog.md` | Delivery: epics, stories, estimates, sprint plan |
| `07-ui-wireframes.md` | Screens: layout per page (Dashboard, Explorer, Detail, Copilot, Admin) |
| `08-code-scaffold.md` | Skeleton: monorepo layout, starter modules, env contract |

## Honest scope (read before estimating)
These specs make "build the whole app" tractable, but two parts converge only through iterative real-world work, not specification:
- **Crawling engine** — thousands of bespoke regulator/tender sites across 100+ countries. Per-source tuning, anti-bot handling, and breakage repair are ongoing engineering.
- **AI extraction & scoring accuracy** — prompt tuning + evaluation against real labeled documents. The spec defines the interface and the rubric; accuracy is earned, not declared.

Everything else (schema, API, UI, report engine, agent wiring) is deterministic from these docs.

## Scale targets (from architecture spec)
5,000+ institutions · 100+ countries · 50M documents · 1M+ embeddings · 100 concurrent users.
