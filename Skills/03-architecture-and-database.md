# 03 — Architecture & Database

## 1. System Architecture
Distributed, service-oriented.

```
React Frontend
      |
API Gateway / Load Balancer        (DevOps-owned; out of scope here)
      |
FastAPI Backend
      |
[ Auth | Opportunity | Search | Reports | AI Orchestrator ]
      |
[ Postgres | pgvector | Local-Disk Storage | Redis Cache | Scheduler ]
      |
[ Crawlers | AI Agents | Report Engine | Notification Engine ]
```

### 1.2 Core Components
Frontend UI · Backend APIs · Auth service · AI orchestration · Crawling service · Reporting engine · Notification engine · Database · Scheduler · Storage (local external drive).

### 1.3 Technology Stack
- **Frontend:** React, TypeScript, MUI, TanStack Table, Chart.js/Recharts
- **Backend:** Python 3.11+, FastAPI, Pydantic, SQLAlchemy, Alembic
- **Database:** PostgreSQL 16+, pgvector
- **AI:** LangGraph, **Azure OpenAI only** (gpt-4o generation + vision, text-embedding-3-large)
- **Storage:** local external hard drive via `StorageProvider` abstraction (no Azure Blob)
- **Cache:** Redis
- **Background:** Celery (Redis broker)

> Deviation from original PRD: Azure Blob → local disk; Azure PostgreSQL → local Postgres; Azure Document Intelligence → Azure OpenAI vision. All other Azure services removed per constraint.

## 2. Frontend Architecture
```
src/
├── components/   ├── pages/    ├── hooks/
├── services/     ├── context/  ├── routes/
├── utils/        └── store/
pages/
├── Dashboard  ├── Opportunities  ├── OpportunityDetail
├── Search     ├── Reports        ├── Copilot
├── Alerts     ├── Sources        └── Admin
```

## 3. Backend Architecture
```
backend/app/
├── api/         # routers (thin: validation, auth, response shaping)
├── core/        # config, security, logging
├── db/          # session, base, migrations entry
├── models/      # SQLAlchemy ORM
├── schemas/     # Pydantic
├── services/    # business logic, orchestration
├── repositories/# SQL / DB abstraction
├── workers/     # Celery tasks (crawl, process, embed, report)
├── agents/      # LangGraph nodes/graphs
├── prompts/     # versioned prompt templates
├── storage/     # StorageProvider (local disk impl)
├── scheduler/   # periodic job definitions
└── main.py
```
**Layering:** API → Service → Repository → Database. No SQL above the repository layer; no business logic in routers.

## 4. Scalability
Targets: 5,000+ institutions, 100+ countries, 50M documents, 100 concurrent users, 1M+ embeddings.
Horizontal scaling by independent worker pools: crawler workers, AI workers, report workers, API servers.

## 5. Database

### 5.1 Required Extensions
```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;
```

### 5.2 Entities
users · roles · countries · regions · regulators · sources · documents · document_embeddings · opportunities · opportunity_history · alerts · reports · comments · audit_logs · chat_sessions · chat_messages.

## 6. Tables

