"""Geo reference data + URL-based country/region detection helpers.

Single source of truth for:
  * ``SOURCE_REGIONS`` — the curated region list (also re-exported by models.source).
  * ``COUNTRY_REGIONS`` — country -> region map (drives the Country dropdown and
    lets the UI auto-fill Region when a country is chosen).
  * ``CCTLD_COUNTRIES`` — country-code TLD -> country, for instant URL detection.

No Phase-1 reference tables exist, so these constants are authoritative and are
exposed to the frontend via ``GET /sources/options``.
"""
from __future__ import annotations

from urllib.parse import urlparse

SOURCE_REGIONS: list[str] = [
    "North America",
    "Latin America & Caribbean",
    "Europe",
    "Middle East & North Africa",
    "Sub-Saharan Africa",
    "Asia Pacific",
    "South Asia",
    "Global",
]

# Countries grouped by region (kept readable); flattened into COUNTRY_REGIONS below.
_COUNTRIES_BY_REGION: dict[str, list[str]] = {
    "North America": ["United States", "Canada"],
    "Latin America & Caribbean": [
        "Mexico", "Brazil", "Argentina", "Chile", "Colombia", "Peru", "Ecuador",
        "Uruguay", "Paraguay", "Bolivia", "Venezuela", "Panama", "Costa Rica",
        "Dominican Republic", "Jamaica", "Trinidad and Tobago", "Bahamas", "Barbados",
    ],
    "Europe": [
        "United Kingdom", "Ireland", "Germany", "France", "Spain", "Portugal", "Italy",
        "Netherlands", "Belgium", "Luxembourg", "Switzerland", "Austria", "Denmark",
        "Sweden", "Norway", "Finland", "Iceland", "Poland", "Czech Republic", "Slovakia",
        "Hungary", "Romania", "Bulgaria", "Greece", "Croatia", "Slovenia", "Estonia",
        "Latvia", "Lithuania", "Ukraine", "Russia", "Turkey", "Cyprus", "Malta",
    ],
    "Middle East & North Africa": [
        "United Arab Emirates", "Saudi Arabia", "Qatar", "Kuwait", "Bahrain", "Oman",
        "Israel", "Jordan", "Lebanon", "Egypt", "Morocco", "Tunisia", "Algeria", "Iraq", "Iran",
    ],
    "Sub-Saharan Africa": [
        "Nigeria", "Kenya", "South Africa", "Ghana", "Ethiopia", "Tanzania", "Uganda",
        "Rwanda", "Senegal", "Côte d'Ivoire", "Cameroon", "Zambia", "Zimbabwe",
        "Mozambique", "Angola", "Botswana", "Namibia", "Mauritius",
    ],
    "Asia Pacific": [
        "China", "Japan", "South Korea", "Singapore", "Malaysia", "Indonesia", "Thailand",
        "Philippines", "Vietnam", "Hong Kong", "Taiwan", "Australia", "New Zealand",
        "Cambodia", "Myanmar", "Brunei", "Mongolia",
    ],
    "South Asia": [
        "India", "Pakistan", "Bangladesh", "Sri Lanka", "Nepal", "Bhutan", "Maldives", "Afghanistan",
    ],
    "Global": ["Global / Multilateral"],
}

COUNTRY_REGIONS: dict[str, str] = {
    country: region for region, countries in _COUNTRIES_BY_REGION.items() for country in countries
}

# Sorted list for the dropdown.
SOURCE_COUNTRIES: list[str] = sorted(COUNTRY_REGIONS)

