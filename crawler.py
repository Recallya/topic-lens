"""Bounded RSS/HTML crawler with robots.txt and publication-date extraction."""
import ipaddress
import json
import socket
import time
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup
from analytics import matches_topic, parse_date

USER_AGENT = "TopicLensBot/1.0"
SOURCES = {
    "antara": {"label": "ANTARA · Indonesia", "url": "https://www.antaranews.com/rss/terkini.xml"},
    "bbc": {"label": "BBC · Dunia", "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
}
TRUSTED_FEED_HOSTS = {urlsplit(source["url"]).hostname for source in SOURCES.values()}


def validate_url(url, resolve=True):
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        raise ValueError("Gunakan URL http/https publik tanpa kredensial.")
    if parts.port not in (None, 80, 443):
        raise ValueError("Hanya port web 80 dan 443 yang didukung.")
    if resolve:
        try:
            addresses = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80))
        except socket.gaierror:
            # Some managed environments resolve public destinations only at the proxy.
            # Permit only our fixed public feed hosts in this case; custom hosts fail closed.
            if parts.hostname in TRUSTED_FEED_HOSTS and requests.utils.get_environ_proxies(url):
                return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", parts.query, ""))
            raise ValueError("DNS sumber tidak dapat diakses. Periksa koneksi internet/DNS perangkat.")
        if not addresses or any(not ipaddress.ip_address(info[4][0]).is_global for info in addresses):
            raise ValueError("Alamat lokal atau jaringan privat tidak dapat di-crawl.")
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", parts.query, ""))


def plain(value):
    return BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True)


def parse_feed(content, base):
    root = ET.fromstring(content)
    results = []
    for item in root.iter():
        if item.tag.split("}")[-1] not in ("item", "entry"):
            continue
        fields = {}
        for child in item:
            key = child.tag.split("}")[-1]
            if key == "link" and child.attrib.get("rel", "alternate") != "alternate":
                continue
            fields[key] = child.attrib.get("href") if key == "link" and child.attrib.get("href") else "".join(child.itertext())
        link = fields.get("link", "").strip()
        if not link:
            continue
        date, precision = parse_date(fields.get("pubDate") or fields.get("published") or fields.get("date"))
        results.append({"url": urljoin(base, link), "title": plain(fields.get("title", "Tanpa judul")),
                        "text": plain(fields.get("encoded") or fields.get("content") or fields.get("description") or fields.get("summary")),
                        "published_at": date, "date_precision": precision, "source": urlsplit(base).hostname})
    return results


def parse_html(content, url):
    soup = BeautifulSoup(content, "html.parser")
    title = soup.find("h1") or soup.find("title")
    title_text = title.get_text(" ", strip=True) if title else "Tanpa judul"
    raw_date = None
    for attrs in ({"property": "article:published_time"}, {"name": "datePublished"}, {"itemprop": "datePublished"}):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            raw_date = tag["content"]
            break

    def find_published(value):
        if isinstance(value, dict):
            if value.get("datePublished"):
                return value["datePublished"]
            for item in value.values():
                found = find_published(item)
                if found:
                    return found
        elif isinstance(value, list):
            for item in value:
                found = find_published(item)
                if found:
                    return found
        return None

    if not raw_date:
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                raw_date = find_published(json.loads(script.string or "{}"))
            except (ValueError, RecursionError):
                continue
            if raw_date:
                break
    if not raw_date:
        tag = soup.find("time", datetime=True)
        raw_date = tag.get("datetime") if tag else None
    date, precision = parse_date(raw_date)
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    body = soup.find("article") or soup.find("main") or soup.body or soup
    text = " ".join(p.get_text(" ", strip=True) for p in body.find_all("p"))[:40000]
    return {"url": url, "title": title_text, "text": text, "source": urlsplit(url).hostname,
            "published_at": date, "date_precision": precision}


