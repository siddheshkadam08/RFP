# 06 — Engineering Backlog

Estimates in story points (Fibonacci). Sprint = 2 weeks. Assumes a small team (2 BE, 1 FE, 1 AI/ML, shared QA). These are planning estimates, not commitments.

## Epics
- **E1 Foundation** — repo, config, DB, migrations, auth, RBAC
- **E2 Source & Crawl** — source CRUD, scheduler, crawler workers, dedupe
- **E3 Document Processing** — extraction, Azure OpenAI vision OCR, chunking, embeddings
- **E4 AI Intelligence** — LangGraph ingestion graph: relevance→extract→classify→score
- **E5 Search** — keyword, semantic, hybrid
- **E6 Opportunities & Dashboard** — opportunity APIs, history, dashboard aggregates
- **E7 Copilot** — RAG graph, chat sessions, citations
- **E8 Reporting & Notifications** — Excel/PDF engine, notification channels
- **E9 Frontend** — all pages, RBAC-aware UI, exports
- **E10 Hardening** — audit, logging, error handling, eval harness

## Stories (selected, with FR links)

### E1 Foundation
| ID | Story | Pts | FR |
|---|---|---|---|
| S1.1 | Monorepo + backend skeleton + `.env` contract | 3 | — |
| S1.2 | SQLAlchemy models + Alembic for all 16 tables | 5 | doc03 §6 |
| S1.3 | JWT login + refresh | 3 | FR-AUTH-001/004 |
| S1.4 | Azure AD SSO (OIDC) | 5 | FR-AUTH-002 |
| S1.5 | RBAC dependency + permission matrix | 5 | FR-ROLE-001 |
| S1.6 | Audit-log writer | 2 | FR-AUTH-005 |

### E2 Source & Crawl
| S2.1 | Source CRUD + tagging | 3 | FR-SOURCE-001/004 |
| S2.2 | Celery + scheduler (freq tiers) | 5 | FR-SOURCE-002, FR-CRAWL-001 |
| S2.3 | Fetcher with retry/backoff + robots | 5 | FR-CRAWL-002/005 |
| S2.4 | Change detection + dedupe (checksum) | 3 | FR-CRAWL-003/004 |
| S2.5 | Source failure detection + alert | 3 | FR-SOURCE-003 |

### E3 Document Processing
| S3.1 | Native extractors (HTML/PDF/DOCX/XLSX/CSV/XML) | 5 | FR-DOC-001 |
| S3.2 | Azure OpenAI vision OCR for scanned | 5 | FR-DOC-002 |
| S3.3 | Language detection | 2 | FR-DOC-003 |
| S3.4 | Local-disk storage provider + blob_path | 3 | FR-DOC-004 |
| S3.5 | Chunk + embed (3072) + pgvector write | 5 | FR-DOC-005 |

### E4 AI Intelligence
| S4.1 | Azure OpenAI client wrapper + cost logging | 3 | doc04 §12.2 |
| S4.2 | LangGraph ingestion graph wiring | 5 | doc04 §13.1 |
| S4.3 | Relevance classifier node + prompt | 3 | FR-AI-001 |
| S4.4 | Field extraction node | 5 | FR-AI-002 |
| S4.5 | Category classifier node | 3 | FR-AI-003 |
| S4.6 | Scoring node + rubric + breakdown storage | 5 | FR-AI-004 |
| S4.7 | Eval harness + labeled set (ongoing) | 8 | FR-AI-005 |

### E5 Search
| S5.1 | Keyword search (pg_trgm/FTS) | 3 | FR-SEARCH-001 |
| S5.2 | Semantic search (pgvector) | 3 | FR-SEARCH-002 |
| S5.3 | Hybrid RRF | 5 | FR-SEARCH-003 |

### E6 Opportunities & Dashboard
| S6.1 | Opportunity search/detail/patch + history | 5 | doc04 §5 |
| S6.2 | Comments | 2 | — |
| S6.3 | Dashboard summary/trends/heatmap | 5 | doc04 §4 |

### E7 Copilot
| S7.1 | RAG copilot graph | 8 | FR-COPILOT-001/003 |
| S7.2 | Chat sessions/messages + citations | 3 | FR-COPILOT-002 |

### E8 Reporting & Notifications
| S8.1 | Excel engine (6 sheets, formatting) | 8 | FR-REPORT-004 |
| S8.2 | PDF engine | 5 | FR-REPORT-004 |
| S8.3 | Weekly/monthly/custom generation + scheduler | 5 | FR-REPORT-001/002/003 |
| S8.4 | Notification channels (email/teams/in-app/webhook) | 5 | FR-NOTIFY-001/002 |

### E9 Frontend
| S9.1 | App shell, routing, auth, RBAC guards | 5 | FR-UI-002 |
| S9.2 | Dashboard page | 5 | doc07 |
| S9.3 | Opportunities explorer + filters + export | 5 | FR-UI-001 |
| S9.4 | Opportunity detail | 3 | doc07 |
| S9.5 | Search page | 3 | doc07 |
| S9.6 | Copilot page | 5 | doc07 |
| S9.7 | Reports / Alerts / Sources / Admin pages | 8 | doc07 |

### E10 Hardening
| S10.1 | Global error handling + envelope | 3 | doc04 §2 |
| S10.2 | Structured logging + correlation id | 3 | doc05 §5 |
| S10.3 | Load/perf pass to scale targets | 5 | doc03 §4 |

## Indicative Sprint Plan
- **Sprint 1–2:** E1 + S2.1–S2.2 (foundation, auth, source CRUD, scheduler)
- **Sprint 3–4:** E2 finish + E3 (crawl + processing + embeddings)
- **Sprint 5–6:** E4 + E5 (AI ingestion + search)
- **Sprint 7–8:** E6 + E9 core pages (opportunities, dashboard, explorer)
- **Sprint 9–10:** E7 + E8 (copilot, reports, notifications)
- **Sprint 11–12:** E9 finish + E10 (remaining UI, hardening, eval)

## Risk register
| Risk | Impact | Mitigation |
|---|---|---|
| Crawler breakage per source | High | per-source adapters, failure alerts, manual re-crawl |
| AI scoring accuracy | High | eval harness + labeled set + tunable rubric (S4.7) |
| Azure OpenAI cost/rate limits | Med | cost logging, batching, caching, backoff |
| 3072-dim vector index perf | Med | HNSW, verify pgvector version (doc03 flag) |
| OCR quality via vision | Med | fall back to native text where available; flag low-confidence |
