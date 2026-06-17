# 07 — UI Wireframes

Low-fidelity layouts. Stack: React + TypeScript + MUI + TanStack Table + Chart.js/Recharts. All actions are RBAC-gated (server-enforced).

## Global Shell
```
┌──────────────────────────────────────────────────────────────┐
│ [≡] RFP Intelligence      🔍 global search    🔔(3)  [User ▾]  │
├───────────┬──────────────────────────────────────────────────┤
│ Dashboard │                                                  │
│ Opportun. │              <page content>                      │
│ Search    │                                                  │
│ Copilot   │                                                  │
│ Reports   │                                                  │
│ Alerts    │                                                  │
│ Sources   │                                                  │
│ Admin*    │   (* admin only)                                 │
└───────────┴──────────────────────────────────────────────────┘
```

## Dashboard
```
┌ KPIs ─────────────────────────────────────────────┐
│ [Total 1,234] [High 92] [New/wk 18] [Regions 13]   │
├ Trends (line) ──────────────┬ Heatmap (geo) ───────┤
│  opportunities over weeks    │  by country/region   │
├ Top Opportunities (table) ──────────────────────── ┤
│ Title | Country | Regulator | Score | Status | →   │
└────────────────────────────────────────────────────┘
```
APIs: `/dashboard/summary`, `/dashboard/trends`, `/dashboard/heatmap`.

## Opportunities (Explorer)
```
┌ Filters ───────────────────────────────────────────┐
│ Region▾ Regulator▾ Category▾ Status▾ Score≥[__]      │
│ Date[__–__]               [Apply] [Export Excel ⬇]  │
├ Results (TanStack Table, sortable, paginated) ───── ┤
│ ☐ Title        Country  Reg.  Cat.  Score  Status   │
│ ☐ XBRL portal  India    RBI   RegRpt  86    new  →  │
│ ☐ ...                                               │
│                          ◀ 1 2 3 … ▶  50/page       │
└─────────────────────────────────────────────────────┘
```
API: `POST /opportunities/search`. Row → Detail.

## Opportunity Detail
```
┌ Header: Title  [Score 86 ●High]  Status[qualified▾]  Owner[▾] ┐
├ Summary (AI) ─────────────────────────────────────────────── ┤
├ Score breakdown (5 dims, bars) ─────┬ Metadata ───────────────┤
│ Relevance 27/30, Stage 16/20, ...   │ Country, Regulator,     │
│                                     │ Budget, Deadline        │
├ Source & Citations ───────────────────────────────────────── ┤
│ link to source document + cited chunks                       │
├ History ──────────────────────┬ Comments ─────────────────── ┤
│ status/owner changes timeline  │ threaded comments + add box  │
└──────────────────────────────────────────────────────────────┘
```
APIs: `GET/PATCH /opportunities/{id}`, `POST .../comments`.

## Search
```
┌ [ query input.............................. ]  [Search] ┐
│ Mode: ( ) Keyword  ( ) Semantic  (•) Hybrid            │
├ Results: ranked list w/ snippet + source + score ───── ┤
└────────────────────────────────────────────────────────┘
```
APIs: `/search/keyword|semantic|hybrid`.

## Copilot
```
┌ Sessions ▾ ─────────────┬ Chat ──────────────────────────────┐
│ • Africa opportunities   │ user: top opps in Africa           │
│ • Standards adoption      │ asst: … [1][2] (conf 0.92)         │
│ + New session             │ ┌ citations: doc#, chunk ────────┐│
│                           │ └────────────────────────────────┘│
│                           │ [ ask something...........] [Send] │
└───────────────────────────┴────────────────────────────────────┘
```
API: `POST /ai/chat`. Citations clickable → source doc.

## Reports
```
┌ Generate ──────────────────────────────────────────┐
│ Type: (•)Weekly ( )Monthly ( )Custom  [params...]   │
│ [Generate]                                          │
├ History ─────────────────────────────────────────── ┤
│ Type   Date        By        [Download xlsx][pdf]   │
└─────────────────────────────────────────────────────┘
```
APIs: `/reports`, `/reports/generate`, `/reports/{id}/download`.

## Alerts
```
┌ Filter: All | Unread ───────────────────────────────┐
│ ● [deadline] Opp X due in 7 days        [mark read]  │
│   [opportunity] New high-score in Kenya             │
└──────────────────────────────────────────────────────┘
```
APIs: `/alerts`, `PATCH /alerts/{id}`.

## Sources (Analyst/Admin)
```
┌ [+ Add Source] ────────────────────────────────────┐
│ Name     URL          Type   Freq   LastCrawl  ●    │
│ RBI site https://...  website daily  2h ago    ✓ → │
│ [crawl now] on row                                  │
└──────────────────────────────────────────────────────┘
```
APIs: `/sources` CRUD, `/sources/{id}/crawl`.

## Admin (Admin only)
Tabs: Users · Prompts · Models · Scheduler · AI Costs · Feature Flags.
```
┌ Users ─────────────────────────────────────────────┐
│ Email           Role▾      Active   [Save]          │
├ Prompts ───────────────────────────────────────────┤
│ prompt_name  version  [edit] [activate]             │
├ AI Costs ──────────────────────────────────────────┤
│ tokens & cost by day / model (from audit_logs)      │
└─────────────────────────────────────────────────────┘
```