class Crawler:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.robots, self.last_fetch, self.delays, self.robot_errors = {}, {}, {}, {}

    def fetch(self, url, check_robots=True):
        for _ in range(5):
            url = validate_url(url)
            parts = urlsplit(url)
            origin = f"{parts.scheme}://{parts.netloc}"
            if check_robots and not self.allowed(url):
                reason = self.robot_errors.get(origin, "robots.txt tidak mengizinkan URL ini")
                raise ValueError("Sumber dilewati: " + reason + ".")
            delay = max(0, self.delays.get(origin, 1.0) - (time.monotonic() - self.last_fetch.get(origin, 0)))
            if delay:
                time.sleep(delay)
            self.last_fetch[origin] = time.monotonic()
            with self.session.get(url, timeout=(5, 12), allow_redirects=False, stream=True) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    url = urljoin(url, response.headers.get("Location", ""))
                    continue
                response.raise_for_status()
                chunks, size = [], 0
                for chunk in response.iter_content(16384):
                    size += len(chunk)
                    if size > 2_000_000:
                        raise ValueError("Halaman melebihi batas 2 MB.")
                    chunks.append(chunk)
                return b"".join(chunks), url, response.headers.get("Content-Type", "")
        raise ValueError("Terlalu banyak pengalihan URL.")

    def allowed(self, url):
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self.robots:
            parser = RobotFileParser()
            try:
                body, _, _ = self.fetch(origin + "/robots.txt", check_robots=False)
                parser.parse(body.decode("utf-8", errors="replace").splitlines())
            except requests.HTTPError as error:
                parser.parse([] if error.response.status_code in (404, 410) else ["User-agent: *", "Disallow: /"])
                self.robot_errors[origin] = f"robots.txt merespons HTTP {error.response.status_code}"
            except (requests.RequestException, ValueError, OSError) as error:
                parser.parse(["User-agent: *", "Disallow: /"])
                self.robot_errors[origin] = f"robots.txt tidak dapat diakses ({type(error).__name__}); periksa jaringan/proxy"
            self.robots[origin] = parser
            self.delays[origin] = max(1, parser.crawl_delay(USER_AGENT) or parser.crawl_delay("*") or 1)
        return self.robots[origin].can_fetch(USER_AGENT, url)

    def crawl(self, urls, topic, limit, progress):
        results, warnings, seen = [], [], set()
        checked = 0
        for source_url in urls:
            if checked >= limit:
                break
            try:
                source_checked = 0
                source_limit = max(1, limit // len(urls))
                progress(f"Membaca sumber {urlsplit(source_url).hostname}…")
                body, final_url, content_type = self.fetch(source_url)
                try:
                    candidates = parse_feed(body, final_url)
                    is_feed = bool(candidates) or "xml" in content_type
                except ET.ParseError:
                    candidates, is_feed = [], False
                if not is_feed:
                    candidates = [parse_html(body, final_url)]
                    soup = BeautifulSoup(body, "html.parser")
                    for anchor in soup.select("a[href]"):
                        link = urljoin(final_url, anchor["href"])
                        if urlsplit(link).hostname == urlsplit(final_url).hostname and urlsplit(link).scheme in ("https", "http"):
                            candidates.append({"url": link})
                for candidate in candidates:
                    if checked >= limit or source_checked >= source_limit:
                        break
                    link = validate_url(candidate["url"], resolve=False)
                    if link in seen:
                        continue
                    seen.add(link)
                    checked += 1
                    source_checked += 1
                    progress(f"Memeriksa {checked}/{limit} · {urlsplit(link).hostname}")
                    if "title" not in candidate:
                        try:
                            page, page_url, mime = self.fetch(link)
                            if "html" not in mime:
                                continue
                            candidate = parse_html(page, page_url)
                        except (requests.RequestException, ValueError, OSError) as error:
                            warnings.append(f"{urlsplit(link).hostname}: {type(error).__name__}")
                            continue
                    if matches_topic(topic, candidate["title"] + " " + candidate["text"]):
                        candidate["url"] = link
                        results.append(candidate)
            except (requests.RequestException, ValueError, OSError) as error:
                warnings.append(f"{urlsplit(source_url).hostname}: {str(error)[:180]}")
        self.session.close()
        return results, warnings, checked
