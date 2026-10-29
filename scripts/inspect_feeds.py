import feedparser
import requests

FEEDS = [
    ("PRX Quantum", "https://feeds.aps.org/rss/recent/prxquantum.xml"),
    ("Quantum Journal", "https://quantum-journal.org/feed/"),
    ("npj Quantum Information", "https://www.nature.com/npjqi.rss"),
    ("IOP Quantum Science and Technology", "https://iopscience.iop.org/journal/rss/2058-9565"),
    ("ACM TQC", "https://dl.acm.org/action/showFeed?type=etoc&feed=rss&jc=tqc"),
    ("IEEE TQE", "https://ieeexplore.ieee.org/rss/TOC8924785.XML"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )
}

for name, url in FEEDS:
    print("=" * 60)
    print(f"FEED: {name} ({url})")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        feed = feedparser.parse(resp.content)
        print(f"Total entries: {len(feed.entries)}")
        if feed.entries:
            e = feed.entries[0]
            print("Keys:", list(e.keys()))
            print("Title:", getattr(e, "title", None))
            print("Authors attr:", getattr(e, "authors", None))
            print("Author attr:", getattr(e, "author", None))
            print("dc:creator:", getattr(e, "dc_creator", None))
            print("creator:", getattr(e, "creator", None))
            print("Summary (first 300 chars):", repr(getattr(e, "summary", ""))[:300])
            if hasattr(e, "content"):
                print("Content:", repr([c.get("value", "")[:200] for c in e.content]))
            
            # Print second entry if exists
            if len(feed.entries) > 1:
                e2 = feed.entries[1]
                print("--- Entry 2 ---")
                print("Title:", getattr(e2, "title", None))
                print("Authors attr:", getattr(e2, "authors", None))
                print("Author attr:", getattr(e2, "author", None))
                print("dc:creator:", getattr(e2, "dc_creator", None))
                print("Summary (first 300 chars):", repr(getattr(e2, "summary", ""))[:300])
    except Exception as exc:
        print(f"Error fetching {name}: {exc}")
