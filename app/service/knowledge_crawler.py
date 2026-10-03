"""Bounded public-source ingestion with pinned public DNS and explicit provenance."""
from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import ipaddress
import json
import socket
import time
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.service.knowledge import KnowledgeDocumentInput, MAX_UPLOAD_BYTES, _timestamp

ALLOWED_HOSTS = frozenset({"arxiv.org", "export.arxiv.org", "rss.arxiv.org", "www.sqlite.org", "sqlite.org",
                           "faculty.chicagobooth.edu", "www0.gsb.columbia.edu", "bse.eu"})
SOURCE_SEEDS = (
    {"source_id": "arxiv-retrieval-foundations", "title": "RAG、ALCE、Self-RAG 原始论文", "enabled": True,
     "url": "https://export.arxiv.org/api/query?id_list=2005.11401,2305.14627,2310.11511", "format": "ATOM", "kind": "PAPER"},
    {"source_id": "arxiv-quant-finance", "title": "arXiv Quantitative Finance RSS", "enabled": True,
     "url": "https://rss.arxiv.org/rss/q-fin", "format": "RSS", "kind": "PAPER"},
)
MAX_FEED_ITEMS = 10
DEFAULT_INTERVAL_SECONDS = 24 * 60 * 60


def _is_public(address: str) -> bool:
    parsed = ipaddress.ip_address(address)
    return parsed.is_global and not parsed.is_multicast


class KnowledgeSourceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=1, max_length=2000)
    format: str = Field(pattern=r"^(RSS|ATOM|HTML|PDF)$")
    enabled: bool = True
    kind: str = Field(default="PAPER", pattern=r"^(ANNOUNCEMENT|FINANCIAL_REPORT|RESEARCH_REPORT|METHOD|PAPER|OTHER)$")
    published_at: str | None = None
    page_size: int = Field(default=10, ge=1, le=20)

    @model_validator(mode="after")
    def validate_source(self):
        validate_public_url(self.url)
        if self.format == "PDF":
            _feed_time(self.published_at)
        return self


class CrawlRefused(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def validate_public_url(url: str, *, allowed_hosts=ALLOWED_HOSTS) -> tuple[str, str]:
    try:
        parsed = urlsplit(url)
        hostname = (parsed.hostname or "").casefold()
        if parsed.scheme != "https" or parsed.port not in (None, 443) or parsed.username or parsed.password:
            raise ValueError("invalid origin")
        if hostname not in allowed_hosts or any(ord(char) < 32 for char in url):
            raise ValueError("unapproved hostname")
        return hostname, urlunsplit(("https", hostname, parsed.path or "/", parsed.query, ""))
    except ValueError:
        raise CrawlRefused("SOURCE_URL_REFUSED") from None


async def resolve_public_address(hostname: str) -> str:
    try:
        addresses = await asyncio.to_thread(socket.getaddrinfo, hostname, 443, 0, socket.SOCK_STREAM)
        values = list(dict.fromkeys(item[4][0] for item in addresses))
        if not values or any(not _is_public(value) for value in values):
            raise ValueError("non-public address")
        # Connect to this address rather than letting the HTTP stack resolve the
        # hostname again; this prevents DNS changes between check and connection.
        return values[0]
    except (OSError, ValueError):
        raise CrawlRefused("SOURCE_ADDRESS_REFUSED") from None


class PublicSourceFetcher:
    def __init__(self, *, transport=None, resolver=resolve_public_address, allowed_hosts=ALLOWED_HOSTS):
        self.resolver, self.allowed_hosts = resolver, allowed_hosts
        self.client = httpx.AsyncClient(transport=transport, timeout=20, follow_redirects=False, trust_env=False,
                                        limits=httpx.Limits(max_connections=4, max_keepalive_connections=4))
        self._arxiv_last_request = 0.0
        self._arxiv_lock = asyncio.Lock()

    async def fetch(self, url: str) -> tuple[bytes, str, str]:
        for _ in range(4):
            hostname, normalized = validate_public_url(url, allowed_hosts=self.allowed_hosts)
            address = await self.resolver(hostname)
            if not _is_public(address):
                raise CrawlRefused("SOURCE_ADDRESS_REFUSED")
            if hostname.endswith("arxiv.org"):
                async with self._arxiv_lock:
                    elapsed = time.monotonic() - self._arxiv_last_request
                    if elapsed < 3:
                        await asyncio.sleep(3 - elapsed)
                    self._arxiv_last_request = time.monotonic()
            parsed = urlsplit(normalized)
            host = f"[{address}]" if ":" in address else address
            pinned = urlunsplit(("https", host, parsed.path, parsed.query, ""))
            try:
                async with self.client.stream("GET", pinned, headers={"Host": hostname, "User-Agent": "PrismResearchLibrary/1.0"},
                                              extensions={"sni_hostname": hostname}) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise CrawlRefused("REDIRECT_REFUSED")
                        url = urljoin(normalized, location)
                        validate_public_url(url, allowed_hosts=self.allowed_hosts)
                        continue
                    response.raise_for_status()
                    size = response.headers.get("content-length")
                    if size is not None and (not size.isdigit() or int(size) > MAX_UPLOAD_BYTES):
                        raise CrawlRefused("SOURCE_BODY_TOO_LARGE")
                    content = bytearray()
                    async for part in response.aiter_bytes(chunk_size=65536):
                        content.extend(part)
                        if len(content) > MAX_UPLOAD_BYTES:
                            raise CrawlRefused("SOURCE_BODY_TOO_LARGE")
                    return bytes(content), response.headers.get("content-type", "").split(";", 1)[0].casefold(), normalized
            except httpx.HTTPError:
                raise CrawlRefused("SOURCE_HTTP_UNAVAILABLE") from None
        raise CrawlRefused("REDIRECT_LIMIT")

    async def close(self):
        await self.client.aclose()


class _ArticleParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.published_at, self.title = [], None, []
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in {"script", "style", "nav", "aside"}:
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag == "meta" and (attributes.get("property") or attributes.get("name", "")).casefold() in {"article:published_time", "date", "dc.date", "citation_publication_date"}:
            self.published_at = attributes.get("content")
        if tag in {"p", "div", "section", "tr", "h1", "h2", "h3", "br"}:
            self.parts.append("\n")
        if tag in {"td", "th"}:
            self.parts.append(" | ")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "nav", "aside"} and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title.append(data)
        elif not self._skip:
            self.parts.append(data)


