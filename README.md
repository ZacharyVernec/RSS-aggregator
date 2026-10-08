# Quantum Feed

This repository aggregates papers matching quantum systems, compilation, and theory keywords from PRX Quantum, Quantum, npj Quantum Information, ACM TQC, and IEEE TQE.

## Local usage

Requires [uv](https://docs.astral.sh/uv/). Install the dependencies and generate the static site:

```bash
uv sync
uv run python scripts/aggregate.py
```

The generated RSS feed is written to `public/feed.xml`, with a landing page at `public/index.html` that lists the matched papers grouped by source.

## Feedback

The landing page lets you vote up or down on each paper and hide ones you don't want to see. Feedback is saved
immediately to the browser's `localStorage` and, once a token is configured, committed to
[`feedback.json`](feedback.json) so the generator and future models can use it:

- **Up / Down** — records a preference for the paper.
- **Hide** — moves the paper out of its source list into a collapsed **Hidden** section. It stays
  in `feed.xml` and can be restored from that section at any time.
- **Expand all / Collapse all** — opens or closes every source section.

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

Hidden papers are omitted from `index.html` but remain in `feed.xml`.

## GitHub Pages

The workflow in `.github/workflows/update_feed.yml` generates and deploys the feed on pushes to `main`, daily at 06:00 UTC, or manually from the Actions tab.

In repository settings, set **Pages > Build and deployment > Source** to **GitHub Actions**. Once deployed, the feed will be available at:

```text
https://<username>.github.io/<repository-name>/feed.xml
```