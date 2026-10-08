#!/usr/bin/env python3
import datetime
import html
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
    ("IEEE TQE", "https://ieeexplore.ieee.org/rss/TOC8924785.XML"),
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


def clean_summary(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


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
    collected = []

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

                published = getattr(item, "published_parsed", None) or getattr(
                    item, "updated_parsed", None
                )
                if published:
                    published_date = datetime.datetime(
                        *published[:6], tzinfo=datetime.timezone.utc
                    )
                else:
                    published_date = datetime.datetime.now(
                        datetime.timezone.utc
                    )
                entry.pubDate(published_date)

                collected.append(
                    {
                        "source": source_name,
                        "title": title,
                        "link": link,
                        "summary": clean_summary(summary),
                        "published": published_date,
                    }
                )

    fg.rss_file(xml_path, pretty=True)

    by_source = {name: [] for name, _ in FEEDS}
    for entry_item in collected:
        by_source[entry_item["source"]].append(entry_item)

    sections = []
    for source_name, _ in FEEDS:
        items = by_source[source_name]
        if not items:
            continue
        items.sort(
            key=lambda e: e["published"]
            or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc),
            reverse=True,
        )
        rows = []
        for item in items:
            date_str = item["published"].strftime("%Y-%m-%d")
            snippet = item["summary"]
            if len(snippet) > 280:
                snippet = snippet[:280].rstrip() + "\u2026"
            summary_html = (
                f'\n        <p class="summary">{html.escape(snippet)}</p>'
                if snippet
                else ""
            )
            rows.append(
                "      <li>\n"
                f'        <a href="{html.escape(item["link"], quote=True)}">'
                f'{html.escape(item["title"])}</a>'
                f'\n        <span class="date">{date_str}</span>'
                f"{summary_html}\n"
                "      </li>"
            )
        sections.append(
            f'  <section>\n    <h3>{html.escape(source_name)} '
            f'<span class="count">{len(items)}</span></h3>\n'
            "    <ul>\n" + "\n".join(rows) + "\n    </ul>\n  </section>"
        )

    sections_html = "\n".join(sections)
    last_updated = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Quantum Systems Feed</title>
  <style>
    :root {{ color-scheme: light dark; }}
    body {{ font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
           max-width: 760px; margin: 0 auto; padding: 32px 20px; line-height: 1.55; }}
    h2 {{ margin-bottom: 4px; }}
    .sub {{ margin-top: 0; opacity: 0.75; }}
    section {{ margin-top: 28px; }}
    h3 {{ margin-bottom: 8px; border-bottom: 1px solid currentColor;
         padding-bottom: 4px; }}
    h3 .count {{ font-weight: normal; opacity: 0.6; font-size: 0.9em; }}
    ul {{ list-style: none; padding: 0; margin: 0; }}
    li {{ padding: 10px 0; border-bottom: 1px solid rgba(128, 128, 128, 0.2); }}
    li a {{ font-weight: 600; text-decoration: none; }}
    li a:hover {{ text-decoration: underline; }}
    .date {{ font-size: 0.82em; opacity: 0.65; margin-left: 6px; }}
    .summary {{ margin: 4px 0 0; font-size: 0.9em; opacity: 0.85; }}
    footer {{ margin-top: 36px; font-size: 0.85em; opacity: 0.7; }}
  </style>
</head>
<body>
  <h2>Quantum Systems, Compilation &amp; Theory Feed</h2>
  <p class="sub">Aggregating PRX Quantum, Quantum, npj QI, ACM TQC, and IEEE TQE.</p>
  <p>Subscribe via RSS: <a href="feed.xml"><code>feed.xml</code></a></p>
{sections_html}
  <footer>Last updated: {last_updated} ({entries_count} entries)</footer>
</body>
</html>
"""

    with open(html_path, "w", encoding="utf-8") as html_file:
        html_file.write(page)

    print(f"Generated {xml_path} with {entries_count} entries.")


if __name__ == "__main__":
    build_feed()
