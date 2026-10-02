#!/usr/bin/env python3
import datetime
import os
import re

from feedgen.feed import FeedGenerator
import feedparser
import requests

FEEDS = [
    ("PRX Quantum", "https://feeds.aps.org/rss/recent/prxquantum.xml"),
    ("Quantum Journal", "https://quantum-journal.org/feed/"),
    ("npj Quantum Information", "https://www.nature.com/npjqi.rss"),
    ("ACM TQC", "https://dl.acm.org/action/showFeed?type=etoc&feed=rss&jc=tqc"),
    ("IEEE TQE", "https://ieeexplore.ieee.org/rss/TOC8964404.XML"),
]

INCLUDE_PATTERN = re.compile(
    r"\b(compil|synthesis|partition|routing|cutting|distribut|interconnect|e-bit|"
    r"teleport|fault-tolerant|error[- ]correct|qec|qldpc|surface code|lattice surgery|"
    r"stabilizer|magic state|zx[- ]calc|tensor network|algorithm|qft|resource estimation|"
    r"mapping|scheduling|one-shot|channel simulation|interferometry|diagonalization)\b",
    re.IGNORECASE,
)

EXCLUDE_PATTERN = re.compile(
    r"\b(fabricat|cryostat|resonator|superconducting cavity|transmon design|"
    r"dielectric loss|two-level system|majorana|topological insulator|ferromagnet|"
    r"spin-orbit coupling|kagome|hubbard|fractional quantum hall|laser cooling|optomechanic)\b",
    re.IGNORECASE,
)

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )
}


def matches_criteria(title: str, summary: str) -> bool:
    text = f"{title} {summary}"
    if EXCLUDE_PATTERN.search(text):
        return False
    return bool(INCLUDE_PATTERN.search(text))


def build_feed(output_dir: str = "public") -> None:
    os.makedirs(output_dir, exist_ok=True)
    xml_path = os.path.join(output_dir, "feed.xml")
    html_path = os.path.join(output_dir, "index.html")

    repo_owner = os.getenv("GITHUB_REPOSITORY_OWNER", "user")
    repo_name = os.getenv("GITHUB_REPOSITORY", "user/repo").split("/")[-1]
    site_url = f"https://{repo_owner}.github.io/{repo_name}/"
    feed_url = f"{site_url}feed.xml"

    fg = FeedGenerator()
    fg.id(site_url)
    fg.title("Quantum Systems, Compilation & Theory (Filtered)")
    fg.description(
        "Automated aggregation of published papers from PRX Quantum, Quantum, "
        "npj QI, ACM TQC, and IEEE TQE."
    )
    fg.link(href=site_url, rel="alternate")
    fg.link(href=feed_url, rel="self")
    fg.language("en")

    seen_links = set()
    entries_count = 0

    for source_name, url in FEEDS:
        try:
            response = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
            if response.status_code != 200:
                print(f"[WARN] HTTP {response.status_code} fetching {source_name}")
                continue
            feed = feedparser.parse(response.content)
        except Exception as exc:
            print(f"[ERROR] Failed fetching {source_name}: {exc}")
            continue

        for item in feed.entries:
            link = getattr(item, "link", "")
            if not link or link in seen_links:
                continue

            title = getattr(item, "title", "Untitled")
            summary = getattr(item, "summary", "")

            if matches_criteria(title, summary):
                seen_links.add(link)
                entries_count += 1
                entry = fg.add_entry()
                entry.id(link)
                entry.title(f"[{source_name}] {title}")
                entry.link(href=link)
                entry.description(summary)

                published = getattr(item, "published_parsed", None)
                if published:
                    published_date = datetime.datetime(
                        *published[:6], tzinfo=datetime.timezone.utc
                    )
                    entry.pubDate(published_date)
                else:
                    entry.pubDate(datetime.datetime.now(datetime.timezone.utc))

    fg.rss_file(xml_path, pretty=True)

    with open(html_path, "w", encoding="utf-8") as html_file:
        html_file.write(
            f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Quantum Systems Feed</title>
</head>
<body style="font-family: sans-serif; max-width: 650px; margin: 40px auto; line-height: 1.6;">
  <h2>Quantum Systems, Compilation &amp; Theory Feed</h2>
  <p>Aggregating PRX Quantum, Quantum, npj QI, ACM TQC, and IEEE TQE.</p>
  <p>Subscribe via RSS: <a href="feed.xml"><code>feed.xml</code></a></p>
  <p><em>Last updated: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} ({entries_count} entries)</em></p>
</body>
</html>"""
        )

    print(f"Generated {xml_path} with {entries_count} entries.")


if __name__ == "__main__":
    build_feed()
