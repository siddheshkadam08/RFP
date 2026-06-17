# 01 — Executive Summary & Business Requirements

## 1.1 Purpose
Defines the product, technical, AI, and data requirements for a production-grade **AI-Powered Global RFP & Opportunity Intelligence System**. The platform continuously monitors global markets to identify, track, analyze, and score business opportunities relevant to IRIS's SupTech and RegTech business.

It detects opportunities not only from published tenders and RFPs, but from **early signals** — strategic plans, annual reports, procurement roadmaps, regulatory announcements, government budgets, modernization programs, and donor-funded projects. The objective: discover opportunities earlier than competitors and enable data-driven business development.

## 1.2 Business Problem
Business development teams face:
- RFPs distributed across thousands of portals
- Many opportunities visible only through indirect signals
- Annual reports and policy papers too lengthy to track manually
- Signals fragmented across geographies and institutions
- High-value opportunities missed for lack of centralized intelligence
- Manual, inconsistent opportunity qualification

Resulting in: missed pipeline, delayed tender response, poor market-trend visibility, inefficient sales targeting.

## 1.3 Proposed Solution
A centralized AI-powered platform that:
- monitors global regulators and public institutions
- crawls websites, tenders, reports, and announcements
- extracts relevant opportunities using AI (Azure OpenAI)
- classifies and scores opportunities
- generates weekly intelligence reports
- enables semantic search and AI Q&A (copilot)
- provides dashboards and Excel/PDF exports

## 1.4 Goals
**Strategic:** earlier opportunity detection · pipeline visibility · bid readiness · regional team support · proactive account targeting.
**Operational:** automate discovery · reduce manual research · improve qualification quality · weekly actionable insights.

## 1.5 Success Metrics (KPIs)
**Opportunity:** opportunities detected/month · qualified opportunities · early-stage (pre-RFP) detections · average opportunity score.
**Platform:** documents processed/week · crawl success rate · AI classification accuracy · AI extraction precision · search latency.
**Business:** opportunities → pipeline · → proposals · win-rate improvement · revenue influenced.

> Each KPI must be queryable from the database (see `audit_logs`, `opportunity_history`) and surfaced on the dashboard.

## 1.6 Target Users & Use Cases
| User | Use cases |
|---|---|
| Executive Leadership | regional strategy, market expansion, trend analysis |
| Sales Teams | opportunity discovery, lead qualification, account planning |
| Pre-Sales Teams | solution mapping, proposal preparation |
| Market Intelligence Analysts | source management, opportunity verification, trend analysis |
| Product Teams | demand trends, standards-adoption monitoring |

## 1.7 Opportunity Categories (business scope)
Regulatory Reporting · Data Collection Platforms · Workflow Platforms · Validation Engines · Analytics Platforms · Risk Platforms · SupTech Transformation.
Each maps to `opportunities.category`. Standards tracked: **XBRL, SDMX, ISO 20022, DPM**.

## 1.8 In / Out of Scope (v1)
**In:** auth/RBAC, source management, crawling, document processing (incl. Azure OpenAI vision OCR), AI extraction/classification/scoring, semantic+keyword+hybrid search, AI copilot, dashboards, Excel/PDF reports, notifications.
**Out:** deployment/infra (DevOps-owned), SMS notifications, OAuth (future), mobile apps, any non-Azure-OpenAI cloud AI service.

## 1.9 Key Constraints
- Azure OpenAI is the **only** external AI dependency.
- Persistent object storage is a **local external hard drive**, accessed via a storage abstraction.
- Database is **local PostgreSQL + pgvector**.
- Embeddings are 3072-dimensional (`text-embedding-3-large`).
