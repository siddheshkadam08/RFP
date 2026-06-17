# 08 — Code Scaffold

Monorepo. No deployment/infra files (DevOps-owned). Local run only.

## Repo Layout
```
rfp-intelligence/
├── README.md
├── .env.example
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── migrations/
│   └── app/
│       ├── main.py
│       ├── core/        # config.py, security.py, logging.py, ai/azure_openai.py
│       ├── db/          # session.py, base.py
│       ├── models/      # one module per table group
│       ├── schemas/     # pydantic
│       ├── api/v1/       # routers: auth, dashboard, opportunities, sources,
│       │                #          reports, alerts, search, ai, admin
│       ├── services/    # business logic
│       ├── repositories/# SQL
│       ├── storage/     # base.py (StorageProvider), local_disk.py
│       ├── agents/      # ingestion_graph.py, copilot_graph.py, nodes/
│       ├── prompts/     # versioned .txt/.jinja
│       ├── workers/     # celery_app.py, crawl.py, process.py, embed.py, report.py
│       └── scheduler/   # periodic.py
└── frontend/
    ├── package.json
    └── src/
        ├── main.tsx, App.tsx
        ├── routes/
        ├── pages/       # Dashboard, Opportunities, OpportunityDetail, Search,
        │                #          Copilot, Reports, Alerts, Sources, Admin
        ├── components/
        ├── services/    # api client (axios), per-domain hooks
        ├── context/     # auth, rbac
        ├── store/
        └── utils/
```

## Backend starter contracts (signatures, not full impl)

### `core/config.py`
```python
class Settings(BaseSettings):
    database_url: str
    redis_url: str
    storage_root: str            # external drive
    jwt_secret: str
    jwt_access_ttl: int = 28800
    azure_openai_endpoint: str
    azure_openai_api_key: str
    azure_openai_gpt_deployment: str = "gpt-4o"
    azure_openai_embed_deployment: str = "text-embedding-3-large"
    azure_openai_api_version: str
    azure_ad_tenant_id: str | None = None
    azure_ad_client_id: str | None = None
    class Config: env_file = ".env"
```

### `storage/base.py`
```python
class StorageProvider(Protocol):
    def save(self, data: bytes, path: str) -> str: ...
    def open(self, path: str) -> BinaryIO: ...
    def exists(self, path: str) -> bool: ...
    def delete(self, path: str) -> None: ...
# local_disk.py: LocalDiskStorage(root=settings.storage_root)
```

### `core/ai/azure_openai.py`
```python
class AzureOpenAIClient:
    def complete(self, messages, *, temperature=0.0, json_mode=False) -> str: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...   # 3072-dim
    def vision_ocr(self, image_bytes: bytes) -> str: ...
    # every call logs tokens + cost to audit_logs
```

### `api/v1/` router pattern
```python
@router.post("/opportunities/search")
async def search(body: OppSearchIn, user=Depends(require_role(...))):
    data, total = await OpportunityService.search(body)
    return envelope(data=data, meta=paginate(body, total))
```

### `agents/ingestion_graph.py`
LangGraph `StateGraph` wiring nodes: detect_relevance → extract_fields → classify_category → score_opportunity → persist_opportunity → emit_alerts (see doc04 §13.1). State carries doc id, chunks, partial fields, cost ledger.

## Frontend starter
- `services/api.ts` — axios instance, attaches JWT, unwraps `{success,data,meta}` envelope, throws on `success:false`.
- `context/AuthContext` + `RequireRole` route guard.
- TanStack Table for all list views; Recharts for dashboard.

## `.env.example`
(see doc 05 §4 — copy and fill; never commit real `.env`)

## Local run (developer machine, not deployment)
```
# DB
createdb rfp && psql rfp -c "CREATE EXTENSION vector; CREATE EXTENSION pg_trgm; CREATE EXTENSION unaccent;"
# backend
cd backend && pip install -e . && alembic upgrade head && uvicorn app.main:app --reload
# workers
celery -A app.workers.celery_app worker -l info
celery -A app.workers.celery_app beat -l info
# frontend
cd frontend && npm install && npm run dev
```

## What this scaffold is / isn't
**Is:** compiling skeleton — schema, migrations, typed APIs, agent graph wiring, storage abstraction, Excel engine, React shell.
**Isn't:** working crawlers (per-source engineering), calibrated AI accuracy (eval-driven), production hardening/perf (E10). These are the real follow-on work, called out in doc 06.
