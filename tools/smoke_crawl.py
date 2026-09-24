"""Optional live network check. Run from the project root; does not save articles."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from crawler import Crawler, SOURCES
import requests


if __name__ == "__main__":
    for url in ("https://www.antaranews.com/robots.txt", "https://feeds.bbci.co.uk/robots.txt"):
        try:
            response = requests.get(url, timeout=15, headers={"User-Agent": "TopicLensBot/1.0"})
            print({"robots_url": url, "status": response.status_code, "type": response.headers.get("Content-Type"), "rules": response.text[:250]}, flush=True)
        except requests.RequestException as error:
            print({"robots_url": url, "error_type": type(error).__name__}, flush=True)
    rows, warnings, checked = Crawler().crawl(
        [source["url"] for source in SOURCES.values()], "Indonesia", 20,
        lambda message: print(message, flush=True))
    print({"checked": checked, "matched": len(rows), "warnings": warnings})
    for row in rows[:3]:
        print({key: row[key] for key in ("source", "title", "published_at")})
