"""Build a descriptive event study from the published guidance panels and matched intraday data.

First generate dist/data/market-events.json using
python scripts/build-market-events.py USMPD.xlsx Dataset_EA-MPD.xlsx.
Run with Python 3. Use --workbooks USMPD.xlsx Dataset_EA-MPD.xlsx to audit every
selected asset against the original workbooks (requires openpyxl). The offline
build identifies the audited market extract by SHA-256 and needs no spreadsheet library.
"""

import argparse
import hashlib
import json
from collections import Counter
from itertools import product
from pathlib import Path
from statistics import fmean, median
from tempfile import NamedTemporaryFile


DATA = Path(__file__).resolve().parents[1] / "dist" / "data"
MARKET = "market-events.json"
PANELS = {"fed": "policy-guidance.json", "ecb": "ecb-guidance.json"}
STATES = ("tightening", "easing", "balanced", "unclear")
ACTIONS = ("all", "hold", "raise", "cut")
RANK = {"easing": -1, "balanced": 0, "tightening": 1}
ASSETS = {
    "fed": ("UST2Y", "OIS1Y", "SP500", "MP2", "MP1"),
    "ecb": ("DE2Y", "OIS_1Y", "STOXX50", "OIS_1M"),
}
WORKBOOK_URLS = {
    "fed": "https://www.frbsf.org/wp-content/uploads/USMPD.xlsx",
    "ecb": "https://www.ecb.europa.eu/pub/pdf/other/Dataset_EA-MPD.xlsx",
}
AUDITED_EXTRACT = "5bfc14e7505361f380e186987f37d853ac868c68ad46018a008c3dbe175e7d85"
AUDITED_WORKBOOKS = {
    "fed": "2b91297c42cf692dd74f65eabf7ee97f81d452676e23fa02edb222bfa60f0d0a",
    "ecb": "548abe37c07b2f4535b6a5a480918df3226aea9b1d65d5a74580894c83b3713b",
}
METHOD = [
    "Each release carries the rate direction explicitly contemplated after the announced decision. A hold or two-sided signal requires affirmative evidence. Unspecified guidance remains a separate category. Conditional language can identify a direction without promising a move.",
    "Match the institution, release date and type of communication. The US sample uses the FOMC statement window. The ECB decision release and subsequent conference have separate windows, including the questions to the ECB President. Each release has equal weight within its own cell.",
    "A positive rate change means yields or expected rates rose. Rates are in basis points and stock index returns in percent. A median difference subtracts the easing-group median from the tightening-group median within the same window and action filter. A blank requires a missing observation or comparison. An observed zero counts as zero.",
    "These are selected historical releases. Dates in the same policy cycle can share expectations and economic conditions. Even unchanged policy can surprise, and forecasts, asset purchases and economic news can accompany a statement. The comparisons describe repricing and do not identify the independent effect of the words.",
    "A change in guidance compares two verified consecutive decisions with comparable communications. Gaps stay unclassified. Moving into or out of unspecified guidance changes explicitness. Only transitions between explicit states receive a direction.",
]
EXAMPLE_NOTES = {
    "fed": {
        "2004-01-28": "The funds target stayed at 1%. The Committee moved from a low-rate holding horizon to describing when it could withdraw accommodation. Compare this with December 2014, another hold that pointed to eventual tightening.",
        "2014-12-17": "The Committee explicitly linked patience about eventual normalization to its earlier promise of sustained accommodation. The two-year yield fell in the statement window even as eventual tightening entered the guidance.",
        "2024-01-31": "A reduction entered the statement as a conditional possibility. The Committee wanted greater confidence in sustained disinflation first. The next-meeting futures measure and the two-year yield both rose.",
        "2026-09-16": "The Fed raised its target range by 25 basis points without specifying its next move. The current-meeting futures surprise separates the unexpected component from the announced adjustment.",
    },
    "ecb": {
        "2011-03-03": "At the press conference following a hold, Trichet acknowledged the possibility of an increase at the next meeting. The German two-year yield rose during the conference.",
        "2013-07-04": "Following another hold, Draghi left the door open to lower rates for an extended period. The two-year yield fell during the conference. Compare this response with the March 2011 conference, another actual hold.",
        "2022-06-09": "In the decision release, the Council outlined an intended July increase, a further September increase and the end of net asset purchases. Yields already moved in the decision window, before the press conference began.",
        "2026-06-11": "A quarter-point increase accompanied revised staff inflation projections and an open future rate path. The German two-year yield rose in the decision window.",
    },
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rounded(value):
    return round(value, 6) or 0


def stats(events, asset):
    values = [row["values"][asset] for row in events if row["values"][asset] is not None]
    result = {"eligible": len(events), "n": len(values), "missing": len(events) - len(values),
              "positive": sum(v > 0 for v in values), "negative": sum(v < 0 for v in values),
              "zero": sum(v == 0 for v in values)}
    for key, compute in (("median", median), ("mean", fmean), ("min", min), ("max", max)):
        result[key] = rounded(compute(values)) if values else None
    return result


def gap(high, low, key):
    if high[key] is None or low[key] is None:
        return None
    return rounded(high[key] - low[key])


def note_links():
    notes = json.loads((DATA / "research-notes.json").read_text())
    lookup = {}
    for note in notes:
        for url in [note["url"], *note.get("publication", {}).get("aliases", [])]:
            key = (note["date"], url)
            if key in lookup and lookup[key] != note["file"]:
                raise ValueError(f"Ambiguous manuscript link for {key}")
            lookup[key] = note["file"]
    return lookup


def releases(panel, bank, notes):
    events = {row["date"]: row["windows"] for row in bank["events"]}
    seen = {}
    result = []
    for obs in panel["observations"]:
        day = obs["date"]
        if obs["state"] not in STATES or obs["action"] not in ACTIONS[1:]:
            raise ValueError(f"Unrecognised action or guidance on {day}")
        if bank["id"] == "ecb":
            window = {"decision-release": "statement", "press-conference": "conference"}[obs["sourceType"]]
        else:
            window = "statement"
        key = (day, window)
        if key in seen or obs["bank"] != bank["id"]:
            raise ValueError(f"Invalid institution or repeated {window} on {day}")
        market = events.get(day, {}).get(window)
        prior = obs.get("priorDate")
        shift = obs.get("shift")
        change = "uncompared"
        if prior:
            previous = seen[(prior, window)]
            if bool(shift) != (previous["state"] != obs["state"]):
                raise ValueError(f"Inconsistent guidance pair on {day}")
            change = "unchanged"
            if shift:
                if (shift["from"], shift["to"]) != (previous["state"], obs["state"]):
                    raise ValueError(f"Incorrect change in source guidance on {day}")
                if "unclear" in (shift["from"], shift["to"]):
                    change = "explicitness"
                else:
                    change = "towardsTightening" if RANK[shift["to"]] > RANK[shift["from"]] else "towardsEasing"
        elif shift:
            raise ValueError(f"Shift without preceding release on {day}")
        event = {k: obs[k] for k in ("date", "action", "state", "rateChangeBps", "url", "evidence")}
        event.update(window=window, hasWindow=market is not None, priorDate=prior,
                     shift=shift, change=change, noteFile=notes.get((day, obs["url"])),
                     values={a: (market or {}).get(a) for a in ASSETS[bank["id"]]})
        seen[key] = event
        result.append(event)
    return result


def comparison(window, action, asset, high, low):
    return {"window": window, "action": action, "asset": asset,
            "tighteningN": high["n"], "easingN": low["n"],
            "medianGap": gap(high, low, "median"), "meanGap": gap(high, low, "mean")}


def build_bank(panel, market, notes):
    bank_id = market["id"]
    assets = {a["id"]: a for a in market["assets"]}
    asset_list = [assets[key] for key in ASSETS[bank_id]]
    events = releases(panel, market, notes)
    windows = []
    groups = []
    contrasts = []
    for window in ("statement", "conference"):
        rows = [e for e in events if e["window"] == window]
        if not rows:
            continue
        windows.append({"id": window, "label": "Decision release" if window == "statement" else "Press conference",
                        "definition": market["windows"][window], "selected": len(rows),
                        "matched": sum(e["hasWindow"] for e in rows)})
        for action, asset in product(ACTIONS, ASSETS[bank_id]):
            subset = rows if action == "all" else [e for e in rows if e["action"] == action]
            by_state = {}
            for state in STATES:
                cell = stats([e for e in subset if e["state"] == state], asset)
                by_state[state] = cell
                groups.append(dict(window=window, action=action, asset=asset, state=state, **cell))
            contrasts.append(comparison(window, action, asset, by_state["tightening"], by_state["easing"]))
    changes = []
    for window in windows:
        rows = [e for e in events if e["window"] == window["id"]]
        for change in ("towardsTightening", "towardsEasing", "explicitness", "unchanged", "uncompared"):
            subset = [e for e in rows if e["change"] == change]
            for asset in ASSETS[bank_id]:
                changes.append(dict(window=window["id"], change=change, asset=asset, **stats(subset, asset)))
    bank = {"id": bank_id, "name": market["name"], "source": market["source"],
            "sourceLabel": market["sourceLabel"], "marketThrough": market["events"][-1]["date"],
            "selected": len(events), "matched": sum(e["hasWindow"] for e in events), "windows": windows,
            "assets": asset_list, "groups": groups, "contrasts": contrasts, "events": events, "changes": changes,
            "examples": [{"date": e["date"], "window": e["window"], "note": EXAMPLE_NOTES[bank_id][e["date"]]}
                         for e in events if e["date"] in EXAMPLE_NOTES[bank_id]
                         and e["window"] == ("conference" if bank_id == "ecb" and e["date"] in
                                              ("2011-03-03", "2013-07-04") else "statement")]}
    if bank_id == "fed":
        holds = [e for e in events if e["action"] == "hold"]
        near = [e for e in holds if e["values"]["MP1"] is not None and abs(e["values"]["MP1"]) <= 2]
        bank["nearPricedHolds"] = {
            "thresholdBp": 2, "actualHolds": len(holds), "matched": len(near),
            "missingCurrentSurprise": sum(e["values"]["MP1"] is None for e in holds),
            "definition": "Actual holds with an absolute current-meeting futures surprise (MP1) of at most 2 bp.",
            "groups": [dict(asset=asset, state=state, **stats([e for e in near if e["state"] == state], asset))
                       for asset, state in product(ASSETS[bank_id], STATES)],
        }
    bank["findings"] = findings(bank)
    return bank


def findings(bank):
    groups = {(g["window"], g["action"], g["asset"], g["state"]): g for g in bank["groups"]}

    def med(cell):
        value = cell["median"]
        if value is None:
            return "unavailable"
        digits = 2 if value == round(value, 2) else 3
        return f"{value:+.{digits}f} bp"

    if bank["id"] == "fed":
        hi, lo = [groups["statement", "hold", "UST2Y", s] for s in STATES[:2]]
        easing_years = sorted({r["date"][:4] for r in bank["events"] if r["state"] == "easing"})
        near = {g["state"]: g for g in bank["nearPricedHolds"]["groups"] if g["asset"] == "UST2Y"}
        a, b = near["tightening"], near["easing"]
        counts = Counter(e["change"] for e in bank["events"])
        return [
            f'Among rate holds the two-year Treasury median was {med(hi)} with explicit tightening guidance '
            f'({hi["n"]} releases) and {med(lo)} with easing guidance ({lo["n"]}). '
            f'The easing observations come from {", ".join(easing_years)}.',
            f'Restricting holds to an absolute current-meeting futures surprise of 2 bp or less gives '
            f'{med(a)} for tightening ({a["n"]}) and {med(b)} for easing ({b["n"]}). '
            'Even a well-anticipated current decision leaves room for news about later meetings.',
            f'Only {counts["towardsTightening"]} verified consecutive comparisons moved toward tightening '
            f'and {counts["towardsEasing"]} toward easing. January 2004 and December 2014 both signalled '
            'eventual tightening at a hold and had opposite two-year yield moves.',
        ]
    hi, lo = [groups["statement", "all", "DE2Y", s] for s in STATES[:2]]
    a, b = [groups["statement", "hold", "DE2Y", s] for s in STATES[:2]]
    ch, cl = [groups["conference", "all", "DE2Y", s] for s in STATES[:2]]
    return [
        f'In the decision-release window the median German two-year yield move was {med(hi)} with tightening '
        f'guidance ({hi["n"]} releases) and {med(lo)} with easing guidance ({lo["n"]}). '
        f'Among actual holds the medians were {med(a)} ({a["n"]}) and {med(b)} ({b["n"]}), respectively.',
        f'Conference-window medians were {med(ch)} for tightening ({ch["n"]}) and {med(cl)} for easing '
        f'({cl["n"]}). Conference observations can include an answer that qualifies the opening statement.',
        f'The ECB market series used here ends on {bank["marketThrough"]}. Later selected decisions retain '
        'their guidance labels and have an empty market value.',
    ]


def audit_workbook(bank, path):
    from openpyxl import load_workbook

    book = load_workbook(path, data_only=True, read_only=True)
    bank_id = bank["id"]
    lookup = {}
    sheet = book["Statements" if bank_id == "fed" else "EA-EMPD"]
    records = iter(sheet.values)
    headers = next(records)
    for record in records:
        if not record[0]:
            continue
        row = dict(zip(headers, record))
        if bank_id == "fed":
            window = "statement"
        else:
            window = {"GC_PR": "statement", "GC_PC": "conference"}.get(row["Event_type"])
        if window:
            key = record[0].date().isoformat(), window
            if key in lookup:
                raise ValueError(f"Duplicate {bank_id} workbook release {key}")
            lookup[key] = row
    for event in bank["events"]:
        row = lookup.get((event["date"], event["window"]))
        if event["hasWindow"] != (row is not None):
            raise ValueError(f"Market window availability differs for {event['date']}")
        for asset in bank["assets"]:
            key = asset["id"]
            raw = (row or {}).get("STOXX50E" if key == "STOXX50" else key)
            scale = 100 if bank_id == "fed" and asset["unit"] == "bp" else 1
            expected = round(raw * scale, 5) if raw is not None else None
            if event["values"][key] != expected:
                raise ValueError(f"Workbook differs for {bank_id} {event['date']} {key}")
    book.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbooks", nargs=2, type=Path, metavar=("USMPD", "EA_EMPD"))
    args = parser.parse_args()
    market_hash = digest(DATA / MARKET)
    if not args.workbooks and market_hash != AUDITED_EXTRACT:
        parser.error("This market extract has changed. Supply --workbooks to verify the new official releases.")
    markets = {b["id"]: b for b in json.loads((DATA / MARKET).read_text())["banks"]}
    notes = note_links()
    banks = [build_bank(json.loads((DATA / path).read_text()), markets[bank_id], notes)
             for bank_id, path in PANELS.items()]
    source_hashes = dict(AUDITED_WORKBOOKS)
    if args.workbooks:
        for bank, path in zip(banks, args.workbooks):
            audit_workbook(bank, path)
            source_hashes[bank["id"]] = digest(path)
    files = [MARKET, *PANELS.values(), "research-notes.json"]
    result = {"schemaVersion": 1, "title": "Forward guidance and market repricing",
              "method": METHOD, "banks": banks, "provenance": {
                  "inputs": {name: digest(DATA / name) for name in files},
                  "workbooks": {k: {"url": WORKBOOK_URLS[k], "sha256": v} for k, v in source_hashes.items()},
              }}
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=DATA, delete=False) as temp:
        json.dump(result, temp, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        temp.write("\n")
    output = Path(temp.name)
    output.chmod((DATA / MARKET).stat().st_mode & 0o777)
    output.replace(DATA / "guidance-study.json")
    for bank in banks:
        print(bank["name"], bank["matched"], "matched windows for", bank["selected"], "releases")


if __name__ == "__main__":
    main()
