from __future__ import annotations

import json
import re
from collections import deque
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from vector_store import VectorStore


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        stripped = data.strip()
        if stripped:
            self._chunks.append(stripped)

    def get_text(self) -> str:
        return " ".join(self._chunks)


def _chunk_text(text: str, words_per_chunk: int = 120) -> Iterable[str]:
    words = text.split()
    if not words:
        return []
    chunk: list[str] = []
    for word in words:
        chunk.append(word)
        if len(chunk) >= words_per_chunk:
            yield " ".join(chunk)
            chunk = []
    if chunk:
        yield " ".join(chunk)


def _extract_html_text(html: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(html)
    return " ".join(parser.get_text().split())


class _LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.links.append(value)


def _extract_links(html: str) -> list[str]:
    parser = _LinkExtractor()
    parser.feed(html)
    return parser.links


def _pdf_to_text(path: Path) -> str:
    raw = path.read_bytes()
    matches = re.findall(rb"\(([^()]*)\)", raw)
    text = " ".join(match.decode("latin-1", errors="ignore") for match in matches)
    return " ".join(text.split())


def _document_to_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _pdf_to_text(path)
    if suffix in {".txt", ".md", ".markdown"}:
        return " ".join(path.read_text(encoding="utf-8").split())
    return ""


class ContractorIngestor:
    """Handles crawling contractor knowledge sources and indexing into a vector store."""

    def __init__(self, store: VectorStore) -> None:
        self._store = store

    def ingest_site(self, start_url: str, max_depth: int = 1) -> None:
        parsed_origin = urlparse(start_url)
        allowed_netloc = parsed_origin.netloc
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(start_url, 0)])
        while queue:
            url, depth = queue.popleft()
            if url in visited:
                continue
            visited.add(url)
            try:
                request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urlopen(request, timeout=10.0) as response:
                    html_bytes = response.read()
            except Exception:
                continue
            html = html_bytes.decode("utf-8", errors="ignore")
            text = _extract_html_text(html)
            if text:
                for chunk in _chunk_text(text):
                    self._store.add_text(chunk, source="website", metadata={"url": url})
            if depth >= max_depth:
                continue
            for link in _extract_links(html):
                href = urljoin(url, link)
                parsed = urlparse(href)
                if parsed.scheme not in {"http", "https"}:
                    continue
                if parsed.netloc and parsed.netloc != allowed_netloc:
                    continue
                queue.append((href, depth + 1))

    def ingest_local_site(self, root: Path, base_url: str = "https://local.test") -> None:
        root = root.resolve()
        for html_path in root.rglob("*.html"):
            text = _extract_html_text(html_path.read_text(encoding="utf-8"))
            if not text:
                continue
            rel = html_path.relative_to(root)
            metadata = {"url": urljoin(base_url + "/", str(rel).replace("\\", "/"))}
            for chunk in _chunk_text(text):
                self._store.add_text(chunk, source="website", metadata=metadata)

    def ingest_documents(self, directory: Path) -> None:
        for path in directory.iterdir():
            if not path.is_file():
                continue
            text = _document_to_text(path)
            if not text:
                continue
            for chunk in _chunk_text(text):
                self._store.add_text(
                    chunk,
                    source="document",
                    metadata={"path": str(path.name)},
                )

    def ingest_faq(self, faq_path: Path) -> None:
        payload = json.loads(faq_path.read_text(encoding="utf-8"))
        for entry in payload:
            question = entry.get("question", "").strip()
            answer = entry.get("answer", "").strip()
            if not question and not answer:
                continue
            joined = f"Q: {question} A: {answer}".strip()
            for chunk in _chunk_text(joined, words_per_chunk=80):
                self._store.add_text(
                    chunk,
                    source="faq",
                    metadata={"question": question[:80]},
                )


def load_sample_corpus(store: VectorStore, samples_dir: Path | None = None) -> None:
    base = samples_dir or Path(__file__).parent / "samples"
    if not base.exists():
        return
    ingestor = ContractorIngestor(store)
    site_dir = base / "website"
    if site_dir.exists():
        ingestor.ingest_local_site(site_dir)
    documents_dir = base / "documents"
    if documents_dir.exists():
        ingestor.ingest_documents(documents_dir)
    faq_path = base / "faq.json"
    if faq_path.exists():
        ingestor.ingest_faq(faq_path)