# Country-code TLD -> country (must be a key in COUNTRY_REGIONS).
CCTLD_COUNTRIES: dict[str, str] = {
    "us": "United States", "ca": "Canada",
    "mx": "Mexico", "br": "Brazil", "ar": "Argentina", "cl": "Chile", "co": "Colombia",
    "pe": "Peru", "ec": "Ecuador", "uy": "Uruguay", "py": "Paraguay", "bo": "Bolivia",
    "ve": "Venezuela", "pa": "Panama", "cr": "Costa Rica", "do": "Dominican Republic",
    "jm": "Jamaica", "tt": "Trinidad and Tobago", "bs": "Bahamas", "bb": "Barbados",
    "uk": "United Kingdom", "gb": "United Kingdom", "ie": "Ireland", "de": "Germany",
    "fr": "France", "es": "Spain", "pt": "Portugal", "it": "Italy", "nl": "Netherlands",
    "be": "Belgium", "lu": "Luxembourg", "ch": "Switzerland", "at": "Austria", "dk": "Denmark",
    "se": "Sweden", "no": "Norway", "fi": "Finland", "is": "Iceland", "pl": "Poland",
    "cz": "Czech Republic", "sk": "Slovakia", "hu": "Hungary", "ro": "Romania",
    "bg": "Bulgaria", "gr": "Greece", "hr": "Croatia", "si": "Slovenia", "ee": "Estonia",
    "lv": "Latvia", "lt": "Lithuania", "ua": "Ukraine", "ru": "Russia", "tr": "Turkey",
    "cy": "Cyprus", "mt": "Malta",
    "ae": "United Arab Emirates", "sa": "Saudi Arabia", "qa": "Qatar", "kw": "Kuwait",
    "bh": "Bahrain", "om": "Oman", "il": "Israel", "jo": "Jordan", "lb": "Lebanon",
    "eg": "Egypt", "ma": "Morocco", "tn": "Tunisia", "dz": "Algeria", "iq": "Iraq", "ir": "Iran",
    "ng": "Nigeria", "ke": "Kenya", "za": "South Africa", "gh": "Ghana", "et": "Ethiopia",
    "tz": "Tanzania", "ug": "Uganda", "rw": "Rwanda", "sn": "Senegal", "ci": "Côte d'Ivoire",
    "cm": "Cameroon", "zm": "Zambia", "zw": "Zimbabwe", "mz": "Mozambique", "ao": "Angola",
    "bw": "Botswana", "na": "Namibia", "mu": "Mauritius",
    "cn": "China", "jp": "Japan", "kr": "South Korea", "sg": "Singapore", "my": "Malaysia",
    "id": "Indonesia", "th": "Thailand", "ph": "Philippines", "vn": "Vietnam", "hk": "Hong Kong",
    "tw": "Taiwan", "au": "Australia", "nz": "New Zealand", "kh": "Cambodia", "mm": "Myanmar",
    "bn": "Brunei", "mn": "Mongolia",
    "in": "India", "pk": "Pakistan", "bd": "Bangladesh", "lk": "Sri Lanka", "np": "Nepal",
    "bt": "Bhutan", "mv": "Maldives", "af": "Afghanistan",
}

# Common free-text aliases the AI fallback (or a user) might produce -> canonical name.
_COUNTRY_ALIASES: dict[str, str] = {
    "usa": "United States", "u.s.": "United States", "u.s.a.": "United States",
    "united states of america": "United States", "america": "United States",
    "uk": "United Kingdom", "u.k.": "United Kingdom", "great britain": "United Kingdom",
    "britain": "United Kingdom", "england": "United Kingdom",
    "uae": "United Arab Emirates", "emirates": "United Arab Emirates",
    "korea": "South Korea", "republic of korea": "South Korea",
    "russian federation": "Russia", "czechia": "Czech Republic",
    "ivory coast": "Côte d'Ivoire", "cote d'ivoire": "Côte d'Ivoire",
    "the netherlands": "Netherlands", "hong kong sar": "Hong Kong",
}

_COUNTRY_LOOKUP: dict[str, str] = {country.lower(): country for country in COUNTRY_REGIONS}


def _hostname(url: str) -> str:
    raw = (url or "").strip()
    if "://" not in raw:
        raw = "http://" + raw
    return (urlparse(raw).hostname or "").lower()


def tld_lookup(url: str) -> tuple[str | None, str | None]:
    """Best-effort (country, region) from the URL's top-level domain.

    Returns the canonical country and its region for country-code TLDs (and the
    US-only ``.gov``/``.mil``); ``(None, 'Europe')`` for ``.eu``; otherwise
    ``(None, None)`` so the caller can fall back to AI.
    """
    host = _hostname(url)
    if not host:
        return None, None
    last_label = host.rsplit(".", 1)[-1]

    country = CCTLD_COUNTRIES.get(last_label)
    if country:
        return country, COUNTRY_REGIONS.get(country)
    if last_label in {"gov", "mil"}:  # restricted to US government
        return "United States", COUNTRY_REGIONS["United States"]
    if last_label == "int":  # international treaty organizations
        return "Global / Multilateral", COUNTRY_REGIONS["Global / Multilateral"]
    if last_label == "eu":  # pan-European, no single country
        return None, "Europe"
    return None, None


def match_country(name: str | None) -> str | None:
    """Map a free-text country name to a canonical COUNTRY_REGIONS key, or None."""
    if not name:
        return None
    key = name.strip().lower()
    return _COUNTRY_LOOKUP.get(key) or _COUNTRY_ALIASES.get(key)
