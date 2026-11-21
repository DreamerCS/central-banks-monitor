"""Describe ECB intraday market changes across recorded speech and testimony windows."""
import argparse
import csv
import itertools
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

DATA = Path(__file__).resolve().parents[1] / "dist" / "data"
START, END = "2000-01-01", "2025-12-31"
KEYS = ("ois1y", "yield2y", "slope", "equity", "eurusd")


def quantile(values, q):
    if not values:
        return None
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return ordered[lo] + (pos - lo) * (ordered[hi] - ordered[lo])


def ranks(series):
    ranked = [None] * len(series)
    order = sorted(range(len(series)), key=series.__getitem__)
    # Average the tied ranks, including unchanged quotes.
    start = 0
    for _, group in itertools.groupby(order, key=series.__getitem__):
        positions = list(group)
        middle = start + (len(positions) - 1) / 2
        for index in positions:
            ranked[index] = middle
        start += len(positions)
    return ranked


def spearman(pairs):
    if len(pairs) < 3:
        return None
    x, y = (ranks(axis) for axis in zip(*pairs))
    centre = (len(pairs) - 1) / 2
    xx, xy, yy = 0.0, 0.0, 0.0
    for a, b in zip(x, y):
        dx, dy = a-centre, b-centre
        xx += dx*dx
        yy += dy*dy
        xy += dx*dy
    return round(xy / math.sqrt(xx*yy), 4) if xx and yy else None


def rounded(value):
    return None if value is None else round(value, 6)


def asset_stats(rows, key):
    series = [r["values"][key] for r in rows if key in r["values"]]
    absolute = [abs(v) for v in series]
    return dict(asset=key, n=len(series), median=rounded(quantile(series, .5)),
                medianAbs=rounded(quantile(absolute, .5)), p90Abs=rounded(quantile(absolute, .9)))


def paired_stats(rows, key):
    by_day = defaultdict(list)
    for r in rows:
        v = r["values"]
        if "ois1y" in v and key in v:
            by_day[r["date"]].append((v["ois1y"], v[key]))
    pairs = [p for day in by_day.values() for p in day]
    day_means = [tuple(mean(axis) for axis in zip(*group)) for group in by_day.values()]
    boundary = quantile([abs(x) for x,y in pairs], .99)
    trimmed = [(x,y) for x,y in pairs if abs(x) <= boundary]
    up, down = [y for x,y in pairs if x > 1], [y for x,y in pairs if x < -1]
    return dict(asset=key, n=len(pairs), nDays=len(by_day), spearman=spearman(pairs),
                daySpearman=spearman(day_means), trimmedSpearman=spearman(trimmed),
                trimN=len(trimmed), trimThresholdAbsBp=rounded(boundary),
                upN=len(up), upMedian=rounded(quantile(up,.5)), downN=len(down), downMedian=rounded(quantile(down,.5)))


def group(kind, label, rows):
    return dict(kind=kind, label=label, nEvents=len(rows), nDays=len({r["date"] for r in rows}),
                distribution=[asset_stats(rows, k) for k in KEYS], pairs=[paired_stats(rows, k) for k in KEYS[1:]])


def speaker_role(row):
    # Title aliases in the source include Willem F. / Wim Duisenberg.
    return "ECB president" if row["speaker"].split()[-1] == row["leader"].split()[-1] else "Other Executive Board member"


