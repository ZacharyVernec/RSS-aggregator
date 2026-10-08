#!/usr/bin/env python3
import datetime
import html
import json
import os
import re
import shutil
import subprocess

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

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEEDBACK_FILE = os.path.join(REPO_ROOT, "feedback.json")


def detect_repo() -> tuple:
    """Return (owner, repo, branch), preferring GitHub Actions env vars."""
    owner = os.getenv("GITHUB_REPOSITORY_OWNER", "")
    full = os.getenv("GITHUB_REPOSITORY", "")
    branch = os.getenv("GITHUB_REF_NAME", "")
    if owner and full:
        return owner, full.split("/")[-1], branch or "main"
    url = ""
    try:
        url = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=REPO_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        pass
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", url)
    if match:
        return match.group(1), match.group(2), branch or "main"
    fallback = full.split("/")[-1] if full else "repo"
    return owner or "user", fallback, branch or "main"


def load_feedback() -> dict:
    """Load the persisted feedback map (article link -> record) if present."""
    try:
        with open(FEEDBACK_FILE, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[WARN] Could not read {FEEDBACK_FILE}: {exc}")
        return {}
    articles = data.get("articles") if isinstance(data, dict) else None
    return articles if isinstance(articles, dict) else {}


def matches_criteria(title: str, summary: str) -> bool:
    text = f"{title} {summary}"
    if EXCLUDE_PATTERN.search(text):
        return False
    return bool(INCLUDE_PATTERN.search(text))


def clean_summary(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Quantum Systems Feed</title>
  <style>
    :root { color-scheme: light dark; }
    * { box-sizing: border-box; }
    body { font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
           max-width: 840px; margin: 0 auto; padding: 28px 18px 60px; line-height: 1.55; }
    h1 { font-size: 1.5rem; margin: 0 0 4px; }
    .sub { margin: 0 0 6px; opacity: .75; }
    a { color: inherit; }
    .topbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
              justify-content: space-between; margin: 14px 0 4px; }
    .status { font-size: .82em; opacity: .72; }
    .buttons { display: flex; gap: 6px; flex-wrap: wrap; }
    button { font: inherit; cursor: pointer; border-radius: 6px; padding: 1px 7px;
             border: 1px solid rgba(128,128,128,.45); background: transparent;
             color: inherit; line-height: 1.2; }
    button:hover { background: rgba(128,128,128,.15); }
    button.on { background: rgba(64,160,255,.22); border-color: rgba(64,160,255,.85); }
    details.source { margin-top: 20px; }
    details.source > summary { cursor: pointer; list-style: none; display: flex;
        align-items: baseline; gap: 8px; padding: 6px 0; font-weight: 600;
        border-bottom: 1px solid currentColor; }
    details.source > summary::-webkit-details-marker { display: none; }
    details.source > summary::before { content: "▸"; font-size: .85em; opacity: .7; }
    details.source[open] > summary::before { content: "▾"; }
    summary .count { font-weight: 400; opacity: .6; font-size: .9em; }
    ul.entries { list-style: none; padding: 0; margin: 0; }
    li.entry { padding: 12px 0; border-bottom: 1px solid rgba(128,128,128,.2); }
    li.entry .row { display: flex; gap: 10px; align-items: baseline;
                    justify-content: space-between; }
    li.entry .title { font-weight: 600; text-decoration: none; }
    li.entry .title:hover { text-decoration: underline; }
    .date { font-size: .8em; opacity: .65; white-space: nowrap; }
    .summary-text { margin: 4px 0 8px; font-size: .9em; opacity: .85; }
    .actions { display: flex; gap: 5px; }
    .actions button { font-size: .78em; padding: 1px 6px; }
    .settings { margin: 8px 0 0; font-size: .88em; }
    .settings > summary { cursor: pointer; opacity: .8; }
    .field { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; margin-top: 8px; }
    .field input { flex: 1 1 280px; padding: 5px 8px; border-radius: 8px; font: inherit;
                   border: 1px solid rgba(128,128,128,.5); background: transparent;
                   color: inherit; }
    .hint { font-size: .82em; opacity: .72; margin: 8px 0 0; }
    footer { margin-top: 34px; font-size: .85em; opacity: .7; }
  </style>
</head>
<body>
  <h1>Quantum Systems, Compilation &amp; Theory Feed</h1>
  <p class="sub">Aggregating PRX Quantum, Quantum, npj QI, ACM TQC, and IEEE TQE.</p>
  <p>Subscribe via RSS: <a href="feed.xml"><code>feed.xml</code></a></p>

  <div class="topbar">
    <span class="status" id="status">Ready</span>
    <span class="buttons">
      <button id="expand-all" type="button">Expand all</button>
      <button id="collapse-all" type="button">Collapse all</button>
      <button id="sync-now" type="button">Sync now</button>
    </span>
  </div>

  <details class="settings">
    <summary>Feedback sync settings</summary>
    <div class="field">
      <input type="password" id="token"
             placeholder="GitHub fine-grained token (Contents: Read and write)"
             autocomplete="off" spellcheck="false">
      <button id="save-token" type="button">Save</button>
      <button id="clear-token" type="button">Clear</button>
    </div>
    <p class="hint">The token is stored only in this browser (localStorage). Votes and hides
      are written to <code>feedback.json</code> in <code>__REPO_LABEL__</code>, which the
      generator and future models can read.</p>
  </details>

__SECTIONS__

  <footer>Last updated: __LAST_UPDATED__ (__ENTRIES__ entries &middot; __HIDDEN__ hidden)</footer>

<script>window.__FEEDBACK__ = __FEEDBACK_JSON__;
window.__REPO__ = __REPO_JSON__;</script>
<script>
(function () {
  "use strict";
  var REPO = window.__REPO__ || {};
  var TOKEN_KEY = "qfeed.token";
  var STORE_KEY = "qfeed.feedback";
  var state = {};
  var syncTimer = null;

  function merge(a, b) {
    var out = {}, k;
    for (k in a) if (Object.prototype.hasOwnProperty.call(a, k)) out[k] = a[k];
    for (k in b) if (Object.prototype.hasOwnProperty.call(b, k)) {
      var cur = out[k], nw = b[k];
      if (!cur) { out[k] = nw; continue; }
      var t1 = Date.parse(cur.updated_at || 0) || 0;
      var t2 = Date.parse(nw.updated_at || 0) || 0;
      out[k] = t2 >= t1 ? nw : cur;
    }
    return out;
  }
  function load() {
    var inline = (window.__FEEDBACK__ && window.__FEEDBACK__.articles) || {};
    var local = {};
    try { local = JSON.parse(localStorage.getItem(STORE_KEY) || "{}") || {}; } catch (e) {}
    state = merge(inline, local);
  }
  function persist() {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(state)); } catch (e) {}
  }
  function token() {
    try { return localStorage.getItem(TOKEN_KEY) || ""; } catch (e) { return ""; }
  }
  function setStatus(msg) {
    var el = document.getElementById("status");
    if (el) el.textContent = msg;
  }
  function b64(str) {
    var bytes = new TextEncoder().encode(str), bin = "", i;
    for (i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    return btoa(bin);
  }
  function lists() {
    var map = {};
    document.querySelectorAll("ul.entries").forEach(function (ul) {
      if (ul.id !== "hidden-list") map[ul.getAttribute("data-source")] = ul;
    });
    return map;
  }
  function render() {
    var hiddenList = document.getElementById("hidden-list");
    var bySource = lists();
    document.querySelectorAll("li.entry").forEach(function (li) {
      var rec = state[li.getAttribute("data-link")] || {};
      var vote = rec.vote || "";
      var isHidden = !!rec.hidden;
      var up = li.querySelector('[data-action="up"]');
      var down = li.querySelector('[data-action="down"]');
      var hide = li.querySelector('[data-action="hide"]');
      up.classList.toggle("on", vote === "up");
      down.classList.toggle("on", vote === "down");
      up.setAttribute("aria-pressed", vote === "up" ? "true" : "false");
      down.setAttribute("aria-pressed", vote === "down" ? "true" : "false");
      hide.classList.toggle("on", isHidden);
      hide.textContent = isHidden ? "Restore" : "Hide";
      hide.title = isHidden ? "Restore" : "Hide";
      var target = isHidden ? hiddenList : bySource[li.getAttribute("data-source")];
      if (target && li.parentElement !== target) target.appendChild(li);
    });
    document.querySelectorAll("details.source").forEach(function (d) {
      var ul = d.querySelector("ul.entries");
      var count = d.querySelector(".count");
      var n = ul ? ul.querySelectorAll("li.entry").length : 0;
      if (count) count.textContent = n;
      d.style.display = n ? "" : "none";
      if (d.id === "hidden-source" && !n) d.removeAttribute("open");
    });
  }
  function scheduleSync() {
    if (!token()) { setStatus("Saved locally — add a token to sync"); return; }
    setStatus("Saving…");
    clearTimeout(syncTimer);
    syncTimer = setTimeout(sync, 900);
  }
  function fileBody() {
    return JSON.stringify({ version: 1, updated_at: new Date().toISOString(), articles: state }, null, 2);
  }
  function apiUrl() {
    return "https://api.github.com/repos/" + REPO.owner + "/" + REPO.repo + "/contents/feedback.json";
  }
  function getSha(t) {
    return fetch(apiUrl() + "?ref=" + encodeURIComponent(REPO.branch || "main"), {
      headers: { Authorization: "Bearer " + t, Accept: "application/vnd.github+json" },
      cache: "no-store"
    }).then(function (res) {
      if (res.status === 404) return null;
      if (!res.ok) throw new Error("read " + res.status);
      return res.json().then(function (j) { return j.sha; });
    });
  }
  function putFile(t, sha, body) {
    return fetch(apiUrl(), {
      method: "PUT",
      headers: {
        Authorization: "Bearer " + t,
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        message: "Update feed feedback [" + new Date().toISOString() + "]",
        content: b64(body),
        sha: sha,
        branch: REPO.branch || "main"
      })
    });
  }
  function sync() {
    var t = token();
    if (!t) { setStatus("Saved locally — add a token to sync"); return; }
    setStatus("Syncing…");
    var body = fileBody();
    getSha(t).then(function (sha) {
      return putFile(t, sha, body).then(function (res) {
        if (res.status === 409 || res.status === 422) {
          return getSha(t).then(function (latest) { return putFile(t, latest, body); });
        }
        return res;
      });
    }).then(function (res) {
      if (!res.ok) throw new Error(res.status + " " + res.statusText);
      setStatus("Synced " + new Date().toLocaleTimeString());
    }).catch(function (err) {
      setStatus("Sync failed: " + err.message);
    });
  }
  document.addEventListener("click", function (e) {
    var btn = e.target && e.target.closest ? e.target.closest("button.act") : null;
    if (!btn) return;
    var li = btn.closest("li.entry");
    if (!li) return;
    var link = li.getAttribute("data-link");
    var rec = Object.assign({}, state[link] || {});
    var action = btn.getAttribute("data-action");
    if (action === "up") rec.vote = rec.vote === "up" ? "" : "up";
    else if (action === "down") rec.vote = rec.vote === "down" ? "" : "down";
    else if (action === "hide") rec.hidden = !rec.hidden;
    rec.title = li.getAttribute("data-title") || rec.title || "";
    rec.source = li.getAttribute("data-source") || rec.source || "";
    rec.updated_at = new Date().toISOString();
    state[link] = rec;
    persist();
    render();
    scheduleSync();
  });
  document.getElementById("expand-all").addEventListener("click", function () {
    document.querySelectorAll("details.source").forEach(function (d) { d.open = true; });
  });
  document.getElementById("collapse-all").addEventListener("click", function () {
    document.querySelectorAll("details.source").forEach(function (d) { d.open = false; });
  });
  document.getElementById("sync-now").addEventListener("click", sync);
  document.getElementById("save-token").addEventListener("click", function () {
    var v = (document.getElementById("token").value || "").trim();
    if (v) { localStorage.setItem(TOKEN_KEY, v); setStatus("Token saved"); }
    else { localStorage.removeItem(TOKEN_KEY); setStatus("Token cleared"); }
  });
  document.getElementById("clear-token").addEventListener("click", function () {
    localStorage.removeItem(TOKEN_KEY);
    document.getElementById("token").value = "";
    setStatus("Token cleared");
  });

  load();
  if (token()) document.getElementById("token").value = token();
  render();
  setStatus(token() ? "Ready" : "Ready — set a token to sync");
  fetch("feedback.json?ts=" + Date.now(), { cache: "no-store" })
    .then(function (res) { return res.ok ? res.json() : null; })
    .then(function (data) {
      if (data && data.articles) { state = merge(state, data.articles); persist(); render(); }
    })
    .catch(function () {});
})();
</script>
</body>
</html>
"""


def build_feed(output_dir: str = "public") -> None:
    os.makedirs(output_dir, exist_ok=True)
    xml_path = os.path.join(output_dir, "feed.xml")
    html_path = os.path.join(output_dir, "index.html")

    repo_owner, repo_name, branch = detect_repo()
    site_url = f"https://{repo_owner}.github.io/{repo_name}/"
    feed_url = f"{site_url}feed.xml"
    feedback = load_feedback()

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

    if os.path.exists(FEEDBACK_FILE):
        shutil.copyfile(FEEDBACK_FILE, os.path.join(output_dir, "feedback.json"))

    by_source = {name: [] for name, _ in FEEDS}
    for entry_item in collected:
        by_source[entry_item["source"]].append(entry_item)

    def render_entry(item: dict) -> str:
        record = feedback.get(item["link"], {})
        hidden_attr = "true" if record.get("hidden") else "false"
        date_str = item["published"].strftime("%Y-%m-%d")
        snippet = item["summary"]
        if len(snippet) > 280:
            snippet = snippet[:280].rstrip() + "…"
        summary_html = (
            f'<p class="summary-text">{html.escape(snippet)}</p>' if snippet else ""
        )
        safe_link = html.escape(item["link"], quote=True)
        safe_source = html.escape(item["source"], quote=True)
        safe_title = html.escape(item["title"], quote=True)
        return (
            f'    <li class="entry" data-link="{safe_link}" '
            f'data-source="{safe_source}" data-title="{safe_title}" '
            f'data-hidden="{hidden_attr}">'
            '<div class="row">'
            f'<a class="title" href="{safe_link}">{html.escape(item["title"])}</a>'
            f'<span class="date">{date_str}</span>'
            "</div>"
            f"{summary_html}"
            '<div class="actions">'
            '<button class="act" type="button" data-action="up" '
            'aria-pressed="false" title="More like this">Up</button>'
            '<button class="act" type="button" data-action="down" '
            'aria-pressed="false" title="Less like this">Down</button>'
            '<button class="act" type="button" data-action="hide" '
            'aria-pressed="false" title="Hide">Hide</button>'
            "</div>"
            "</li>"
        )

    sections = []
    hidden_rows = []
    for source_name, _ in FEEDS:
        items = by_source[source_name]
        if not items:
            continue
        items.sort(
            key=lambda e: e["published"]
            or datetime.datetime.min.replace(tzinfo=datetime.timezone.utc),
            reverse=True,
        )
        visible_items = [
            i for i in items if not feedback.get(i["link"], {}).get("hidden")
        ]
        hidden_items = [
            i for i in items if feedback.get(i["link"], {}).get("hidden")
        ]
        hidden_rows.extend(render_entry(i) for i in hidden_items)
        sections.append(
            '<details class="source" open>\n'
            f'  <summary><span class="src">{html.escape(source_name)}</span> '
            f'<span class="count">{len(visible_items)}</span></summary>\n'
            f'  <ul class="entries" data-source="{html.escape(source_name, quote=True)}">\n'
            + "\n".join(render_entry(i) for i in visible_items)
            + "\n  </ul>\n</details>"
        )

    sections.append(
        '<details class="source hidden-source" id="hidden-source" '
        'style="display:none">\n'
        '  <summary><span class="src">Hidden</span> '
        f'<span class="count">{len(hidden_rows)}</span></summary>\n'
        '  <ul class="entries" data-source="__hidden__" id="hidden-list">\n'
        + "\n".join(hidden_rows)
        + "\n  </ul>\n</details>"
    )

    sections_html = "\n".join(sections)
    last_updated = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )

    feedback_json = json.dumps(
        {"version": 1, "articles": feedback}, ensure_ascii=False
    ).replace("<", "\\u003c")
    repo_json = json.dumps(
        {"owner": repo_owner, "repo": repo_name, "branch": branch}
    ).replace("<", "\\u003c")

    page = (
        PAGE_TEMPLATE.replace("__SECTIONS__", sections_html)
        .replace("__FEEDBACK_JSON__", feedback_json)
        .replace("__REPO_JSON__", repo_json)
        .replace("__LAST_UPDATED__", last_updated)
        .replace("__ENTRIES__", str(entries_count))
        .replace("__HIDDEN__", str(len(hidden_rows)))
        .replace("__REPO_LABEL__", f"{repo_owner}/{repo_name}")
    )

    with open(html_path, "w", encoding="utf-8") as html_file:
        html_file.write(page)

    print(f"Generated {xml_path} with {entries_count} entries.")


if __name__ == "__main__":
    build_feed()