```sql
CREATE TABLE roles (
    id UUID PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE users (
    id UUID PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255),
    hashed_password TEXT,              -- null for SSO-only users
    azure_oid VARCHAR(255) UNIQUE,     -- Azure AD object id (SSO)
    role_id UUID REFERENCES roles(id),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE regions (
    id UUID PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE countries (
    id UUID PRIMARY KEY,
    region_id UUID REFERENCES regions(id),
    name VARCHAR(100) NOT NULL,
    iso_code VARCHAR(10),
    active BOOLEAN DEFAULT TRUE
);

CREATE TABLE regulators (
    id UUID PRIMARY KEY,
    country_id UUID REFERENCES countries(id),
    name TEXT NOT NULL,
    regulator_type VARCHAR(100),       -- central_bank|deposit_insurer|business_registry|
                                       -- capital_market|stock_exchange|tax_authority|
                                       -- statistical_body|local_government
    website TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE sources (
    id UUID PRIMARY KEY,
    regulator_id UUID REFERENCES regulators(id),
    source_name TEXT,
    source_url TEXT,
    source_type VARCHAR(50),           -- website|pdf|rss|portal|api|news
    crawl_frequency VARCHAR(20),       -- hourly|daily|weekly|monthly
    last_crawl TIMESTAMP,
    active BOOLEAN DEFAULT TRUE
);

CREATE TABLE documents (
    id UUID PRIMARY KEY,
    source_id UUID REFERENCES sources(id),
    file_name TEXT,
    blob_path TEXT,                    -- path on external-drive storage
    document_type VARCHAR(50),
    language VARCHAR(20),
    checksum TEXT,                     -- dedupe key
    extracted_text TEXT,
    published_date DATE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE document_embeddings (
    id UUID PRIMARY KEY,
    document_id UUID REFERENCES documents(id),
    chunk_index INT,
    chunk_text TEXT,
    embedding VECTOR(3072)             -- text-embedding-3-large
);

CREATE TABLE opportunities (
    id UUID PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT,
    category VARCHAR(100),
    country_id UUID REFERENCES countries(id),
    regulator_id UUID REFERENCES regulators(id),
    source_document_id UUID REFERENCES documents(id),
    score INT CHECK (score BETWEEN 0 AND 100),
    status VARCHAR(50) DEFAULT 'new',  -- new|qualified|active|won|lost|archived
    budget TEXT,
    deadline DATE,
    owner_id UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE opportunity_history (
    id UUID PRIMARY KEY,
    opportunity_id UUID REFERENCES opportunities(id),
    field VARCHAR(100),
    old_value TEXT,
    new_value TEXT,
    changed_by UUID REFERENCES users(id),
    changed_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE alerts (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    opportunity_id UUID REFERENCES opportunities(id),
    alert_type VARCHAR(50),            -- opportunity|deadline|ai_anomaly|crawl_failure
    message TEXT,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE reports (
    id UUID PRIMARY KEY,
    report_type VARCHAR(50),           -- weekly|monthly|custom
    params JSONB,
    file_path TEXT,                    -- external-drive path to xlsx/pdf
    generated_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE comments (
    id UUID PRIMARY KEY,
    opportunity_id UUID REFERENCES opportunities(id),
    user_id UUID REFERENCES users(id),
    body TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE audit_logs (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    action VARCHAR(100),
    entity VARCHAR(100),
    entity_id UUID,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE chat_sessions (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    title TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE chat_messages (
    id UUID PRIMARY KEY,
    session_id UUID REFERENCES chat_sessions(id),
    role VARCHAR(20),                  -- user|assistant
    content TEXT,
    citations JSONB,
    confidence NUMERIC,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 6.x Indexes
```sql
-- Vector: HNSW preferred for 3072-dim recall/latency (note below)
CREATE INDEX idx_doc_embedding ON document_embeddings
  USING hnsw (embedding vector_cosine_ops);

CREATE INDEX idx_opp_status   ON opportunities (status);
CREATE INDEX idx_opp_score    ON opportunities (score DESC);
CREATE INDEX idx_opp_country  ON opportunities (country_id);
CREATE INDEX idx_doc_checksum ON documents (checksum);
CREATE INDEX idx_doc_text_trgm ON documents USING gin (extracted_text gin_trgm_ops);
```

> **Flag — verify before build:** the original PRD specified `ivfflat` on a `VECTOR(3072)`. pgvector's ivfflat has historically had a 2000-dim ceiling for indexing; HNSW supports higher dims and generally gives better recall/latency, so this spec switches to HNSW. Confirm against the pgvector version your DevOps team pins, and confirm gpt-4o + text-embedding-3-large deployment names in your Azure OpenAI resource. These are version-sensitive facts I have not verified against live docs.