def build(data):
    meta = json.loads((data / "ecb-cross-asset-events.json").read_text())
    appearances = []
    for part in meta["parts"]:
        appearances.extend(json.loads((data / (part + ".json")).read_text())["records"])
    appearances = sorted((r for r in appearances if START <= r["date"] <= END),
                         key=lambda r:(r["date"], r["time"], r["id"]))
    if len({r["id"] for r in appearances}) != len(appearances):
        raise ValueError("Repeated ECB appearance identity")
    eligible = [r for r in appearances if r["groupEligible"]]
    decisions = [r for r in meta["records"] if START <= r["date"] <= END and r["stage"] == "release" and r["groupEligible"]]
    flags = Counter(f for r in appearances for f in r.get("flags", []))
    coverage = dict(allEvents=len(appearances), eligibleEvents=len(eligible),
                    eligibleDays=len({r["date"] for r in eligible}), withOis1y=sum("ois1y" in r["values"] for r in eligible),
                    withCorpusMatch=sum(bool(r.get("textMatched")) for r in eligible),
                    allWithCorpusMatch=sum(bool(r.get("textMatched")) for r in appearances),
                    nSpeakers=len({r["speaker"] for r in eligible}),
                    flags=[dict(label=f, n=n) for f,n in flags.most_common()])
    groups = [dict(group("all", "All eligible speeches", eligible), nAllEvents=len(appearances))]
    for kind, classify in [("year", lambda r:r["date"][:4]), ("leader", lambda r:r["leader"]), ("speakerRole", speaker_role)]:
        grouped = defaultdict(list)
        for row in eligible:
            grouped[classify(row)].append(row)
        all_counts = Counter(classify(row) for row in appearances)
        groups.extend(dict(group(kind, key, rows), nAllEvents=all_counts[key]) for key, rows in grouped.items())
    groups.append(group("decisionRelease", "Standard ECB decision releases", decisions))
    linked = [r for r in eligible if r.get("documentUrl") and "ois1y" in r["values"]]
    examples = []
    for label, row in (("Largest rise",max(linked,key=lambda r:r["values"]["ois1y"])),
                       ("Largest fall",min(linked,key=lambda r:r["values"]["ois1y"]))):
        examples.append(dict(selection=label, **{k:row[k] for k in ("id","date","time","speaker","title","documentUrl","window")},
                             values={k:row["values"].get(k) for k in KEYS}))
    assets = [dict(key=k,label=a["label"],unit=a["unit"]) for k in KEYS for a in meta["assets"] if a["id"]==k]
    result = dict(period=dict(start=START, end=END), coverage=coverage, assets=assets, groups=groups,
                  examples=examples, source=meta["source"], method=[
        "The frame is every timestamped speech or testimony recorded in the ECB EA-EMPD during 2000–2025. The main statistics exclude non-trading sessions, overlapping ECB appearances, decision-day speeches and records with no reported asset changes. An observed change of zero remains eligible. No movement threshold or text score is required. Flag counts can overlap.",
        "Changes compare median quotes 20–10 minutes before the recorded start with quotes 40–50 minutes after it, using the database’s assumed talk duration. Other economic news can occur within this interval. Missing observations remain missing and reported zeros are retained.",
        "For each asset, the table gives its signed median change, the median absolute move and the 90th percentile of absolute moves. OIS and yields use basis points. 2s10s is the 10-year less 2-year German yield. Equities and EUR/USD use percentage changes; a positive FX change indicates euro appreciation.",
        "Rank correlations use only appearances with both the 1-year OIS and the specified asset. The date sensitivity first averages these paired observations within each local date, then ranks dates equally. The outlier sensitivity excludes observations strictly above the subgroup’s 99th percentile of absolute OIS changes and keeps ties. Subgroup medians for OIS rises above 1 bp and falls below −1 bp describe only those tails.",
        "The president-in-office breakdown includes appearances by other Executive Board members. Speaker-role figures distinguish the officeholder’s own appearances. The decision comparison uses eligible release windows, which have different durations and contain formal policy announcements.",
        "Rank correlations describe co-movement. The one-year OIS can respond to policy guidance, economic information or other news. The two examples have the largest positive and negative 1-year OIS moves among eligible appearances with a direct official transcript link; the links are more often available for manually reviewed speeches.",
    ])
    (data / "speech-market-panel.json").write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    fields = ["id","date","time","timeZone","leader","speaker","speakerRole","title","eligible","flags","textMatched","documentUrl","window",*KEYS]
    with (data / "policy-research-ecb-speeches.csv").open("w",encoding="utf-8",newline="") as file:
        writer = csv.DictWriter(file,fieldnames=fields,lineterminator="\n");writer.writeheader()
        for r in appearances:
            out = {k:r.get(k,"") for k in ("id","date","time","timeZone","leader","speaker","title","documentUrl","window")}
            out.update(speakerRole=speaker_role(r),eligible=int(r["groupEligible"]),flags=" | ".join(r.get("flags",[])),
                       textMatched=int(bool(r.get("textMatched"))))
            out.update({k:r["values"].get(k,"") for k in KEYS})
            writer.writerow(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data",type=Path,default=DATA)
    build(parser.parse_args().data)
