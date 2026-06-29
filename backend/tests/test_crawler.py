"""Crawler discovery: registrable-domain / cross-domain policy, embedded-doc mining, pagination.

Pure-function tests (no network) covering the gaps fixed in the multi-depth crawler upgrade.
"""
from app.services import crawler as C


# --- registrable_domain (eTLD+1 without external deps) ------------------------

def test_registrable_domain_handles_multi_part_suffixes():
    assert C.registrable_domain("rbidocs.rbi.org.in") == "rbi.org.in"
    assert C.registrable_domain("www.rbi.org.in") == "rbi.org.in"
    assert C.registrable_domain("a.b.example.co.uk") == "example.co.uk"


def test_registrable_domain_plain_and_ip():
    assert C.registrable_domain("www.sec.gov") == "sec.gov"
    assert C.registrable_domain("example.com") == "example.com"
    assert C.registrable_domain("192.168.0.1") == "192.168.0.1"  # bare IP untouched


# --- cross-domain follow policy ----------------------------------------------

def test_same_site_uses_registrable_domain():
    assert C._same_site("rbidocs.rbi.org.in", "www.rbi.org.in")
    assert not C._same_site("evil.com", "www.rbi.org.in")


def test_accept_url_classification(monkeypatch):
    monkeypatch.setattr(C.settings, "CRAWL_ALLOW_CROSS_DOMAIN", True)
    base = "www.rbi.org.in"
    assert C._accept_url("https://cdn.example.com/tender.pdf", base) == "doc"   # cross-domain doc OK
    assert C._accept_url("https://other.com/page", base) is None                # cross-domain HTML dropped
    assert C._accept_url("https://rbidocs.rbi.org.in/x/notice", base) == "page" # sibling subdomain HTML OK
    assert C._accept_url("https://www.rbi.org.in/banner.png", base) is None     # blocked extension
    assert C._accept_url("https://www.rbi.org.in/login", base) is None          # noise path


def test_accept_url_cross_domain_disabled(monkeypatch):
    monkeypatch.setattr(C.settings, "CRAWL_ALLOW_CROSS_DOMAIN", False)
    base = "www.rbi.org.in"
    assert C._accept_url("https://cdn.example.com/tender.pdf", base) is None     # off-domain doc now blocked
    assert C._accept_url("https://www.rbi.org.in/a/notice.pdf", base) == "doc"   # same-host doc still OK


# --- embedded document mining (<iframe>/<embed>/<object>) ---------------------

def test_extract_links_mines_embedded_documents(monkeypatch):
    monkeypatch.setattr(C.settings, "CRAWL_ALLOW_CROSS_DOMAIN", True)
    html = """<html><body>
      <a href="/Scripts/detail.aspx">Tender Detail</a>
      <iframe src="https://rbidocs.rbi.org.in/rdocs/tender/PDFs/NOTICE123.PDF"></iframe>
      <embed src="/files/embedded.pdf">
      <object data="https://cdn.thirdparty.com/external.pdf"></object>
      <a href="/login">Login</a>
    </body></html>"""
    urls = [c.url for c in C.extract_links("https://www.rbi.org.in/Scripts/list.aspx", html)]
    assert any("NOTICE123.PDF" in u for u in urls)       # iframe PDF
    assert any("embedded.pdf" in u for u in urls)         # embed PDF
    assert any("external.pdf" in u for u in urls)         # cross-domain <object> PDF
    assert any("detail.aspx" in u for u in urls)          # normal link
    assert not any("/login" in u for u in urls)           # noise path filtered


# --- pagination discovery -----------------------------------------------------

def test_discover_pagination_finds_get_links_only():
    html = """<html><head><link rel="next" href="?page=2"></head><body>
      <a href="?frmpage=2">Next &rsaquo;</a>
      <a href="/unrelated">A long descriptive sentence that merely contains next somewhere</a>
      <a href="javascript:__doPostBack('grid','Page$2')">2</a>
    </body></html>"""
    nexts = C.discover_pagination("https://www.rbi.org.in/Scripts/list.aspx", html)
    assert any("page=2" in u for u in nexts)              # rel=next
    assert any("frmpage=2" in u for u in nexts)           # "Next" anchor text
    assert not any("doPostBack" in u for u in nexts)      # postback pager excluded (no real href)
    assert not any("/unrelated" in u for u in nexts)      # long non-next text excluded
