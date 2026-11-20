# Central Bank Intelligence

Central bank data and publications for 29 jurisdictions. The [live site](https://dreamercs.github.io/central-banks-monitor/) includes a publication map, monthly archive, source directory and historical data explorer.

## Data sources

- The monthly archive indexes central bank decisions, minutes, speeches and research from June to November 2026. Each entry links to its source. Publication counts describe documents indexed in the archive.
- The historical chart draws on [BIS central bank policy rates](https://data.bis.org/topics/CBPOL), the [Taiwan central bank discount rate schedule](https://www.cbc.gov.tw/en/lp-695-2.html) and the [BIS daily Singapore nominal effective exchange rate](https://data.bis.org/topics/EER/BIS%2CWS_EER%2C1.0/D.N.B.SG). The year, month and Monday–Sunday week views use the last available observation in each period.
- The U.S. yield chart uses the [Treasury daily par yield curve](https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics).

## Run locally

```sh
python3 scripts/build-research-archive.py
python3 scripts/check-data.py
python3 -m http.server 8000 --directory dist
```

The repository’s GitHub Pages workflow publishes `dist/` and refreshes the dated Treasury yields and publication map. To regenerate the historical series, run `python3 scripts/build-historical-data.py --help`. The input files are the BIS policy-rate flat CSV ZIP, the three CBC discount-rate table pages and the BIS daily Singapore NEER CSV.
