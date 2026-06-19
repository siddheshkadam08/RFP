"""Detect the country/region of a website from its URL.

Strategy (per the approved design):
  1. Instant: country-code TLD lookup (e.g. .in -> India -> South Asia, .gov -> US).
  2. Fallback: for ambiguous TLDs (.com/.org/.net…), fetch a snippet of the page
     and ask Azure OpenAI. Region is constrained to SOURCE_REGIONS; the country is
     normalized to our canonical list when recognized.

Never raises — returns {"country", "region", "method"} with nulls on failure.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.geo import COUNTRY_REGIONS, SOURCE_REGIONS, match_country, tld_lookup
from app.services import ai_service
from app.services.url_fetcher import fetch_url_content

logger = logging.getLogger(__name__)


def _parse_json(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
        except ValueError:
            return {}
    return data if isinstance(data, dict) else {}


async def detect_location(url: str) -> dict[str, Any]:
    """Return {"country", "region", "method"} for a website URL."""
    country, region = tld_lookup(url)
    if country or region:
        return {"country": country, "region": region, "method": "tld"}

    # Ambiguous TLD — try the AI fallback, with a page snippet when we can fetch it.
    snippet = ""
    try:
        fetched = await fetch_url_content(url, timeout=12.0)
        snippet = f"Page title: {fetched.title}\n{fetched.text[:1500]}"
    except Exception as exc:  # noqa: BLE001 - fetch is best-effort
        logger.info("detect_location: page fetch skipped for %s (%s)", url, exc)

    regions = ", ".join(SOURCE_REGIONS)
    system = (
        "You identify the home COUNTRY and world REGION of the organization that owns a "
        f"website. REGION must be EXACTLY one of: {regions}. "
        'Respond ONLY with compact JSON, e.g. {"country": "Switzerland", "region": "Europe"}. '
        "Use null for a field you cannot determine."
    )
    user = f"URL: {url}\n{snippet}".strip()

    try:
        text = await ai_service.chat_completion(
            [{"role": "system", "content": system}, {"role": "user", "content": user}]
        )
    except Exception as exc:  # noqa: BLE001 - AI is optional
        logger.info("detect_location: AI fallback unavailable for %s (%s)", url, exc)
        return {"country": None, "region": None, "method": "unknown"}

    data = _parse_json(text)
    ai_country = (str(data.get("country") or "")).strip() or None
    ai_region = (str(data.get("region") or "")).strip() or None

    matched = match_country(ai_country)
    if matched:
        # Recognized country -> trust our canonical country + its region.
        return {"country": matched, "region": COUNTRY_REGIONS[matched], "method": "ai"}

    region = ai_region if ai_region in SOURCE_REGIONS else None
    method = "ai" if (ai_country or region) else "unknown"
    return {"country": ai_country, "region": region, "method": method}
