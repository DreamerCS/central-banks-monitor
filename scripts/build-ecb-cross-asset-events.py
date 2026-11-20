"""Rebuild ECB cross-asset event windows from the ECB EA-EMPD workbook.

python scripts/build-ecb-cross-asset-events.py Dataset_EA-MPD.xlsx
Requires openpyxl and the site's existing ECB stance, speech and leadership data.
"""
import argparse
from bisect import bisect_left, bisect_right
from collections import Counter
import csv
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = "https://www.ecb.europa.eu/pub/pdf/other/Dataset_EA-MPD.xlsx"
PAPER = "https://www.ecb.europa.eu/pub/pdf/scpwps/ecb.wp3157~f5789c7b8a.en.pdf"
ZONE = "Europe/Berlin"
ASSETS = [
    ("ois1m", "OIS_1M", "1-month euro OIS", "Rates", "bp", "Change in the one-month euro overnight indexed swap rate."),
    ("ois3m", "OIS_3M", "3-month euro OIS", "Rates", "bp", "Change in the three-month euro overnight indexed swap rate."),
    ("ois6m", "OIS_6M", "6-month euro OIS", "Rates", "bp", "Change in the six-month euro overnight indexed swap rate."),
    ("ois1y", "OIS_1Y", "1-year euro OIS", "Rates", "bp", "Change in the one-year euro overnight indexed swap rate."),
    ("ois2y", "OIS_2Y", "2-year euro OIS", "Rates", "bp", "Change in the two-year euro overnight indexed swap rate."),
    ("ois5y", "OIS_5Y", "5-year euro OIS", "Rates", "bp", "Change in the five-year euro overnight indexed swap rate."),
    ("ois10y", "OIS_10Y", "10-year euro OIS", "Rates", "bp", "Change in the ten-year euro overnight indexed swap rate."),
    ("yield2y", "DE2Y", "German 2-year yield", "Rates", "bp", "A positive change means the German two-year sovereign yield rose."),
    ("yield5y", "DE5Y", "German 5-year yield", "Rates", "bp", "A positive change means the German five-year sovereign yield rose."),
    ("yield10y", "DE10Y", "German 10-year yield", "Rates", "bp", "A positive change means the German ten-year sovereign yield rose."),
    ("slope", ("DE10Y","DE2Y"), "German 2s10s", "Rates", "bp", "Ten-year minus two-year German yield changes. A positive value means the curve steepened."),
    ("italy10y", "IT10Y", "Italian 10-year yield", "Rates", "bp", "Change in the Italian ten-year sovereign yield."),
    ("france10y", "FR10Y", "French 10-year yield", "Rates", "bp", "Change in the French ten-year sovereign yield."),
    ("spain10y", "ES10Y", "Spanish 10-year yield", "Rates", "bp", "Change in the Spanish ten-year sovereign yield."),
    ("italySpread10y", ("IT10Y","DE10Y"), "Italy–Germany 10-year spread", "Rates", "bp", "Italian minus German ten-year yield changes. A positive value means the spread widened."),
    ("franceSpread10y", ("FR10Y","DE10Y"), "France–Germany 10-year spread", "Rates", "bp", "French minus German ten-year yield changes. A positive value means the spread widened."),
    ("spainSpread10y", ("ES10Y","DE10Y"), "Spain–Germany 10-year spread", "Rates", "bp", "Spanish minus German ten-year yield changes. A positive value means the spread widened."),
    ("equity", "STOXX50E", "EURO STOXX 50", "Equities", "%", "Percentage change in the euro-area blue-chip equity index."),
    ("bankEquity", "SX7E", "EURO STOXX Banks", "Equities", "%", "Percentage change in the euro-area bank equity index."),
    ("eurusd", "EURUSD", "EUR/USD", "FX", "%", "US dollars per euro. A positive change indicates euro appreciation."),
    ("eurgbp", "EURGBP", "EUR/GBP", "FX", "%", "Pounds sterling per euro. A positive change indicates euro appreciation."),
    ("eurjpy", "EURJPY", "EUR/JPY", "FX", "%", "Japanese yen per euro. A positive change indicates euro appreciation."),
]
STAGES = {
    "release": {"label": "Decision release", "window": "Median quotes before and after the announcement in Frankfurt time."},
    "conference": {"label": "Press conference", "window": "Median quotes before and after the conference in Frankfurt time."},
    "combined": {"label": "Whole meeting", "window": "From the median quote before the release to the median quote after the press conference."},
    "speech": {"label": "Speech or testimony", "window": "Median quote 20–10 minutes before the recorded start, compared with 40–50 minutes after the start."},
}
WINDOWS = {
    "release": ("13:25–13:35 → 14:00–14:10", "13:55–14:05 → 14:30–14:40"),
    "conference": ("14:15–14:25 → 15:40–15:50", "14:30–14:40 → 15:55–16:05"),
    "combined": ("13:25–13:35 → 15:40–15:50", "13:55–14:05 → 15:55–16:05"),
}
STAGE_CODES = {"GC_PR":"release", "GC_PC":"conference", "GC_ME":"combined", "EB":"speech", "P":"speech"}