def extract_article_html(content: bytes) -> dict:
    try:
        parser = _ArticleParser()
        parser.feed(content.decode("utf-8"))
        text = "".join(parser.parts).strip()
        if not text:
            raise ValueError("empty article")
        return {"title": "".join(parser.title).strip(), "text": text, "published_at": parser.published_at}
    except (UnicodeError, ValueError):
        raise CrawlRefused("SOURCE_TEXT_UNAVAILABLE") from None


def _feed_time(value: str | None) -> str:
    if not value:
        raise CrawlRefused("PUBLICATION_TIME_REQUIRED")
    try:
        return _timestamp(value)
    except (ValueError, AttributeError):
        try:
            return _timestamp(parsedate_to_datetime(value))
        except (ValueError, TypeError, AttributeError):
            raise CrawlRefused("PUBLICATION_TIME_REQUIRED") from None


def parse_feed(content: bytes, *, limit=MAX_FEED_ITEMS) -> list[dict]:
    if b"<!DOCTYPE" in content.upper() or b"<!ENTITY" in content.upper():
        raise CrawlRefused("XML_DECLARATION_REFUSED")
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        raise CrawlRefused("SOURCE_FEED_INVALID") from None
    atom = "{http://www.w3.org/2005/Atom}"
    items = []
    entries = root.findall(f"{atom}entry") or root.findall("./channel/item")
    for entry in entries[:limit]:
        title = entry.findtext(f"{atom}title") or entry.findtext("title") or ""
        summary = entry.findtext(f"{atom}summary") or entry.findtext("description") or ""
        published = entry.findtext(f"{atom}published") or entry.findtext("pubDate")
        link = entry.findtext("link")
        pdf = None
        for element in entry.findall(f"{atom}link"):
            if element.attrib.get("type") == "application/pdf" or element.attrib.get("title") == "pdf":
                pdf = element.attrib.get("href")
            elif element.attrib.get("rel", "alternate") == "alternate":
                link = element.attrib.get("href")
        if link and link.startswith("http://") and urlsplit(link).hostname in ALLOWED_HOSTS:
            link = "https://" + link[len("http://"):]
        if pdf and pdf.startswith("http://") and urlsplit(pdf).hostname in ALLOWED_HOSTS:
            pdf = "https://" + pdf[len("http://"):]
        if not title.strip() or not link:
            continue
        try:
            published_at = _feed_time(published)
            validate_public_url(link)
            if pdf:
                validate_public_url(pdf)
        except CrawlRefused:
            continue
        if "<" in summary:
            summary = extract_article_html(summary.encode())["text"]
        items.append({"title": " ".join(title.split())[:500], "text": summary.strip(), "source_url": link,
                      "published_at": published_at, "pdf_url": pdf})
    return items


