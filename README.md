# Quantum Feed

This repository aggregates papers and whitepapers matching quantum systems, compilation, and theory keywords across peer-reviewed journals, arXiv preprints, and industry technical leaders.

The landing page organizes matched articles into four dedicated tabs:
1. **Journals**: Peer-reviewed publications from PRX Quantum, Quantum, npj Quantum Information, Quantum Science and Technology, ACM TQC, and IEEE TQE.
2. **arXiv**: Preprints from arXiv `quant-ph`.
3. **Industry & Whitepapers**: Technical engineering blogs, benchmarks, and architecture whitepapers from AWS Quantum, Microsoft Quantum, Qiskit, Quandela, Google Research, and IBM Research.
4. **Academic Blogs**: Personal research blogs, essays, and notes from quantum computing, QEC, and theoretical computer science researchers (Scott Aaronson, Craig Gidney, Quantum Frontiers, Earl Campbell, Thomas Vidick, Dave Bacon's *The Quantum Pontiff*, Gil Kalai, Matt Leifer, Vivien Londe, Windows on Theory, Computational Complexity, Gödel's Lost Letter, and QuTech). **Exempt from keyword filters** so personal essays and commentary are preserved in full.

### Sources without an RSS feed
Blogs that publish no feed are still listed on the page via each category's `manual_links` entry, rendered as
"visit directly" links at the top of the tab (currently **Henry Yuen** —
[henryyuen.net/posts](https://www.henryyuen.net/posts)). When a feed appears, move the entry from
`manual_links` into that category's `feeds` list.

## Local usage

Requires [uv](https://docs.astral.sh/uv/). Install the dependencies and generate the static site:

```bash
uv sync
uv run python scripts/aggregate.py
```

The generated feeds and web page are written to `public/`:
- `public/index.html` — Landing page with tabs, live filtering, and interactive feedback
- `public/feed.xml` — Master RSS feed containing all matched articles and blog posts
- `public/feed-journals.xml` — RSS feed for academic journal papers only
- `public/feed-arxiv.xml` — RSS feed for arXiv preprints only
- `public/feed-industry.xml` — RSS feed for industry technical whitepapers and engineering posts only
- `public/feed-blogs.xml` — RSS feed for academic personal blogs only (unfiltered)

## Important Papers & Notable Authors

Important papers are visually distinguished in the web feed with an eye-catching monochrome star (**★**) and larger bold typography (1.15em), making them stand out at a glance while preserving the site's clean aesthetic.

Additionally, the paper entry displays the author line with the star (**★**) placed directly next to the notable author's name (e.g. `★ Dominic W. Berry, Kianna Wan, ..., ★ Ryan Babbush`), so you can immediately see which specific researcher triggered the highlight.

A paper is marked as important if:
1. **Authored by a notable researcher**: It is authored or co-authored by any researcher listed in [`authors.json`](authors.json).
2. **Upvoted by you**: Clicking the **Up** button immediately stars and highlights the paper.

### Filtering Important Papers
Use the **★ Important only** button in the topbar to instantly toggle the view between the full chronological feed and only starred/important papers. Tab badges and section counts dynamically update to reflect the filtered view, and your preference is remembered across sessions.

### Customizing Authors
The tracked researcher list is stored in [`authors.json`](authors.json) at the repository root. You can easily add, remove, or modify names:

```json
[
  "Daniel Gottesman",
  "John Preskill",
  "Craig Gidney",
  "Michael Nielsen",
  "Isaac Chuang",
  "..."
]
```

## Feedback

The landing page lets you vote up or down on each paper and hide ones you don't want to see. Feedback is saved
immediately to the browser's `localStorage` and, once a token is configured, committed to
[`feedback.json`](feedback.json) so the generator and future models can use it:

- **Up / Down** — records a preference for the paper.
- **Hide** — moves the paper out of its source list into a collapsed **Hidden** section across all tabs. It stays
  in `feed.xml` and can be restored from that section at any time.
- **Expand all / Collapse all** — opens or closes source sections within the active tab.

To enable committing, open **Feedback sync settings** on the page and paste a
[fine-grained personal access token](https://github.com/settings/personal-access-tokens/new) scoped
to this repository with **Contents: Read and write**. The token is stored only in that browser's
`localStorage` and is sent only to `api.github.com`. Without a token, feedback is still kept
locally in the browser.

`feedback.json` records one entry per paper link:

```json
{
  "version": 1,
  "updated_at": "2026-10-08T15:00:00.000Z",
  "articles": {
    "https://example.org/paper": {
      "vote": "up",
      "hidden": false,
      "title": "Paper title",
      "source": "PRX Quantum",
      "updated_at": "2026-10-08T15:00:00.000Z"
    }
  }
}
```

Hidden papers are omitted from the main tab lists in `index.html` (moved to the collapsed Hidden section) but remain in `feed.xml`.

## GitHub Pages

The workflow in `.github/workflows/update_feed.yml` generates and deploys the feed on pushes to `main`, daily at 06:00 UTC, or manually from the Actions tab.

In repository settings, set **Pages > Build and deployment > Source** to **GitHub Actions**. Once deployed, the feed will be available at:

```text
https://<username>.github.io/<repository-name>/feed.xml
```
and the category feeds at `feed-journals.xml`, `feed-arxiv.xml`, `feed-industry.xml`, and `feed-blogs.xml`.
