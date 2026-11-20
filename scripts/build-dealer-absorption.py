#!/usr/bin/env python3
"""Pair ten-year Treasury competitive awards with weekly FR 2004A net positions."""
import argparse
from collections import defaultdict
from datetime import date, timedelta
import json
from pathlib import Path
from statistics import median
from urllib.request import urlopen

from dealer_settled_positions import build_same_security

SERIES = "PDPOSGSC-G7L11"
PD_API = "https://markets.newyorkfed.org/api/pd/"
TREASURY_API = "https://www.treasurydirect.gov/TA_WS/securities/search?format=json&type=Note"
TREASURY = "https://www.treasurydirect.gov/instit/annceresult/press/preanre/"
CONTINGENCY = {("2019-06-21", "9128286T2")}
AS_OF = "2026-11-20"
WEEK = timedelta(weeks=1)
HORIZONS = ["preTrend", "baseline", "preSettlement", "settlement", "week1", "week2", "week3"]
SOURCES = [
    {"label": "US Treasury · TreasuryDirect auction results (note records)", "url": TREASURY_API},
    {"label": "US Treasury · Treasury Securities Auctions Data", "url": "https://fiscaldata.treasury.gov/datasets/treasury-securities-auctions-data/"},
    {"label": "New York Fed · net positions for nominal coupons over 7 and up to 11 years", "url": PD_API + "get/" + SERIES + ".json"},
    {"label": "New York Fed · reporting periods and release schedule", "url": "https://www.newyorkfed.org/markets/counterparties/primary-dealers-statistics"},
    {"label": "Federal Reserve Board · FR 2004 reports and instructions", "url": "https://www.federalreserve.gov/apps/reportingforms/Report/Index/FR_2004"},
    {"label": "Treasury · June 2019 contingency operation", "url": TREASURY + "2019/BPD_SPL_20190620_4.pdf"},
    {"label": "Glicoes, Petrasek, Saravay and Tian (2026) · CUSIP-level inventory study", "url": "https://www.federalreserve.gov/econres/notes/feds-notes/treasury-issuance-and-dealer-balance-sheets-20261030.html"},
    {"label": "Federal Reserve Board · inventory half-life by tenor, figure 4", "url": "https://www.federalreserve.gov/econres/notes/feds-notes/treasury-issuance-and-dealer-balance-sheets-accessible-20261030.htm"},
]


def read_json(url, local):
    if local and local.exists():
        return json.loads(local.read_bytes())
    with urlopen(url, timeout=90) as response:
        raw = response.read()
    result = json.loads(raw)
    if local:
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(raw)
    return result


def wednesday_on_or_after(day):
    return day + timedelta(days=(2 - day.weekday()) % 7)


def wednesday_before(day):
    return wednesday_on_or_after(day) - WEEK


def date_field(row, key):
    return date.fromisoformat(row[key][:10])


def apportion_groups(events):
    cells = defaultdict(list)
    for event in events:
        cells[event["regime"], event["issueType"]].append(event)
    # Interpolated sample terciles within homogeneous reporting and issuance groups.
    # Keep full-precision competitive shares when locating cut-offs.
    cutoffs = []
    for (regime, issue_type), members in sorted(cells.items()):
        shares = sorted(e["dealerSharePct"] for e in members)
        def quantile(p):
            k = (len(shares) - 1) * p
            lower = int(k)
            return shares[lower] + (shares[min(lower + 1, len(shares)-1)] - shares[lower]) * (k-lower)
        low, high = quantile(1/3), quantile(2/3)
        for e in members:
            share = e["dealerSharePct"]
            e["awardGroup"] = "Low" if share <= low else "High" if share >= high else "Middle"
            e["dealerSharePct"] = round(share, 6)
        cutoffs.append({"regime": regime, "issueType": issue_type, "n": len(shares),
                        "lowMaxPct": round(low, 6), "highMinPct": round(high, 6)})
    return cutoffs


