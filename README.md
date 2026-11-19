# Central Bank Intelligence — Source Atlas

A static, public prototype for the central bank research project. It includes a 29-jurisdiction target map, a searchable directory of publication sources, a dated U.S. Treasury yield backdrop, the analysis workflow, and a local CSV calculator for market observations before and after a speech. See [the research framework](docs/research-framework.md) for the book-guided analytical checks and integration requirements.

## Scope

The directory contains **105 official page links** covering all **29 requested jurisdictions**, including **all 69 entries** on the original Europe Policies & Models worksheet. The daily monitor checks individual RSS/Atom feeds and official dated listings. The public [source coverage page](dist/source-coverage.html) shows which inputs returned dated records and the latest item from each source. Some inputs publish infrequently or return only a short history. The map combines the recent records returned by those checks with the monthly research archive.

The archive contains selected source-based notes for August to November 2026. The source coverage page has separate historical comparisons for August–September and October–19 November. Each lists dated links returned by the checked sources that did not match the archive by URL, related document URL or normalised title and day. The review queue depends on available listing pages, feed history and language editions. Verify feed and meeting dates against the publication before using a record in a market event study.

The supplied `Prompt.docx` defines the sell-side report analysis workflow: a 500–800 word source-only summary, 3–5 ranked further-research questions, chart/table/footnote review, page references and careful attribution to the report's date. Its source-grounded checks also guide speech and central-bank document analysis, with format adapted to each document. It does **not** define a numerical hawkish/dovish scoring rubric. The public site describes this method without embedding the private prompt file or pretending that a static page can analyse complete documents. The team's validated speech model must be integrated before numerical scores or an index are published.

The site displays a dated daily U.S. Treasury par yield curve backdrop (2Y, 10Y and 10Y−2Y), refreshed by the Pages workflow after U.S. business days and on code updates. The official feed supplies daily closing benchmarks, **not real-time or intraday market reaction**. Its observation date and stale-data status appear on the page; a failed fetch retains the previous snapshot. A licensed minute-level feed is still necessary to analyse speech-window reactions automatically. The uploaded reference books are used as analytical lenses and are **not** committed to this public repository.

The market calculator accepts a local CSV with `timestamp_utc,asset,value`. Timestamps must be ISO UTC, for example `2026-11-18T14:00:00Z`. It chooses the closest strictly earlier and strictly later observations within the selected maximum gap, then reports `after − before`. For a yield entered as percentage points, it also shows `100 × change` in basis points. The result is descriptive, not causal. It does not infer an event window automatically, handle simultaneous news, or create an index across speeches. No example values are fabricated. `dist/market-template.csv` contains only the header.

Production work still needs the team's validated model, a speech corpus with reliable release timestamps, versioned scoring and human review, licensed market series at a suitable frequency, and an event-study protocol. Do not commit proprietary model files, API keys or licensed data to this public repository.

## Local preview

Rebuild the archive from the committed research dataset and serve it with a static HTTP server.

```sh
python3 scripts/build-research-archive.py
python3 -m http.server 8000 --directory dist
```

Open `http://localhost:8000`. Opening `index.html` directly as a file will block the JSON fetch in some browsers.

## GitHub Pages

The workflow in `.github/workflows/pages.yml` publishes `dist` on pushes to `main`. In repository **Settings → Pages**, select **GitHub Actions** as the build and deployment source. The site is designed to work from either a project path or a custom domain because asset references are relative.

## Updating sources

Edit `dist/data/sources.json` and `dist/data/coverage.json`. Each source record requires a unique `id`, an HTTPS `url`, and the displayed institution, country, region, category, source type and status. A feed URL is optional. Review publication rights and the accuracy of the page before promoting a proposed entry. Update the snapshot and expansion dates and on-page note when the directory changes.

Add daily machine-readable channels to `scripts/monitored-sources.json`. A listing needs selectors for each dated entry, its title and its official link. Validate the latest dated result with `python3 scripts/update-map-activity.py` after installing `lxml`. The scheduled run rebuilds the monthly archive and refreshes map activity and channel health. Use `--audit aug-sep` or `--audit oct-nov` to rerun a historical review with the dated listings available at the time of the check. `dist/data/archive-periods.json` supplies the archive date ranges and month links.

Update `dist/data/research-archive.json` with verified research records before rebuilding the site. Files in `dist/data/archive-fragments` contain individual research batches. The live site builds from the combined archive dataset.

No external fonts, trackers or runtime services are used. External institution links open in a new tab.
