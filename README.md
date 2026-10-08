# Quantum Feed

This repository aggregates papers matching quantum systems, compilation, and theory keywords from PRX Quantum, Quantum, npj Quantum Information, ACM TQC, and IEEE TQE.

## Local usage

Install the dependencies and generate the static site:

```bash
python -m pip install -r requirements.txt
python scripts/aggregate.py
```

The generated RSS feed is written to `public/feed.xml`, with a landing page at `public/index.html` that lists the matched papers grouped by source.

## GitHub Pages

The workflow in `.github/workflows/update_feed.yml` generates and deploys the feed on pushes to `main`, daily at 06:00 UTC, or manually from the Actions tab.

In repository settings, set **Pages > Build and deployment > Source** to **GitHub Actions**. Once deployed, the feed will be available at:

```text
https://<username>.github.io/<repository-name>/feed.xml
```