def summarise(events):
    rows = []
    for issue_type in ("All","New issue","Reopening"):
        for group in ("All","High","Middle","Low"):
            sample = [e for e in events if issue_type in ("All",e["issueType"]) and group in ("All",e["awardGroup"])]
            hs = {}
            for h in HORIZONS:
                changes = [e["reports"][h]["positionBn"] - e["reports"]["baseline"]["positionBn"]
                           for e in sample if e["reports"][h] and e["reports"]["baseline"]]
                hs[h] = {"n": len(changes), "medianChangeBn": round(median(changes), 6) if changes else None}
            rows.append({"issueType": issue_type, "awardGroup": group, "events": len(sample), "horizons": hs})
    return rows


def build(as_of, cache):
    def load(key, url):
        return read_json(url, cache / key if cache else None)
    releases = load("list", PD_API + "list/seriesbreaks.json")["pd"]["seriesbreaks"]
    positions = load("univ", PD_API + "get/" + SERIES + ".json")["pd"]["timeseries"]
    # The public report normally appears the following Thursday (at least eight days).
    last_public = as_of - timedelta(days=8)
    marks = {date.fromisoformat(p["asofdate"]): int(p["value"]) / 1000 for p in positions
             if p["asofdate"] <= last_public.isoformat() and p["value"] not in ("",None,"*")}
    start, last = min(marks), max(marks)
    regimes = [r for r in releases if r["enddate"] >= start.isoformat() and r["startdate"] <= as_of.isoformat()]
    def regime(day):
        return next((r["seriesbreak"] for r in regimes if r["startdate"] <= day.isoformat() <= r["enddate"]), None)

    auctions = []
    treasury_rows = load("treas", TREASURY_API)
    for row in treasury_rows:
        if row.get("originalSecurityTerm") != "10-Year" or row.get("securityType") != "Note" or row.get("inflationProtected") != "No":
            continue
        if not row.get("competitiveAuctionCloseDate") or not row.get("primaryDealersCompetitiveParAwarded"):
            continue
        auction, issue, maturity = [date_field(row, k) for k in ("competitiveAuctionCloseDate", "issueDate", "maturityDate")]
        if not start <= auction <= as_of or (auction.isoformat(), row["cusip"]) in CONTINGENCY:
            continue
        # Both new notes and these regular reopenings have over nine years to maturity.
        # The tenor field alone misclassifies a three-year auction on 5 November 2019.
        if not 9.0 < (maturity-issue).days/365.25 < 10.1:
            continue
        awards = [int(row[k]) for k in ("primaryDealersCompetitiveParAwarded","directBiddersCompetitiveParAwarded","indirectBiddersCompetitiveParAwarded")]
        total = int(row["subtotalCompetitiveParAwardedInsideOfOfferingAmount"])
        if sum(awards) != total or total <= 0 or row["reopening"] not in ("Yes","No"):
            raise ValueError(f"Review Treasury allocation fields at {auction}: {awards}, {total}")
        auctions.append((auction, issue, row, awards[0], total))
    auctions.sort(key=lambda a:a[0])
    ids = {(a,r["cusip"]) for a, _, r, _, _ in auctions}
    if len(ids) != len(auctions):
        raise ValueError("Duplicate auction date/CUSIP")
    events = []
    for i,(a, issue, row, dealer, competitive) in enumerate(auctions):
        group = regime(a)
        next_auction = auctions[i+1][0] if i+1 < len(auctions) else None
        baseline, settlement = wednesday_before(a), wednesday_on_or_after(issue)
        dates = [baseline-WEEK, baseline, wednesday_before(issue), settlement,
                 settlement+WEEK, settlement+2*WEEK, settlement+3*WEEK]
        reports = {}
        missing = {}
        for h,day in zip(HORIZONS, dates):
            reason = None
            if day < start or day > last:
                reason = "outside published observations"
            elif regime(day) != group:
                reason = "reporting-period boundary"
            elif day not in marks:
                reason = "weekly observation missing"
            elif next_auction and day >= next_auction:
                reason = "next scheduled ten-year auction"
            if reason:
                reports[h] = None
                missing[h] = reason
            else:
                reports[h] = {"date": day.isoformat(), "positionBn": marks[day]}
        events.append({"auctionDate": a.isoformat(), "issueDate": issue.isoformat(), "cusip": row["cusip"],
                       "issueType": "Reopening" if row["reopening"] == "Yes" else "New issue",
                       "regime": group, "competitiveAwardBn": competitive/1e9, "dealerAwardBn": dealer/1e9,
                       "dealerSharePct": dealer/competitive*100, "reports": reports, "unavailable": missing,
                       "resultsUrl": TREASURY + str(a.year) + "/" + row["treasuryAuctionResultsPressReleaseFileName"]})
    cutoffs = apportion_groups(events)
    specific = load("specific", PD_API + "get/PDSI10NSP.json")["pd"]["timeseries"]
    same_security = build_same_security(events, treasury_rows, specific)
    return {
        "asOf": as_of.isoformat(), "series": SERIES,
        "coverage": {"firstAuction": events[0]["auctionDate"], "lastAuction": events[-1]["auctionDate"],
                     "firstPosition": start.isoformat(), "lastPosition": last.isoformat(), "weeklyObservations": len(marks),
                     "auctionCount": len(events), "newIssues": sum(e["issueType"]=="New issue" for e in events),
                     "reopenings": sum(e["issueType"]=="Reopening" for e in events),
                     "matchedFirstReport": sum(bool(e["reports"]["settlement"] and e["reports"]["baseline"]) for e in events)},
        "regimes": [{"id":r["seriesbreak"],"label":r["label"],"start":r["startdate"],"end":None if r["enddate"]=="9999-12-31" else r["enddate"]} for r in regimes],
        "groupCutoffs": cutoffs, "summary": summarise(events),
        "method": {"question":"Are relatively large primary-dealer awards at regular nominal ten-year Treasury auctions followed by a larger or more persistent change in aggregate coupon inventories?",
                   "award":"Primary dealers’ competitive par award divided by the competitive par awarded inside the offering. Official competitive bidder classes reconcile to this denominator. All regular new issues and reopenings are retained; the June 2019 contingency test is excluded.",
                   "groups":"Rank all awards in each reporting period and issue type. The bottom and top thirds use inclusive linearly interpolated 1/3 and 2/3 cut-offs. The cut-offs use each full sample period and are retrospective.",
                   "timing":"Baseline is the last Wednesday strictly before auction. Settlement is the first Wednesday on or after issue. Later observations use exact weekly offsets and are omitted at a reporting break or from the next regular ten-year auction onward. Pre-trend is the prior Wednesday. Pre-settlement is the last Wednesday strictly before issue and can include the auction.",
                   "units":"Awards are at par. Weekly positions use market value, in USD billions, for nominal Treasury coupons with more than seven and no more than eleven years remaining. Net equals outright long less short. The Fed’s trade-date series includes when-issued trading and auction allotments on the award date.",
                   "interpretation":"The weekly maturity bucket contains other securities, valuation changes and secondary trades. Its change can reflect a short being covered. Trade timing, unrelated flows and shared market conditions leave the holding period of a particular security unidentified.",
                   "release":"FR 2004A Wednesday observations are normally released the following Thursday, at least eight days later, and may be revised."},
        "sources": SOURCES + same_security["sources"], "events": events, "sameSecurity": same_security}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=AS_OF)
    parser.add_argument("--cache", type=Path, help="Read or populate an optional cache of official JSON responses")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "dist/data/dealer-absorption.json")
    args = parser.parse_args()
    dataset = build(date.fromisoformat(args.as_of), args.cache)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dataset, separators=(",",":"), ensure_ascii=False) + "\n")
    print(json.dumps(dataset["coverage"]))