def series_spec():
    return [dict(id=identifier, label=label, unit=unit, group=group, description=description)
            for identifier, _, label, group, unit, description in ASSETS]


def measures(row):
    result = {}
    for identifier, columns, *_ in ASSETS:
        keys = columns if isinstance(columns, tuple) else (columns,)
        values = [row[k] for k in keys]
        if any(v is None for v in values):
            continue
        if not all(type(v) in (int, float) and math.isfinite(v) for v in values):
            raise ValueError(f"Unexpected market quote in {keys} at {row['Date_time']}")
        change = values[0] - values[1] if len(values) == 2 else values[0]
        result[identifier] = round(change, 6) or 0
    return result


def speech_quote_window(stamp):
    def clock(minutes):
        t = stamp + timedelta(minutes=minutes)
        return t.strftime("%H:%M") if t.date() == stamp.date() else t.strftime("%d %b %H:%M")
    return f"{clock(-20)}–{clock(-10)} → {clock(40)}–{clock(50)} Frankfurt time"


def build(bookfile, data):
    meetings = {r["date"]:r for r in json.loads((data/"ecb-stance-history.json").read_text())["records"]}
    leaders = json.loads((data/"ecb-leadership.json").read_text())["profiles"]
    with (data/"ecb-speech-stance.csv").open(newline="", encoding="utf8") as f:
        speech_texts = {r["speech_id"]:r for r in csv.DictReader(f)}
    book = load_workbook(bookfile, data_only=True, read_only=True)
    try:
        notes = "\n".join(str(value) for row in book["Notes"].values for value in row if value is not None)
        if "Euro Area Extended Monetary Policy" not in notes or "positive change indicates an appreciation of the euro" not in notes:
            raise ValueError("Unexpected workbook methodology. Review FX direction and definitions.")
        table = book["EA-EMPD"].values
        header = next(table)
        rows = [dict(zip(header, row)) for row in table if isinstance(row[0],datetime)
                and 2000 <= row[0].year <= 2026]
    finally:
        book.close()
    times = sorted(r["Date_time"] for r in rows if r["Event_type"] in {"P","EB"})
    meeting_days = set(meetings)
    matched_text_ids = set()
    events = []
    for row in rows:
        stage = STAGE_CODES[row["Event_type"]]
        stamp = row["Date_time"]
        day = stamp.date().isoformat()
        values = measures(row)
        flags = []
        event = dict(date=day, time=stamp.strftime("%H:%M"), timeZone=ZONE, stage=stage,
                     type="decision" if stage in {"release","combined"} else stage,
                     groupEligible=False, values=values)
        if stage == "speech":
            speaker = " ".join(row["Speaker"].split())
            title = " ".join(row["Title"].split())
            identity = "|".join((stamp.isoformat(timespec="minutes"),speaker,title))
            token = hashlib.sha256(identity.encode()).hexdigest()[:10]
            event.update(id="ecb-speech-"+token, speaker=speaker, title=title, sourceUrl=WORKBOOK,
                         leader=next(p["name"] for p in leaders if p["start"] <= day and (not p["end"] or day<=p["end"])),
                         window=speech_quote_window(stamp))
            if row["Non_regular_trading_day"] or row["Outside_regular_trading_hours"]:
                flags.append("Outside regular trading hours or on a non-trading day")
            # Window spans 70 minutes from the earliest before quote to the latest after quote.
            overlap = bisect_left(times, stamp + timedelta(minutes=70))-bisect_right(times, stamp - timedelta(minutes=70))
            if overlap > 1:
                flags.append("Overlapping ECB speech window")
            if day in meeting_days:
                flags.append("ECB decision on the same day")
            text = speech_texts.get(token)
            if text:
                if text["event_time"] != stamp.isoformat(timespec="minutes") or text["title"] != title or text["speaker"] != speaker:
                    raise ValueError("Ambiguous speech identity "+token)
                matched_text_ids.add(token)
                event["textMatched"] = True
                if text["text_score"] != "":
                    event["score"] = int(text["text_score"])
                if text["transcript"]:
                    event.update(documentUrl=text["transcript"],sourceUrl=text["transcript"])
        else:
            meeting = meetings.get(day)
            if not meeting:
                raise ValueError("Update the decision archive for "+day)
            # The market workbook also contains conference-time prices for release-only meetings.
            if stage in {"conference","combined"} and meeting["sourceType"] != "conference":
                continue
            release_url = meeting["releaseUrl"]
            document = meeting["sourceUrl"] if stage == "conference" else release_url
            event.update(id=f"ecb-{stage}-{day}", title="ECB "+STAGES[stage]["label"].lower(),
                         leader=meeting["leader"],documentUrl=document,sourceUrl=document,
                         window=WINDOWS[stage][day >= "2022-07-01"]+" Frankfurt time")
            if stage == "combined":
                event["conferenceUrl"] = meeting["sourceUrl"]
            elif stage == "conference" and meeting["score"] is not None:
                event["score"] = meeting["score"]
            elif stage == "release":
                release = meeting["releaseReading"] if meeting["sourceType"] == "conference" else meeting
                if release["score"] is not None:
                    event["score"] = release["score"]
            modern = day >= "2022-07-01"
            expected_time = (("14:45" if modern else "14:30") if stage == "conference" else ("14:15" if modern else "13:45"))
            if event["time"] != expected_time:
                event["window"] = "Exceptional announcement time. The workbook reports a window change without date-specific quote boundaries."
                flags.append("Non-standard event time")
            if row["Non_regular_trading_day"] or row["Outside_regular_trading_hours"]:
                flags.append("Outside regular trading hours or on a non-trading day")
        if not values:
            flags.append("No reported change in the selected instruments")
        event["groupEligible"] = not flags
        if flags:
            event["flags"] = flags
        events.append(event)
    if matched_text_ids != speech_texts.keys():
        raise ValueError("Speech-archive dates differ from this workbook. Rebuild the historical speech table.")
    events.sort(key=lambda r: (r["date"],r["time"],["release","combined","conference","speech"].index(r["stage"]),r["id"]))
    if len({r["id"] for r in events}) != len(events):
        raise ValueError("Non-unique event identity")
    return dict(bank="ecb", timezone=ZONE, assets=series_spec(), stages=STAGES,
                source=dict(label="ECB · Euro Area Extended Monetary Policy Event-Study Database",
                            url=WORKBOOK, methodologyUrl=PAPER,sha256=hashlib.sha256(bookfile.read_bytes()).hexdigest()),
                coverage=dict(fromDate=events[0]["date"],toDate=events[-1]["date"],records=len(events),
                              byStage=dict(Counter(r["stage"] for r in events)),
                              eligibleByStage=dict(Counter(r["stage"] for r in events if r["groupEligible"]))),
                method=[
                    "Asset changes compare median quotes in the stated before and after windows. The ECB uses an assumed 30-minute speech and ten-minute quote intervals on each side. Times are local to Frankfurt.",
                    "Rates and spreads are in basis points. Equities and currencies show signed percentage changes. A rise in EUR/USD, EUR/JPY or EUR/GBP means the euro appreciated. Missing quotes are omitted. An observed zero remains zero.",
                    "Conference and whole-meeting rows require an ECB press conference linked in the historical archive. The continuous whole-meeting figure is observed separately. Combining it with the release and conference as another independent event double-counts the meeting.",
                    "Grouped speech results exclude non-trading days, events outside regular trading hours, overlapping ECB speech windows and decision dates. Eligible windows can still include other news. Each asset uses its own observed-price denominator.",
                    "A score follows the statement, the conference, or the identified speaker separately. The whole meeting has no single language score. The publisher's timing and price data also cover appearances without a reviewed transcript.",
                ],records=events)


def write_archive(result, output):
    """Keep meeting observations in the index, with dated speech files alongside."""
    def write(path, content):
        path.write_text(json.dumps(content, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
    meetings = []
    batches = {}
    for event in result["records"]:
        if event["stage"] == "speech":
            first = int(event["date"][:4]) // 5 * 5
            name = f"ecb-cross-asset-speeches-{first}-{first + 4}"
            batches.setdefault(name, []).append(event)
        else:
            meetings.append(event)
    for name, events in batches.items():
        write(output.parent / (name + ".json"), {"records": events})
    write(output, {**result, "records": meetings, "parts": sorted(batches)})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook",type=Path)
    parser.add_argument("--data",type=Path,default=ROOT/"dist/data")
    parser.add_argument("--output",type=Path,default=ROOT/"dist/data/ecb-cross-asset-events.json")
    args = parser.parse_args()
    result = build(args.workbook,args.data)
    write_archive(result, args.output)
    print(result["coverage"])
