"""Match one-year overnight indexed swap changes across two meeting windows.

Run after build-stance-cohorts.py:
    python scripts/build-stance-window-pairs.py USMPD.xlsx Dataset_EA-MPD.xlsx
The second argument must contain the extended ECB worksheet, EA-EMPD.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
from openpyxl import load_workbook

DATA = Path(__file__).resolve().parents[1] / "dist" / "data"
FED = "https://www.frbsf.org/wp-content/uploads/USMPD.xlsx"
ECB = "https://www.ecb.europa.eu/pub/pdf/other/Dataset_EA-MPD.xlsx"
SHEETS = {"Statements": "release", "Press Conferences": "conference", "Monetary Events": "combined"}
EVENTS = {"GC_PR": "release", "GC_PC": "conference", "GC_ME": "combined"}

def values(sheet):
    rows = iter(sheet.values)
    headers = next(rows)
    for row in rows:
        yield dict(zip(headers, row))

def add(windows, date, stage, raw, scale):
    if isinstance(raw, (int, float)) and math.isfinite(raw):
        stages = windows.setdefault(date, {})
        if stage in stages:
            raise ValueError(f"Ambiguous event window for {date}, {stage}")
        stages[stage] = round(raw * scale, 7)

def extract(path, bank):
    book = load_workbook(path, read_only=True, data_only=True)
    windows = {}
    try:
        if bank == "fed":
            for sheet, stage in SHEETS.items():
                for row in values(book[sheet]):
                    if row["Date"] and row.get("Unscheduled", 0) == 0:
                        add(windows, row["Date"].date().isoformat(), stage, row["OIS1Y"], 100)
        else:
            for row in values(book["EA-EMPD"]):
                stage = EVENTS.get(row["Event_type"])
                if stage:
                    add(windows, row["Date_time"].date().isoformat(), stage, row["OIS_1Y"], 1)
    finally:
        book.close()
    return windows

def build(fed_file, ecb_file):
    panels = json.loads((DATA / "stance-cohorts.json").read_bytes())
    result = []
    for bank in panels["banks"]:
        key = bank["id"]
        if key not in {"fed", "ecb"}:
            continue
        windows = extract(fed_file if key == "fed" else ecb_file, key)
        records = []
        for meeting in bank["records"]:
            day = meeting["date"]
            w = windows.get(day, {})
            if not {"conference", "release"} <= w.keys():
                continue
            if key == "ecb" and meeting["sourceType"] != "conference":
                continue
            first, second = w["release"], w["conference"]
            records.append(dict(date=day, leader=meeting["leader"], cycle=meeting["cycle"],
                releaseBp=first, conferenceBp=second, totalBp=round(first + second, 7),
                combinedWindowBp=w.get("combined"), score=meeting["score"], sourceUrl=meeting["url"],
                compareUrl="stance-history.html?bank=" + key + "&date=" + day))
        result.append(dict(id=key, currency="USD" if key == "fed" else "EUR",
                           records=records, thresholds=[0.5, 1, 2]))
    return {"method": "Changes in local-currency one-year OIS, in basis points. Both the decision and conference require a price. The Fed sample uses scheduled decisions. ECB dates require an identified press conference. A full reversal requires both legs to exceed the selected band with opposite signs and the second leg larger in magnitude. The arithmetic sum can differ from the database’s continuous meeting window if the leg boundaries leave a gap. Conference windows last longer, and other news can affect prices.",
            "sources":[{"label":"San Francisco Fed · USMPD","url":FED,"sha256":hashlib.sha256(fed_file.read_bytes()).hexdigest()},
                       {"label":"European Central Bank · EA-EMPD","url":ECB,"sha256":hashlib.sha256(ecb_file.read_bytes()).hexdigest()}],"banks":result}

if __name__ == "__main__":
    parse = argparse.ArgumentParser(description=__doc__)
    parse.add_argument("fed_workbook", type=Path)
    parse.add_argument("ecb_workbook", type=Path)
    args = parse.parse_args()
    out = build(args.fed_workbook, args.ecb_workbook)
    (DATA / "stance-window-pairs.json").write_text(json.dumps(out,ensure_ascii=False,separators=(",",":"),allow_nan=False)+"\n")
    for bank in out["banks"]:
        both=[r for r in bank["records"] if min(abs(r["releaseBp"]),abs(r["conferenceBp"]))>1]
        opposite=[r for r in both if r["releaseBp"] * r["conferenceBp"]<0]
        full=[r for r in opposite if abs(r["conferenceBp"])>abs(r["releaseBp"])]
        print(bank["id"],len(bank["records"]),len(both),len(opposite),len(full))
