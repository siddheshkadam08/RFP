# AI-Powered Global RFP & Opportunity Intelligence System

A production-grade platform that continuously monitors global markets to identify, track, analyze, and score business opportunities relevant to SupTech and RegTech business. The system detects opportunities from published tenders, RFPs, and early signals such as strategic plans, annual reports, procurement roadmaps, and regulatory announcements.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (React)                      │
│  Dashboard │ Opportunities │ Search │ AI Copilot │ ...  │
└──────────────────────┬──────────────────────────────────┘
                       │ REST API (JSON)
┌──────────────────────┴──────────────────────────────────┐
│                  Backend (FastAPI)                        │
│  Auth │ APIs │ Services │ AI Agents │ Background Tasks   │
└───┬──────────┬──────────────┬───────────────────────────┘
    │          │              │
┌───┴───┐ ┌───┴───┐ ┌───────┴────────┐
│Postgres│ │ Redis │ │ Azure OpenAI   │
│  (DB)  │ │(Cache)│ │ (AI Services)  │
└────────┘ └───────┘ └────────────────┘
```

## Tech Stack

### Backend
- **Framework**: FastAPI (Python 3.11)
- **Database**: PostgreSQL 16 with SQLAlchemy 2.0 (async)
- **Migrations**: Alembic
- **Task Queue**: Celery + Redis
- **AI**: Azure OpenAI (GPT-4 + Embeddings)
- **Authentication**: JWT + RBAC

### Frontend
- **Framework**: React 18 + TypeScript
- **Build Tool**: Vite
- **Styling**: Tailwind CSS
- **Charts**: Recharts
- **Icons**: Lucide React
- **HTTP Client**: Axios

### Infrastructure
- **Containerization**: Docker + Docker Compose
- **Reverse Proxy**: Nginx
- **Cache/Broker**: Redis

## Project Structure

```
├── backend/
│   ├── app/
│   │   ├── api/v1/endpoints/    # REST API endpoints
│   │   │   ├── auth.py          # Authentication APIs
│   │   │   ├── dashboard.py     # Dashboard KPI APIs
│   │   │   ├── opportunities.py # Opportunity CRUD + search
│   │   │   ├── sources.py       # Source management
│   │   │   ├── reports.py       # Report generation
│   │   │   ├── alerts.py        # Alert management
│   │   │   ├── search.py        # Keyword/semantic/hybrid search
│   │   │   ├── copilot.py       # AI Copilot chat APIs
│   │   │   └── admin.py         # Admin management
│   │   ├── core/                # Core configuration
│   │   │   ├── config.py        # App settings (env vars)
│   │   │   ├── database.py      # SQLAlchemy async setup
│   │   │   ├── security.py      # JWT + password hashing
│   │   │   ├── celery_app.py    # Celery configuration
│   │   │   └── exceptions.py    # Custom exceptions
│   │   ├── models/              # SQLAlchemy models
│   │   │   ├── user.py          # User + roles
│   │   │   ├── opportunity.py   # Opportunities
│   │   │   ├── source.py        # Data sources
│   │   │   ├── document.py      # Crawled documents
│   │   │   ├── alert.py         # Alerts
│   │   │   ├── report.py        # Reports
│   │   │   ├── comment.py       # Comments
│   │   │   ├── audit_log.py     # Audit trail
│   │   │   └── chat_session.py  # AI chat sessions
│   │   ├── schemas/             # Pydantic request/response models
│   │   ├── services/            # Business logic layer
│   │   │   ├── ai_service.py    # Azure OpenAI integration
│   │   │   ├── auth_service.py
│   │   │   ├── opportunity_service.py
│   │   │   ├── dashboard_service.py
│   │   │   ├── search_service.py
│   │   │   ├── report_service.py
│   │   │   ├── alert_service.py
│   │   │   ├── source_service.py
│   │   │   └── audit_service.py
│   │   ├── agents/              # AI pipeline agents
│   │   │   ├── pipeline.py      # Orchestrator
│   │   │   └── prompts.py       # Prompt templates
│   │   └── tasks.py             # Celery background tasks
│   ├── alembic/                 # Database migrations
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/               # Page components
│   │   │   ├── LoginPage.tsx
│   │   │   ├── DashboardPage.tsx
│   │   │   ├── OpportunityExplorerPage.tsx
│   │   │   ├── OpportunityDetailPage.tsx
│   │   │   ├── SearchPage.tsx
│   │   │   ├── CopilotPage.tsx
│   │   │   ├── ReportsPage.tsx
│   │   │   ├── AlertsPage.tsx
│   │   │   ├── SourcesPage.tsx
│   │   │   └── AdminPage.tsx
│   │   ├── components/          # Reusable components
│   │   │   ├── layout/          # Sidebar, Layout
│   │   │   └── common/          # Badge, Spinner, EmptyState
│   │   ├── services/            # API client services
│   │   ├── store/               # Auth context
│   │   └── utils/               # Types, helpers
│   ├── Dockerfile
│   └── nginx.conf
├── docker-compose.yml
└── .env.example
```

## Features

### Opportunity Intelligence
- **Automated Discovery**: Crawl 12+ source types (regulators, tenders, reports, RSS feeds)
- **AI Relevance Detection**: Azure OpenAI determines if content is SupTech/RegTech relevant
- **Smart Extraction**: AI extracts title, institution, country, budget, deadline, standards
- **Classification**: Auto-categorize into suptech, regtech, analytics, risk, taxonomy, etc.
- **Scoring**: Weighted scoring (0-100) based on strategic relevance, budget, timeline, tech match, competition

### Opportunity Lifecycle
Signal Detected → Under Review → Qualified → Active → Pursuing → Closed Won/Lost → Archived

### Search & Discovery
- **Keyword Search**: Full-text search across opportunities
- **Semantic Search**: Natural language queries using embeddings
- **Hybrid Search**: Combined keyword + vector search

### AI Copilot
- Natural language Q&A about opportunities
- RAG-powered with citations and confidence scores
- Contextual chat with session memory
- Suggested prompts for common queries

### Dashboard & Analytics
- KPI cards (total opportunities, high priority, new this week, active RFPs)
- Regional heatmap visualization
- Opportunity trend charts
- Standards adoption tracking (XBRL, SDMX, ISO 20022)

### Reporting
- Automated weekly intelligence reports
- Regional, regulator, trend, and standards reports
- Excel and PDF export
- Email distribution

### Alerts & Notifications
- New high-priority opportunities
- Approaching deadlines (7, 3, 1 day)
- Region trend changes
- Score spikes

### Security & Governance
- JWT authentication with RBAC (Admin, Analyst, Sales User, Viewer)
- SSO via Azure AD (extensible)
- Full audit trail for all actions
- AI decision logging (prompt version, model, tokens, cost)

### Geographic Coverage
13 regions: South Asia, Middle East, North/Southern/Western/Eastern Africa, North/South America, South East/East/Central Asia, Eastern/Western Europe

### Standards Tracked
XBRL, iXBRL, XBRL-CSV, XBRL-JSON, SDMX, ISO 20022, DPM, Taxonomies

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Azure OpenAI API credentials (for AI features)

### 1. Clone and Configure

```bash
cp .env.example .env
# Edit .env with your Azure OpenAI credentials and other settings
```

### 2. Start with Docker Compose

```bash
docker compose up -d
```

This starts:
- **Backend** (FastAPI) on port 8000
- **Frontend** (Nginx + React) on port 80
- **PostgreSQL** on port 5432
- **Redis** on port 6379
- **Celery Worker** for background processing
- **Celery Beat** for scheduled tasks

### 3. Run Database Migrations

```bash
docker compose exec backend alembic upgrade head
```

### 4. Access the Application

- **Frontend**: http://localhost
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

### Local Development

**Backend:**
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

## API Overview

All APIs follow REST conventions with JWT auth and standard response format:

```json
{
  "success": true,
  "data": {},
  "meta": {}
}
```

| Endpoint | Description |
|----------|-------------|
| `POST /api/v1/auth/login` | Authenticate user |
| `GET /api/v1/dashboard/summary` | Dashboard KPIs |
| `GET /api/v1/dashboard/trends` | Weekly trends |
| `GET /api/v1/dashboard/heatmap` | Geographic distribution |
| `POST /api/v1/opportunities/search` | Search & filter opportunities |
| `GET /api/v1/opportunities/{id}` | Opportunity details |
| `PATCH /api/v1/opportunities/{id}` | Update opportunity |
| `POST /api/v1/search/keyword` | Keyword search |
| `POST /api/v1/search/semantic` | Semantic search |
| `POST /api/v1/search/hybrid` | Hybrid search |
| `POST /api/v1/ai/chat` | AI Copilot chat |
| `POST /api/v1/ai/summarize` | Document summarization |
| `GET /api/v1/sources` | List sources |
| `POST /api/v1/sources` | Add source |
| `GET /api/v1/reports` | List reports |
| `POST /api/v1/reports/generate` | Generate report |
| `GET /api/v1/alerts` | List alerts |

## AI Pipeline

```
Document → Relevance Agent → Extraction Agent → Classification Agent → Scoring Agent → Store
              │                    │                    │                   │
              ▼                    ▼                    ▼                   ▼
         Is relevant?        Extract fields      Categorize          Score 0-100
         (confidence)     (title, country...)   (suptech, etc.)    (weighted formula)
```

### Scoring Formula
```
Score = 0.30 × Strategic Relevance
      + 0.25 × Budget Potential
      + 0.20 × Timeline Urgency
      + 0.15 × Technology Match
      + 0.10 × Competition
```

Score Bands: **High** (71-100) | **Medium** (41-70) | **Low** (0-40)

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://...` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `SECRET_KEY` | JWT signing key | (required) |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key | (required for AI) |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL | (required for AI) |
| `AZURE_OPENAI_DEPLOYMENT` | GPT model deployment name | `gpt-4` |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | Embedding model name | `text-embedding-ada-002` |
| `CELERY_BROKER_URL` | Celery broker URL | `redis://localhost:6379/1` |

## User Roles

| Role | Permissions |
|------|------------|
| **Admin** | Full access: manage users, sources, AI config, all data |
| **Analyst** | Review AI findings, validate opportunities, generate reports |
| **Sales User** | View opportunities, update pursuit status, add comments |
| **Viewer** | Read-only access |

## License

Proprietary — IRIS SupTech & RegTech Business
