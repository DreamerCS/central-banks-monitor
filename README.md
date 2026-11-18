# Central Bank Intelligence — Source Atlas

A static, public prototype for the central bank research project. It includes a 29-jurisdiction target map, a searchable directory of publication sources, the analysis workflow, and a local CSV calculator for market observations before and after a speech.

## Scope

The directory starts from a **26 October 2026 snapshot** derived from the supplied research register and a prior offline research preview: 69 catalogued European source pages and 15 proposed Americas entries. On 18 November, 21 official links were added, including a link for each of the 18 previously unlisted jurisdictions and speech listings for the Fed, Bank of Canada and Banco de México. All **29 of the requested jurisdictions now have a source entry**. Argentina, Peru and China currently use a general policy, publication or institutional portal pending a dedicated speech-index audit. The public data file contains only institution, country, region, category, source type, and official page/feed URLs. It does **not** contain internal research notes, the team's scoring model, workbook rights metadata, market data, monitoring claims, or private documents. Links and feeds require verification before ingestion; this is not a live publication monitor.

The supplied `Prompt.docx` defines the sell-side report analysis workflow: a 500–800 word source-only summary, 3–5 ranked further-research questions, chart/table/footnote review, page references and careful attribution to the report's date. It does **not** define a numerical hawkish/dovish scoring rubric. The public site describes this method without embedding the private prompt file or pretending that a static page can analyse complete reports. The team's validated speech model must be integrated before numerical scores or an index are published.

The market calculator accepts a local CSV with `timestamp_utc,asset,value`. Timestamps must be ISO UTC, for example `2026-11-18T14:00:00Z`. It chooses the closest strictly earlier and strictly later observations within the selected maximum gap, then reports `after − before`. For a yield entered as percentage points, it also shows `100 × change` in basis points. The result is descriptive, not causal. It does not infer an event window automatically, handle simultaneous news, or create an index across speeches. No example values are fabricated. `dist/market-template.csv` contains only the header.

Production work still needs the team's validated model, a speech corpus with reliable release timestamps, versioned scoring and human review, licensed market series at a suitable frequency, and an event-study protocol. Do not commit proprietary model files, API keys or licensed data to this public repository.

## Local preview

Serve the `dist` directory with any static HTTP server, for example:

```sh
python3 -m http.server 8000 --directory dist
```

Open `http://localhost:8000`. Opening `index.html` directly as a file will block the JSON fetch in some browsers.

## GitHub Pages

The workflow in `.github/workflows/pages.yml` publishes `dist` on pushes to `main`. In repository **Settings → Pages**, select **GitHub Actions** as the build and deployment source. The site is designed to work from either a project path or a custom domain because asset references are relative.

## Updating sources

Edit `dist/data/sources.json` and `dist/data/coverage.json`. Each source record requires a unique `id`, an HTTPS `url`, and the displayed institution, country, region, category, source type and status. A feed URL is optional. Review publication rights and the accuracy of the page before promoting a proposed entry. Update the snapshot and expansion dates and on-page note when the directory changes.

No external fonts, trackers or runtime services are used. External institution links open in a new tab.
