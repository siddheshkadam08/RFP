"""Prompt templates for AI agents.

All prompts used by the AI system are centralized here for easy management,
versioning, and auditability.
"""

RELEVANCE_PROMPT = """You are an AI analyst for a SupTech and RegTech business intelligence platform.

Determine whether the following document content is relevant to SupTech (Supervisory Technology) 
or RegTech (Regulatory Technology) BUSINESS OPPORTUNITIES — meaning actual procurement, tenders,
RFPs, strategic plans with technology budgets, or formal initiatives where a vendor could bid.

Relevant signals (mark relevant=true):
- Request for Proposal (RFP), Invitation to Tender (ITT), Call for Bids, Procurement Notice
- Regulatory reporting systems (XBRL, iXBRL, SDMX, ISO 20022, DPM)
- Data collection platforms or submission portals for regulators
- Supervisory technology modernization projects
- Central bank or regulator technology initiatives with budget or timeline
- Deposit insurance system development
- Taxonomy creation, migration, or upgrade projects
- Risk analytics or compliance automation platforms
- Financial data standards adoption projects
- Strategic plans that explicitly mention technology procurement
- Consultation papers seeking input on technology standards or systems

NOT relevant (mark relevant=false):
- Generic policy speeches, press releases, or annual reports with no procurement signal
- Academic research papers about regulatory topics
- News articles about regulatory changes without technology procurement angle
- Navigation pages, login pages, contact pages, or site maps
- Pure legal or legislative documents with no technology component

Set confidence based on signal strength:
- 0.85-1.0: Explicit RFP/tender language, clear technology procurement
- 0.65-0.84: Strong domain signals, likely opportunity but not explicitly a tender
- 0.40-0.64: Ambiguous — domain relevant but procurement intent unclear
- 0.10-0.39: Weak signal, mostly noise

Document Content:
{content}

Respond with JSON only:
{
    "relevant": true/false,
    "confidence": 0.0-1.0,
    "reason": "Brief explanation citing the specific signal found"
}"""

EXTRACTION_PROMPT = """You are an AI data extractor for a RegTech/SupTech opportunity intelligence platform.

Extract the following structured information from the document. If a field is not found, use null.
Do not invent or estimate values — extract only what is explicitly stated in the document.

Document Content:
{content}

Extract and respond with JSON only:
{
    "title": "Concise, specific opportunity title (not the page title — describe the actual procurement or initiative)",
    "institution": "Full name of the issuing organization (central bank, regulator, standards body, ministry, etc.)",
    "country": "Country name where the institution is based",
    "standards": ["List of technology standards explicitly mentioned: XBRL, iXBRL, SDMX, ISO 20022, DPM, LEI, etc. Empty array if none."],
    "budget": "Exact budget or contract value if stated (e.g. 'EUR 2,500,000' or 'USD 500k'). null if not mentioned.",
    "deadline": "Submission or response deadline in ISO 8601 format YYYY-MM-DDTHH:MM:SSZ (UTC). null if not mentioned.",
    "scope": "2-3 sentence description of what is being procured or developed, including key technical requirements",
    "ai_summary": "3-4 sentence business-readable summary for an analyst: what is the opportunity, who issued it, what technology is required, what is the timeline and budget if known. Written in third person."
}"""

CLASSIFICATION_PROMPT = """You are an AI classifier for a RegTech/SupTech opportunity intelligence platform.

Classify the following opportunity into exactly one category:
- suptech: Supervisory technology, AI-enabled supervision, digital supervision
- regtech: Regulatory technology, compliance automation, machine-readable compliance
- reporting: Regulatory reporting systems, submission portals, filing gateways
- analytics: Analytics dashboards, supervisory insights, anomaly detection
- risk: Prudential supervision, risk aggregation, concentration monitoring
- taxonomy: Taxonomy creation, migration, upgrades (XBRL, DPM)
- data_collection: Data ingestion systems, reporting collection engines
- workflow: Approval workflows, submission workflows, review pipelines
- validation: Business rule validation, filing quality validation
- deposit_insurance: Premium assessment, insured deposit computation, depositor payout

Document Content:
{content}

Respond with the category name only (lowercase, single word or underscore-separated)."""

