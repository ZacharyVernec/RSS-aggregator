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

CATEGORIES = [
    {
        "id": "journals",
        "title": "Journals",
        "description": "Peer-reviewed papers from PRX Quantum, Quantum, npj QI, Quantum Science and Technology, ACM TQC, and IEEE TQE.",
        "feeds": [
            ("PRX Quantum", "https://feeds.aps.org/rss/recent/prxquantum.xml"),
            ("Quantum Journal", "https://quantum-journal.org/feed/"),
            ("npj Quantum Information", "https://www.nature.com/npjqi.rss"),
            ("Quantum Science and Technology", "https://iopscience.iop.org/journal/rss/2058-9565"),
            ("ACM TQC", "https://dl.acm.org/action/showFeed?type=etoc&feed=rss&jc=tqc"),
            ("IEEE TQE", "https://ieeexplore.ieee.org/rss/TOC8924785.XML"),
        ],
    },
    {
        "id": "arxiv",
        "title": "arXiv",
        "description": "Preprints matching quantum systems, compilation, and theory keywords from arXiv quant-ph.",
        "feeds": [
            ("arXiv quant-ph", "https://rss.arxiv.org/rss/quant-ph"),
        ],
    },
    {
        "id": "industry",
        "title": "Industry & Whitepapers",
        "description": "Technical engineering blogs, benchmarks, and architecture whitepapers from quantum industry leaders.",
        "feeds": [
            ("AWS Quantum Blog", "https://aws.amazon.com/blogs/quantum-computing/feed/"),
            ("Microsoft Quantum Blog", "https://devblogs.microsoft.com/qsharp/feed/"),
            ("Qiskit Blog", "https://medium.com/feed/qiskit"),
            ("Google Research", "https://research.google/blog/rss/"),
            ("IBM Research", "https://research.ibm.com/rss"),
        ],
    },
    {
        "id": "blogs",
        "title": "Academic Blogs",
        "description": "Personal research blogs, essays, and notes from quantum computing, QEC, and theoretical computer science academics (exempt from keyword filters).",
        "exempt_from_filters": True,
        "feeds": [
            ("Scott Aaronson (Shtetl-Optimized)", "https://scottaaronson.blog/?feed=rss2"),
            ("Craig Gidney (Algorithmic Assertions)", "https://algassert.com/feed.xml"),
            ("Quantum Frontiers (IQIM Caltech)", "https://quantumfrontiers.com/feed/"),
            ("Earl Campbell (Quantum Wizardry)", "https://earltcampbell.com/feed/"),
            ("Thomas Vidick (MyCQstate)", "https://mycqstate.wordpress.com/feed/"),
            ("Dave Bacon (The Quantum Pontiff)", "https://dabacon.org/pontiff/feed/"),
            ("Gil Kalai (Combinatorics and more)", "https://gilkalai.wordpress.com/feed/"),
            ("Matt Leifer", "https://mattleifer.info/feed/"),
            ("Vivien Londe", "https://vivienlonde.github.io/feed.xml"),
            ("Windows on Theory", "https://windowsontheory.org/feed/"),
            (
                "Computational Complexity",
                "https://blog.computationalcomplexity.org/feeds/posts/default?alt=rss",
            ),
            ("Gödel's Lost Letter", "https://rjlipton.com/feed/"),
            ("QuTech", "https://qutech.nl/feed/"),
        ],
    },
]

FEEDS = [feed for cat in CATEGORIES for feed in cat["feeds"]]

INCLUDE_PATTERN = re.compile(
    r"\b(compil|transpil|synthesis|partition|routing|cutting|distribut|interconnect|e-bit|"
    r"teleport|fault-tolerant|error[- ]correct|qec|qldpc|surface code|lattice surgery|"
    r"stabilizer|magic state|zx[- ]calc|tensor network|algorithm|qft|resource estimation|"
    r"mapping|scheduling|schedulers?|one-shot|channel simulation|interferometry|diagonalization|"
    r"logical qubit|syndrome|decod|circuit optimization|qir|openqasm|pulse[- ]level|"
    r"block[- ]encoding|benchmarking)\b",
    re.IGNORECASE,
)

