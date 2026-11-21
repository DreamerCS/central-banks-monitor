# The Policy Tape

Central bank data and publications for 29 jurisdictions. The [live site](https://dreamercs.github.io/central-banks-monitor/) includes a market-reaction explorer, rates and FX history, a publication map and a monthly archive.

## Data sources

- The monthly archive indexes central bank decisions, minutes, speeches and research from January to November 2026. Each entry links to its source. Publication counts describe documents indexed in the archive.
- The historical chart draws on [BIS central bank policy rates](https://data.bis.org/topics/CBPOL), the [Taiwan central bank discount rate schedule](https://www.cbc.gov.tw/en/lp-695-2.html) and the [BIS daily Singapore nominal effective exchange rate](https://data.bis.org/topics/EER/BIS%2CWS_EER%2C1.0/D.N.B.SG). The year, month and Monday–Sunday week views use the last available observation in each period.
- Announcement-window changes come from the San Francisco Fed USMPD and ECB EA-EMPD. The overview uses Federal Reserve rates and exchange rates via FRED.
- The U.S. yield chart uses the [Treasury daily par yield curve](https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics).

## Run locally

```sh
python3 -m pip install 'openpyxl>=3.1,<4'
curl -fL https://www.frbsf.org/wp-content/uploads/USMPD.xlsx -o /tmp/usmpd.xlsx
curl -fL https://www.ecb.europa.eu/pub/pdf/other/Dataset_EA-MPD.xlsx -o /tmp/ea-empd.xlsx
python3 scripts/build-market-events.py /tmp/usmpd.xlsx /tmp/ea-empd.xlsx
python3 scripts/update-market-history.py
python3 scripts/build-research-archive.py
python3 scripts/check-data.py
python3 -m http.server 8000 --directory dist
```

The repository’s GitHub Pages workflow publishes `dist/` and refreshes the dated Treasury yields and publication map. To regenerate the historical series, run `python3 scripts/build-historical-data.py --help`. The input files are the BIS policy-rate flat CSV ZIP, the three CBC discount-rate table pages and the BIS daily Singapore NEER CSV.