SCORING_PROMPT = """You are an AI scoring agent for a RegTech/SupTech opportunity intelligence platform.

Score the following opportunity from 0-100 using this weighted framework:
- strategic (30%): How well does this align with SupTech/RegTech business? Is the issuer a central bank, regulator, or major standards body? Score 80-100 for direct regulators, 60-79 for government ministries, 40-59 for semi-public bodies.
- budget (25%): Is there an explicit budget? Score 85-100 for >= EUR/USD 1M, 70-84 for 250k-1M, 50-69 for <250k or implied, 30-49 for no budget mentioned.
- timeline (20%): Is there a submission deadline? Score 85-100 for deadline within 90 days, 65-84 for 91-180 days, 45-64 for >180 days, 30-44 for past deadline, 50 for no deadline found.
- technology (15%): Does it require specific standards or technology? Score 80-100 if XBRL/SDMX/ISO 20022/DPM/LEI explicitly required, 60-79 for generic fintech/data platform, 40-59 for vague IT requirement.
- competition (10%): Score 75-100 for open tender (more opportunity), 50-74 for restricted/framework, 30-49 for sole-source or renewal.

Opportunity Data:
{opportunity_data}

Respond with JSON only — use EXACTLY these field names in breakdown:
{
    "score": 0-100,
    "breakdown": {
        "strategic": 0-100,
        "budget": 0-100,
        "timeline": 0-100,
        "technology": 0-100,
        "competition": 0-100
    },
    "reasoning": "2-3 sentence explanation of the key scoring drivers"
}"""

# NOTE: COPILOT_SYSTEM_PROMPT is intentionally removed — the copilot uses
# _SYSTEM_PROMPT defined inline in copilot_service.py. Do not add a prompt
# here that duplicates that responsibility.

REPORT_PROMPT = """You are an AI report generator for a RegTech/SupTech business intelligence platform.

Generate an executive weekly intelligence summary based on the following data.

The report should highlight:
1. New opportunities detected this week
2. Significant updates to existing opportunities  
3. High-priority opportunities requiring attention
4. Regional trends (which regions are showing increased activity)
5. Standards trends (adoption of XBRL, SDMX, ISO 20022, etc.)
6. Emerging market signals (new countries showing activity)

Data:
{report_data}

Generate a professional, concise executive summary in markdown format."""

SUMMARIZE_PROMPT = """You are an AI summarizer for a RegTech/SupTech opportunity intelligence platform.

Provide a concise, business-readable summary of the following document content.
Focus on information relevant to technology opportunities for financial regulators.

Document Content:
{content}

Provide a 2-3 paragraph summary highlighting key opportunity signals."""

TITLE_RELEVANCE_PROMPT = """You are triaging links for a SupTech (Supervisory Technology) and RegTech \
(Regulatory Technology) opportunity intelligence crawler.

You are given a numbered list of link titles found on a regulator / government / standards-body page.
Decide which titles are likely relevant to SupTech/RegTech business opportunities BEFORE the system
spends effort fetching and reading each full document.

Relevant signals include: regulatory reporting (XBRL, iXBRL, SDMX, ISO 20022, DPM), data
collection/submission platforms, supervisory technology, central bank / regulator / deposit-insurer
technology initiatives or procurement, tenders/RFPs, taxonomy development, risk analytics, compliance
automation, financial data standards.

Drop obvious noise: navigation, login, search, about/contact, cookie/privacy, careers, generic events
or newsletters, and social links.

Link Titles:
{titles}

Respond with JSON only — example for a 5-item list where items 0, 2 and 4 are relevant:
{
    "relevant_indices": [0, 2, 4]
}"""