EXCLUDE_PATTERN = re.compile(
    r"\b(fabricat|cryostat|resonator|superconducting cavity|transmon design|"
    r"dielectric loss|two-level system|majorana|topological insulator|ferromagnet|"
    r"spin-orbit coupling|kagome|hubbard|fractional quantum hall|laser cooling|optomechanic|"
    r"funding round|series [a-d]|financial results|quarterly results|webinar|"
    r"appointed|appoints|sponsorship)\b",
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
           max-width: 860px; margin: 0 auto; padding: 28px 18px 60px; line-height: 1.55; }
    h1 { font-size: 1.5rem; margin: 0 0 4px; }
    .sub { margin: 0 0 6px; opacity: .75; }
    a { color: inherit; }
    .rss-links { font-size: .92em; margin: 4px 0 14px; opacity: .88; }
    .rss-links code { font-size: .9em; }
    .topbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
              justify-content: space-between; margin: 14px 0 4px; }
    .status { font-size: .82em; opacity: .72; }
    .buttons { display: flex; gap: 6px; flex-wrap: wrap; }
    button { font: inherit; cursor: pointer; border-radius: 6px; padding: 1px 7px;
             border: 1px solid rgba(128,128,128,.45); background: transparent;
             color: inherit; line-height: 1.2; }
    button:hover { background: rgba(128,128,128,.15); }
    button.on { background: rgba(64,160,255,.22); border-color: rgba(64,160,255,.85); }

    .tab-nav { display: flex; gap: 6px; margin: 22px 0 16px; border-bottom: 1px solid rgba(128,128,128,.3);
               padding-bottom: 0; overflow-x: auto; }
    .tab-btn { appearance: none; border: none; background: transparent; font: inherit;
               font-weight: 500; color: inherit; padding: 8px 14px; cursor: pointer;
               border-radius: 6px 6px 0 0; border-bottom: 2px solid transparent;
               margin-bottom: -1px; opacity: .75; display: inline-flex; align-items: center;
               gap: 8px; white-space: nowrap; transition: all .15s ease; }
    .tab-btn:hover { opacity: 1; background: rgba(128,128,128,.1); }
    .tab-btn.active { opacity: 1; font-weight: 600; border-bottom-color: #2563eb; color: #2563eb; }
    @media (prefers-color-scheme: dark) {
      .tab-btn.active { border-bottom-color: #60a5fa; color: #60a5fa; }
    }
    .badge { font-size: .8em; padding: 1px 7px; border-radius: 10px;
             background: rgba(128,128,128,.2); font-weight: 500; color: inherit; }
    .tab-btn.active .badge { background: rgba(37,99,235,.2); }
    @media (prefers-color-scheme: dark) {
      .tab-btn.active .badge { background: rgba(96,165,250,.25); }
    }
    .tab-panel[hidden] { display: none !important; }
    .tab-desc { font-size: .88em; opacity: .75; margin: 6px 0 14px; font-style: italic; }
    .empty-state { padding: 24px 0; opacity: .6; font-size: .95em; text-align: center; }

    details.source { margin-top: 18px; }
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
  <p class="sub">Aggregating peer-reviewed journals, arXiv preprints, industry whitepapers, and academic personal blogs.</p>
  <p class="rss-links">Subscribe via RSS:
    <a href="feed.xml"><strong>All Feeds</strong> (<code>feed.xml</code>)</a> &middot;
    <a href="feed-journals.xml"><code>Journals</code></a> &middot;
    <a href="feed-arxiv.xml"><code>arXiv</code></a> &middot;
    <a href="feed-industry.xml"><code>Industry</code></a> &middot;
    <a href="feed-blogs.xml"><code>Academic Blogs</code></a>
  </p>

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

  <nav class="tab-nav" role="tablist" aria-label="Venue Categories">
    <button class="tab-btn active" role="tab" id="tab-btn-journals" aria-controls="tab-panel-journals" aria-selected="true" data-tab="journals">
      Journals <span class="badge" id="badge-journals">0</span>
    </button>
    <button class="tab-btn" role="tab" id="tab-btn-arxiv" aria-controls="tab-panel-arxiv" aria-selected="false" data-tab="arxiv">
      arXiv <span class="badge" id="badge-arxiv">0</span>
    </button>
    <button class="tab-btn" role="tab" id="tab-btn-industry" aria-controls="tab-panel-industry" aria-selected="false" data-tab="industry">
      Industry &amp; Whitepapers <span class="badge" id="badge-industry">0</span>
    </button>
    <button class="tab-btn" role="tab" id="tab-btn-blogs" aria-controls="tab-panel-blogs" aria-selected="false" data-tab="blogs">
      Academic Blogs <span class="badge" id="badge-blogs">0</span>
    </button>
  </nav>

  <div class="tab-panels">
__PANELS__
  </div>

  <details class="source hidden-source" id="hidden-source" style="display:none">
    <summary><span class="src">Hidden</span> <span class="count">__HIDDEN__</span></summary>
    <ul class="entries" data-source="__hidden__" id="hidden-list">
__HIDDEN_ROWS__
    </ul>
  </details>

  <footer>Last updated: __LAST_UPDATED__ (__ENTRIES__ entries &middot; <span id="hidden-count-footer">__HIDDEN__</span> hidden)</footer>

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

    var catCounts = {};
    document.querySelectorAll(".tab-btn").forEach(function (btn) {
      var c = btn.getAttribute("data-tab");
      if (c) catCounts[c] = 0;
    });
    document.querySelectorAll("details.source").forEach(function (d) {
      var ul = d.querySelector("ul.entries");
      var count = d.querySelector(".count");
      var n = ul ? ul.querySelectorAll("li.entry").length : 0;
      if (count) count.textContent = n;
      d.style.display = n ? "" : "none";
      if (d.id === "hidden-source") {
        if (!n) d.removeAttribute("open");
      } else {
        var cat = d.getAttribute("data-category");
        if (cat && catCounts.hasOwnProperty(cat)) {
          catCounts[cat] += n;
        }
      }
    });

    for (var cat in catCounts) {
      var badge = document.getElementById("badge-" + cat);
      if (badge) badge.textContent = catCounts[cat];
    }
    var hiddenN = hiddenList ? hiddenList.querySelectorAll("li.entry").length : 0;
    var footerHidden = document.getElementById("hidden-count-footer");
    if (footerHidden) footerHidden.textContent = hiddenN;
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
    var activePanel = document.querySelector(".tab-panel:not([hidden])") || document;
    activePanel.querySelectorAll("details.source").forEach(function (d) { d.open = true; });
  });
  document.getElementById("collapse-all").addEventListener("click", function () {
    var activePanel = document.querySelector(".tab-panel:not([hidden])") || document;
    activePanel.querySelectorAll("details.source").forEach(function (d) { d.open = false; });
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

  function switchTab(tabId) {
    document.querySelectorAll(".tab-btn").forEach(function (btn) {
      var isCurrent = btn.getAttribute("data-tab") === tabId;
      btn.classList.toggle("active", isCurrent);
      btn.setAttribute("aria-selected", isCurrent ? "true" : "false");
    });
    document.querySelectorAll(".tab-panel").forEach(function (panel) {
      if (panel.id === "tab-panel-" + tabId) {
        panel.removeAttribute("hidden");
      } else {
        panel.setAttribute("hidden", "until-found");
      }
    });
    try { localStorage.setItem("qfeed.tab", tabId); } catch (e) {}
  }

  document.querySelectorAll(".tab-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      switchTab(btn.getAttribute("data-tab"));
    });
  });

  var activeTab = "journals";
  try { activeTab = localStorage.getItem("qfeed.tab") || "journals"; } catch (e) {}
  if (document.getElementById("tab-panel-" + activeTab)) {
    switchTab(activeTab);
  }

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

    # Main combined feed
    fg = FeedGenerator()
    fg.id(site_url)
    fg.title("Quantum Systems, Compilation & Theory (Filtered)")
    fg.description(
        "Automated aggregation of quantum systems, compilation, and theory papers "
        "and technical whitepapers from academic journals, arXiv, and industry leaders."
    )
    fg.link(href=site_url, rel="alternate")
    fg.link(href=feed_url, rel="self")
    fg.language("en")

    # Category-specific feeds
    category_fgs = {}
    for cat in CATEGORIES:
        cid = cat["id"]
        cfg = FeedGenerator()
        cfg.id(f"{site_url}#{cid}")
        title_suffix = " (Unfiltered)" if cat.get("exempt_from_filters") else " (Filtered)"
        cfg.title(f"Quantum Systems: {cat['title']}{title_suffix}")
        cfg.description(cat["description"])
        cfg.link(href=site_url, rel="alternate")
        cfg.link(href=f"{site_url}feed-{cid}.xml", rel="self")
        cfg.language("en")
        category_fgs[cid] = cfg

    seen_links = set()
    entries_count = 0
    collected = []

    for cat in CATEGORIES:
        cid = cat["id"]
        is_exempt = cat.get("exempt_from_filters", False)
        for source_name, url in cat["feeds"]:
            try:
                response = requests.get(url, headers=REQUEST_HEADERS, timeout=20)
                if response.status_code != 200:
                    print(f"[WARN] HTTP {response.status_code} fetching {source_name}")
                    continue
                feed = feedparser.parse(response.content)
            except Exception as exc:
                print(f"[ERROR] Failed fetching {source_name}: {exc}")
                continue

            added_for_source = 0
            for item in feed.entries:
                if is_exempt and added_for_source >= 20:
                    break
                link = getattr(item, "link", "")
                if not link or link in seen_links:
                    continue

                title = getattr(item, "title", "Untitled") or "Untitled"
                summary = getattr(item, "summary", "")
                if not summary and hasattr(item, "content") and item.content:
                    try:
                        summary = item.content[0].value
                    except (IndexError, AttributeError):
                        summary = ""
                if not summary:
                    summary = getattr(item, "description", "")

                if is_exempt or matches_criteria(title, summary):
                    seen_links.add(link)
                    entries_count += 1
                    added_for_source += 1

                    published = getattr(item, "published_parsed", None) or getattr(
                        item, "updated_parsed", None
                    )
                    if published:
                        try:
                            published_date = datetime.datetime(
                                *published[:6], tzinfo=datetime.timezone.utc
                            )
                        except Exception:
                            published_date = datetime.datetime.now(
                                datetime.timezone.utc
                            )
                    else:
                        published_date = datetime.datetime.now(
                            datetime.timezone.utc
                        )

                    entry = fg.add_entry()
                    entry.id(link)
                    entry.title(f"[{source_name}] {title}")
                    entry.link(href=link)
                    entry.description(summary)
                    entry.pubDate(published_date)

                    cat_entry = category_fgs[cid].add_entry()
                    cat_entry.id(link)
                    cat_entry.title(f"[{source_name}] {title}")
                    cat_entry.link(href=link)
                    cat_entry.description(summary)
                    cat_entry.pubDate(published_date)

                    collected.append(
                        {
                            "source": source_name,
                            "category": cid,
                            "title": title,
                            "link": link,
                            "summary": clean_summary(summary),
                            "published": published_date,
                        }
                    )

    fg.rss_file(xml_path, pretty=True)
    for cid, cfg in category_fgs.items():
        cfg.rss_file(os.path.join(output_dir, f"feed-{cid}.xml"), pretty=True)

    if os.path.exists(FEEDBACK_FILE):
        shutil.copyfile(FEEDBACK_FILE, os.path.join(output_dir, "feedback.json"))

    by_source = {}
    for cat in CATEGORIES:
        for name, _ in cat["feeds"]:
            by_source[name] = []

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

    panels = []
    hidden_rows = []

    for cat in CATEGORIES:
        cid = cat["id"]
        cat_sections = []
        for source_name, _ in cat["feeds"]:
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
            cat_sections.append(
                f'<details class="source" data-category="{cid}" open>\n'
                f'  <summary><span class="src">{html.escape(source_name)}</span> '
                f'<span class="count">{len(visible_items)}</span></summary>\n'
                f'  <ul class="entries" data-source="{html.escape(source_name, quote=True)}">\n'
                + "\n".join(render_entry(i) for i in visible_items)
                + "\n  </ul>\n</details>"
            )

        empty_text = "No blog posts currently available." if cat.get("exempt_from_filters") else "No matching articles in this category currently."
        cat_body = "\n".join(cat_sections) if cat_sections else f'<p class="empty-state">{empty_text}</p>'
        is_first = (cid == "journals")
        hidden_attr = "" if is_first else " hidden"
        active_cls = " active" if is_first else ""
        panels.append(
            f'<div class="tab-panel{active_cls}" id="tab-panel-{cid}" role="tabpanel" '
            f'aria-labelledby="tab-btn-{cid}"{hidden_attr}>\n'
            f'  <p class="tab-desc">{html.escape(cat["description"])}</p>\n'
            f'  {cat_body}\n'
            f'</div>'
        )

    panels_html = "\n".join(panels)
    hidden_rows_html = "\n".join(hidden_rows)
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
        PAGE_TEMPLATE.replace("__PANELS__", panels_html)
        .replace("__HIDDEN_ROWS__", hidden_rows_html)
        .replace("__FEEDBACK_JSON__", feedback_json)
        .replace("__REPO_JSON__", repo_json)
        .replace("__LAST_UPDATED__", last_updated)
        .replace("__ENTRIES__", str(entries_count))
        .replace("__HIDDEN__", str(len(hidden_rows)))
        .replace("__REPO_LABEL__", f"{repo_owner}/{repo_name}")
    )

    with open(html_path, "w", encoding="utf-8") as html_file:
        html_file.write(page)

    print(f"Generated {xml_path} and {len(category_fgs)} category feeds with {entries_count} total entries.")


if __name__ == "__main__":
    build_feed()
