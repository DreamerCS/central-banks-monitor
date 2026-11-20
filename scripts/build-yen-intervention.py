"""Build a fully static intervention study from Japan MOF, Federal Reserve H.10 and H.15.
Run from any directory: python scripts/build-yen-intervention.py
Optional --input-dir DIR reads operations.csv, DEXJPUS.csv and DGS2.csv locally.
"""
import argparse
from bisect import bisect_left, bisect_right
from collections import defaultdict
import calendar
import csv
from datetime import date
from hashlib import sha256
import io
import json
import math
from pathlib import Path
from statistics import mean, median, stdev
from urllib.request import Request, urlopen

from yen_intervention_page import render

CUTOFF = date(2026, 9, 30)
FIRST = date(1991, 4, 1)
TARGETS = (0, 5, 20)
SOURCE = {
    "operations.csv": "https://www.mof.go.jp/english/policy/international_policy/reference/feio/foreign_exchange_intervention_operations.csv",
    **{name + ".csv": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=" + name + "&cosd=1990-01-01&coed=2026-11-19" for name in ("DEXJPUS", "DGS2")}
}
GROUPS = {"sells":"Yen sales", "earlyBuys":"Yen purchases, 1991–98", "recentBuys":"Yen purchases, 2022–24", "latestBuys":"Yen purchases, 2026"}
MONTHS = {v:i for i,v in enumerate(calendar.month_abbr) if v}
PAIRS = {"the US dollar (sold) the Japanese yen (bought)":"buy", "the US dollar (bought) the Japanese yen (sold)":"sell"}


def load(name, folder):
    if folder:
        return (folder / name).read_bytes()
    req = Request(SOURCE[name], headers={"User-Agent":"Mozilla/5.0 (public market data)"})
    with urlopen(req, timeout=60) as source:
        return source.read()


def operations(body):
    rows = list(csv.reader(io.StringIO(body.decode("cp932"))))
    if not any("100 million Yen" in r[0] for r in rows):
        raise ValueError("Unexpected intervention currency units")
    amounts, all_days, other = {}, set(), 0
    year, month = None, None
    q3 = any("July - September 2026" in r for r in rows)
    if not q3: raise ValueError("Release does not certify the entire stated period")
    for r in rows:
        if len(r)<9 or not r[5].strip().isdigit(): continue
        if r[3].strip(): year = int(r[3])
        if r[4].strip(): month = MONTHS[r[4].strip()]
        day = date(year, month, int(r[5]))
        if not FIRST <= day <= CUTOFF: continue
        pair = " ".join(r[8].split())
        if not pair: raise ValueError(f"Missing currency pair: {day}")
        all_days.add(day)
        if pair not in PAIRS:
            other += 1
            continue
        direction, amount = PAIRS[pair], int(r[6].replace(",",""))
        if day in amounts: raise ValueError(f"Duplicate yen/dollar operation date: {day}")
        amounts[day] = {"date":day,"direction":direction,"amount":amount}
    return [amounts[d] for d in sorted(amounts)], sorted(all_days), other


def feed(body, series):
    rows = csv.DictReader(io.StringIO(body.decode("utf-8-sig")))
    if rows.fieldnames != ["observation_date",series]: raise ValueError(f"Unexpected header: {series}")
    out = {}
    for r in rows:
        d = date.fromisoformat(r["observation_date"])
        if d <= CUTOFF and r[series] not in ("","."):
            v = float(r[series])
            if d in out or not math.isfinite(v): raise ValueError(f"Invalid {series} observation {d}")
            out[d] = v
    return out


def cluster(actions, days):
    episodes = []
    for a in actions:
        prev = episodes[-1][-1] if episodes else None
        if prev and a["direction"] == prev["direction"] and bisect_right(days,a["date"])-bisect_right(days,prev["date"])<=5:
            episodes[-1].append(a)
        else: episodes.append([a])
    return episodes


# Dates of BOJ framework announcements, per the two official historical chronologies.
BREAKS = [date.fromisoformat(s) for s in (
    "1999-02-12", "2000-08-11", "2001-03-19", "2006-03-09", "2010-10-05",
    "2013-04-04", "2016-01-29", "2016-09-21", "2024-03-19")]


def period(d):
    return bisect_right(BREAKS,d)


def category(action):
    if action["direction"] == "sell": return "sells"
    year = action["date"].year
    if year <= 1998: return "earlyBuys"
    if 2022 <= year <= 2024: return "recentBuys"
    if year == 2026: return "latestBuys"
    raise ValueError(f"Update cohort definitions: {year}")


def rounded(value):
    return round(value, 6)


def direction_move(a, b, side):
    return (1 if side == "sell" else -1) * 100 * math.log(b / a)


def build(folder):
    files = {name:load(name,folder) for name in SOURCE}
    actions, all_days, other = operations(files["operations.csv"])
    prices = feed(files["DEXJPUS.csv"],"DEXJPUS")
    yields = feed(files["DGS2.csv"],"DGS2")
    days, ydays = sorted(prices), sorted(yields)
    def yield_at(d):
        i = bisect_right(ydays,d)-1
        return yields[ydays[i]] if i>=0 and (d-ydays[i]).days<=5 else None
    def has_operation(after, until):
        return bisect_right(all_days,after) < bisect_right(all_days,until)
    features = {}
    for i in range(20,len(days)):
        y1,y2 = yield_at(days[i-20]),yield_at(days[i])
        if y1 is None or y2 is None: continue
        moves = [100*math.log(prices[days[j]]/prices[days[j-1]]) for j in range(i-19,i+1)]
        features[i] = [sum(moves),stdev(moves),100*(y2-y1)]
    episodes = []
    for group in cluster(actions,days):
        first,last = group[0]["date"],group[-1]["date"]
        side = group[0]["direction"]
        i = bisect_left(days,first)-1
        j = bisect_right(days,last)  # strictly after the final Tokyo operation date
        if i not in features or j+20>=len(days): raise ValueError(f"Incomplete window for {first}")
        span = j-i
        def regime_path(start):
            return tuple(period(days[k]) for k in (start-20,start,start+span,start+span+20))
        actual_regime = regime_path(i)
        eligible = []
        for o, feat in features.items():
            if o+span+20>=len(days) or days[o-20]<FIRST: continue
            if abs((days[o]-days[i]).days)>731 or regime_path(o)!=actual_regime: continue
            if bisect_left(all_days,days[o-20]) < bisect_right(all_days,days[o+span+20]): continue
            eligible.append(o)
        matches=[]
        if len(eligible)>=3:
            scales = [stdev(features[o][k] for o in eligible) for k in range(3)]
            if min(scales)<=0: raise ValueError("Degenerate candidate feature")
            ranked=[]
            for o in eligible:
                diffs=[(features[o][k]-features[i][k])/scales[k] for k in range(3)]
                if max(map(abs,diffs))<=1.5:
                    ranked.append((sum(x*x for x in diffs),o))
            for _,o in sorted(ranked):
                if all(o+span+20<m-20 or m+span+20<o-20 for m in matches): matches.append(o)
                if len(matches)==3: break
        if len(matches)<3: matches=[]
        def quote(n):return {"date":days[n].isoformat(),"yenPerDollar":prices[days[n]]}
        def comparison(o):
            return {"baseline":quote(o),"prior20":list(map(rounded,features[o])),
                    "quotes":[quote(o+span+n) for n in TARGETS],
                    "moves":[rounded(direction_move(prices[days[o]],prices[days[o+span+n]],side)) for n in TARGETS]}
        controls=[comparison(o) for o in matches]
        obs=comparison(i)
        outcomes=[]
        for h,n in enumerate(TARGETS):
            # Same-day other-currency operations may form part of the intervention; censor later operations.
            clean = not has_operation(last,days[j+n])
            gap=obs["moves"][h]-mean(c["moves"][h] for c in controls) if controls else None
            outcomes.append({"clean":clean,"matchedExcess":rounded(gap) if gap is not None else None})
        episodes.append({"first":str(first),"last":str(last),"group":category(group[0]),"direction":side,
                         "operations":[[str(a["date"]),a["amount"]] for a in group],
                         "amount100mYen":sum(a["amount"] for a in group),**obs,"outcomes":outcomes,
                         "controls":controls,"candidateCount":len(eligible)})
    def summary(chosen):
        results=[]
        for h in range(3):
            usable=[e for e in chosen if e["outcomes"][h]["clean"]]
            raw=[e["moves"][h] for e in usable]
            gaps=[e["outcomes"][h]["matchedExcess"] for e in usable if e["outcomes"][h]["matchedExcess"] is not None]
            def tally(nums):
                return {"n":len(nums),"median":rounded(median(nums)) if nums else None,
                        "positive":sum(round(v,2)>0 for v in nums),"ties":sum(round(v,2)==0 for v in nums)}
            matched_raw=[e["moves"][h] for e in usable if e["controls"]]
            results.append({"observed":tally(raw),"matched":tally(gaps),
                            "matchedObservedMedian":rounded(median(matched_raw)) if matched_raw else None,
                            "excluded":len(chosen)-len(raw)})
        return results
    grouped={key:{"title":title,"results":summary([e for e in episodes if e["group"]==key]),
                  "episodes":sum(e["group"]==key for e in episodes)} for key,title in GROUPS.items()}
    return {"through":str(CUTOFF),"first":str(FIRST),"horizons":TARGETS,"sources":SOURCE,
            "operations":len(actions),"otherCurrencyOperations":other,"groups":grouped,"episodes":episodes,
            "frameworkBreaks":[d.isoformat() for d in BREAKS],
            "sourceHashes":{name:sha256(body).hexdigest() for name,body in files.items()}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir",type=Path)
    parser.add_argument("--dist",type=Path,default=Path(__file__).resolve().parents[1]/"dist")
    args=parser.parse_args()
    data=build(args.input_dir)
    args.dist.mkdir(exist_ok=True,parents=True)
    (args.dist/"data").mkdir(exist_ok=True)
    (args.dist/"data/yen-intervention.json").write_text(json.dumps(data,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf8")
    (args.dist/"yen-intervention.html").write_text(render(data),encoding="utf8")
    print(len(data["episodes"]),"episodes",len([e for e in data["episodes"] if e["controls"]]),"matched")


if __name__=="__main__": main()
