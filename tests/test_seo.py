import json
import struct
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).parents[1]
STATIC = ROOT / "static"
SITE_URL = "https://gr33nops.github.io/sonkip/"


class SeoDocumentParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title_parts = []
        self.meta = {}
        self.links = []
        self.h1_parts = []
        self.seo_parts = []
        self.schemas = []
        self._in_title = False
        self._in_h1 = False
        self._seo_depth = 0
        self._in_schema = False
        self._schema_parts = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = attributes.get("name") or attributes.get("property")
            if key:
                self.meta[key] = attributes.get("content", "")
        elif tag == "link":
            self.links.append(attributes)
        elif tag == "h1":
            self._in_h1 = True
        elif attributes.get("id") == "seo-content":
            self._seo_depth = 1
        elif self._seo_depth:
            self._seo_depth += 1
        if tag == "script" and attributes.get("type") == "application/ld+json":
            self._in_schema = True
            self._schema_parts = []

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "h1":
            self._in_h1 = False
        if self._seo_depth:
            self._seo_depth -= 1
        if tag == "script" and self._in_schema:
            self.schemas.append(json.loads("".join(self._schema_parts)))
            self._in_schema = False

    def handle_data(self, data):
        if self._in_title:
            self.title_parts.append(data)
        if self._in_h1:
            self.h1_parts.append(data)
        if self._seo_depth:
            self.seo_parts.append(data)
        if self._in_schema:
            self._schema_parts.append(data)


def _document():
    parser = SeoDocumentParser()
    parser.feed((STATIC / "index.html").read_text(encoding="utf-8"))
    return parser


def _schema_nodes(document):
    nodes = []
    for schema in document.schemas:
        nodes.extend(schema.get("@graph", [schema]))
    return {node["@type"]: node for node in nodes}


def test_homepage_exposes_complete_search_and_social_metadata():
    document = _document()
    title = "".join(document.title_parts).strip()
    description = document.meta["description"]
    canonical = next(link["href"] for link in document.links if "canonical" in link.get("rel", "").split())

    assert 45 <= len(title) <= 65
    assert "music downloader" in title.lower()
    assert 130 <= len(description) <= 165
    assert canonical == SITE_URL
    assert document.meta["robots"] == "index, follow, max-image-preview:large"
    assert document.meta["og:type"] == "website"
    assert document.meta["og:url"] == SITE_URL
    assert document.meta["og:image"].startswith(SITE_URL)
    assert document.meta["og:image"].endswith(".png")
    assert document.meta["twitter:card"] == "summary_large_image"


def test_homepage_schema_describes_the_free_cross_platform_application_and_faq():
    schemas = _schema_nodes(_document())
    app = schemas["SoftwareApplication"]
    faq = schemas["FAQPage"]

    assert app["name"] == "Sonkip"
    assert app["url"] == SITE_URL
    assert app["applicationCategory"] == "MultimediaApplication"
    assert set(app["operatingSystem"]) == {"Android", "Windows", "macOS", "Linux"}
    assert app["offers"] == {"@type": "Offer", "price": "0", "priceCurrency": "USD"}
    assert app["softwareVersion"] == "2.7.0"
    assert len(app["featureList"]) >= 5
    assert len(faq["mainEntity"]) >= 5
    assert all(item["@type"] == "Question" for item in faq["mainEntity"])


def test_homepage_has_a_descriptive_h1_and_substantial_crawlable_product_content():
    document = _document()
    h1 = " ".join("".join(document.h1_parts).split())
    seo_copy = " ".join("".join(document.seo_parts).split())

    assert "music downloader" in h1.lower()
    assert len(seo_copy.split()) >= 300
    for phrase in ("Android", "Windows", "macOS", "Linux", "playlist", "metadata", "open source"):
        assert phrase.lower() in seo_copy.lower()


def test_crawlers_receive_robots_sitemap_and_a_large_social_preview():
    robots = (STATIC / "robots.txt").read_text(encoding="utf-8")
    sitemap = ElementTree.parse(STATIC / "sitemap.xml").getroot()
    namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = sitemap.findall("s:url", namespace)
    preview = (STATIC / "sonkip-social.png").read_bytes()

    assert "User-agent: *" in robots
    assert "Allow: /" in robots
    assert f"Sitemap: {SITE_URL}sitemap.xml" in robots
    assert [url.findtext("s:loc", namespaces=namespace) for url in urls] == [SITE_URL]
    assert date.fromisoformat(urls[0].findtext("s:lastmod", namespaces=namespace)) <= date.today()
    assert preview.startswith(b"\x89PNG\r\n\x1a\n")
    assert struct.unpack(">II", preview[16:24]) == (1200, 630)
    assert len(preview) >= 10_000


def test_homepage_self_hosts_fonts_instead_of_blocking_on_google_fonts():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    stylesheet = (STATIC / "style.css").read_text(encoding="utf-8")
    font_files = [
        STATIC / "fonts" / "dm-mono-400.woff2",
        STATIC / "fonts" / "dm-mono-500.woff2",
        STATIC / "fonts" / "manrope.woff2",
    ]

    assert "fonts.googleapis.com" not in html
    assert "fonts.gstatic.com" not in html
    assert "@font-face" in stylesheet
    for font_file in font_files:
        assert font_file.read_bytes().startswith(b"wOF2")