class KnowledgeCrawler:
    def __init__(self, service, *, fetcher=None, interval_seconds=DEFAULT_INTERVAL_SECONDS, seeds=SOURCE_SEEDS):
        if interval_seconds < 1:
            raise ValueError("crawl interval must be positive")
        self.service = service
        self.fetcher = fetcher or PublicSourceFetcher()
        self.interval_seconds = interval_seconds
        self._task = None
        self._run_lock = asyncio.Lock()
        with self.service.store._lock:
            for seed in seeds:
                validate_public_url(seed["url"])
                existing = self.service.store._connection.execute("SELECT source_id FROM knowledge_sources WHERE source_id=?", (seed["source_id"],)).fetchone()
                if not existing:
                    self._save_source({**seed, "last_run_at": None, "last_status": "NOT_RUN", "last_error": None})

    def _save_source(self, source):
        encoded = json.dumps(source, ensure_ascii=False, sort_keys=True)
        updated = _timestamp(self.service.clock())
        connection = self.service.store._connection
        with self.service.store._lock:
            existing = connection.execute("SELECT source_id FROM knowledge_sources WHERE source_id=?", (source["source_id"],)).fetchone()
            if existing:
                connection.execute("UPDATE knowledge_sources SET payload_json=?,updated_at=? WHERE source_id=?", (encoded, updated, source["source_id"]))
            else:
                connection.execute("INSERT INTO knowledge_sources(source_id,payload_json,updated_at) VALUES (?,?,?)", (source["source_id"], encoded, updated))

    def list_sources(self):
        with self.service.store._lock:
            rows = self.service.store._connection.execute("SELECT payload_json FROM knowledge_sources ORDER BY source_id").fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def set_enabled(self, source_id: str, enabled: bool):
        if type(enabled) is not bool:
            raise ValueError("enabled must be boolean")
        source = next((item for item in self.list_sources() if item["source_id"] == source_id), None)
        if source is None:
            raise ValueError("unknown source")
        self._save_source({**source, "enabled": enabled})
        return {"source_id": source_id, "enabled": enabled}

    def configure_source(self, source_id: str, config: KnowledgeSourceInput):
        import re
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", source_id):
            raise ValueError("invalid source identity")
        source = next((item for item in self.list_sources() if item["source_id"] == source_id), None)
        record = {**config.model_dump(), "source_id": source_id, "last_run_at": None,
                  "last_status": "NOT_RUN", "last_error": None, "next_start": 0}
        if source and source["url"] == config.url and source["format"] == config.format:
            record.update({key: value for key, value in source.items() if key.startswith("last_") or key == "next_start"})
        self._save_source(record)
        return record

    async def _offload_ingest(self, function, *args, **kwargs):
        task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # Cancellation must wait for a synchronous write already underway;
            # otherwise the store could close while its worker still uses it.
            with suppress(Exception):
                await task
            raise

    async def _ingest_item(self, owner_id, source, item):
        metadata = {"title": item["title"], "source": source["title"], "source_url": item["source_url"],
                    "canonical_source": item["source_url"], "published_at": item["published_at"],
                    "visibility": "PUBLIC", "kind": source.get("kind", "OTHER")}
        if item.get("pdf_url"):
            try:
                body, _, _ = await self.fetcher.fetch(item["pdf_url"])
                return await self._offload_ingest(self.service.upload, owner_id, "paper.pdf", body, metadata, admin=True)
            except (CrawlRefused, ValueError):
                # A fetched abstract remains explicitly an abstract, never a
                # silent substitute for the unavailable full paper.
                metadata["title"] = metadata["title"][:480] + " [摘要]"
        if not item.get("text"):
            raise CrawlRefused("SOURCE_TEXT_UNAVAILABLE")
        return await self._offload_ingest(self.service.ingest, owner_id, KnowledgeDocumentInput(**metadata, text=item["text"]), admin=True)

    async def run_once(self, owner_id="research-crawler"):
        if self._run_lock.locked():
            return {"status": "ALREADY_RUNNING", "sources": []}
        async with self._run_lock:
            results = []
            for source in self.list_sources():
                if not source.get("enabled"):
                    continue
                last = source.get("last_run_at")
                if last and source.get("last_status") == "CALCULATED":
                    age = (datetime.fromisoformat(_timestamp(self.service.clock())) - datetime.fromisoformat(last)).total_seconds()
                    if age < DEFAULT_INTERVAL_SECONDS:
                        results.append({"source_id": source["source_id"], "status": "CACHED", "ingested": 0, "failed": 0,
                                        "reason": "SOURCE_24H_CACHE", "coverage": source.get("coverage")})
                        continue
                ingested, failed, reason = 0, 0, None
                coverage = None
                try:
                    async with asyncio.timeout(120):
                        fetch_url = source["url"]
                        parsed_url = urlsplit(fetch_url)
                        arxiv_api = parsed_url.hostname in {"export.arxiv.org", "arxiv.org"} and parsed_url.path == "/api/query"
                        if arxiv_api:
                            params = dict(parse_qsl(parsed_url.query))
                            params.update({"start": str(source.get("next_start", 0)), "max_results": str(source.get("page_size", MAX_FEED_ITEMS))})
                            fetch_url = urlunsplit((parsed_url.scheme, parsed_url.netloc, parsed_url.path, urlencode(params), ""))
                        body, media_type, source_url = await self.fetcher.fetch(fetch_url)
                        if source["format"] in {"RSS", "ATOM"}:
                            page_size = source.get("page_size", MAX_FEED_ITEMS)
                            items = parse_feed(body, limit=page_size)
                            if not items:
                                raise CrawlRefused("NO_DATED_FEED_ITEMS")
                            feed_root = ET.fromstring(body)
                            entry_count = len(feed_root.findall("{http://www.w3.org/2005/Atom}entry") or feed_root.findall("./channel/item"))
                            total_text = feed_root.findtext("{http://a9.com/-/spec/opensearch/1.1/}totalResults")
                            total = int(total_text) if total_text and total_text.isdigit() else entry_count
                            offset = source.get("next_start", 0) if arxiv_api else 0
                            has_more = offset + entry_count < total if arxiv_api else entry_count > page_size
                            coverage = {"scope": "BOUNDED_FEED_NOT_FULL_ARCHIVE", "start": offset, "page_size": page_size,
                                        "entry_count": entry_count, "dated_items": len(items), "total_results": total,
                                        "has_more": has_more}
                            if arxiv_api:
                                source["next_start"] = offset + entry_count if has_more else 0
                        elif source["format"] == "HTML":
                            article = extract_article_html(body)
                            items = [{**article, "source_url": source_url, "published_at": _feed_time(article["published_at"] or source.get("published_at"))}]
                        elif source["format"] == "PDF":
                            metadata = {"title": source["title"], "source": source["title"], "source_url": source_url,
                                        "canonical_source": source_url, "published_at": _feed_time(source.get("published_at")),
                                        "visibility": "PUBLIC", "kind": source.get("kind", "PAPER")}
                            saved = await self._offload_ingest(self.service.upload, owner_id, "paper.pdf", body, metadata, admin=True)
                            ingested += int(saved["created"])
                            items = []
                        else:
                            raise CrawlRefused("SOURCE_FORMAT_REFUSED")
                        for item in items:
                            try:
                                saved = await self._ingest_item(owner_id, source, item)
                                ingested += int(saved["created"])
                            except (CrawlRefused, ValueError):
                                failed += 1
                except CrawlRefused as exc:
                    reason = exc.code
                except TimeoutError:
                    reason = "SOURCE_DEADLINE"
                except Exception:
                    reason = "SOURCE_INGEST_UNAVAILABLE"
                status = "FAILED" if reason else "PARTIAL" if failed else "CALCULATED"
                self._save_source({**source, "last_run_at": _timestamp(self.service.clock()), "last_status": status,
                                   "last_error": reason, "last_ingested": ingested, "last_failed": failed, "coverage": coverage})
                results.append({"source_id": source["source_id"], "status": status, "ingested": ingested,
                                "failed": failed, "reason": reason, "coverage": coverage})
            return {"status": "DISABLED" if not results else "CALCULATED" if all(item["status"] in {"CALCULATED", "CACHED"} for item in results) else "PARTIAL",
                    "sources": results}

    async def start(self):
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop(), name="prism-knowledge-crawler")

    async def _loop(self):
        try:
            while True:
                try:
                    await self.run_once()
                except Exception:
                    # A transient database/source failure must not silently end
                    # the daily lifecycle. Never persist raw diagnostic payloads.
                    pass
                await asyncio.sleep(self.interval_seconds)
        except asyncio.CancelledError:
            raise

    async def close(self):
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        async with self._run_lock:
            await self.fetcher.close()
