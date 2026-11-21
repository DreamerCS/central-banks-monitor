"""Build the observable event frame, source-check ledger and annual coverage diagnostics."""
import argparse
import csv
import hashlib
import io
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "dist" / "data"
OUTLETS = ("Bloomberg", "Financial Times", "Reuters", "The Wall Street Journal")
FRAME_FIELDS = ("eventId", "bank", "date", "type", "speaker", "title", "officialSource",
                "actionBp", "priorMoveBp", "pricingGapBp", "verifiedArticles", "publishersWithNews",
                "release2yBp", "release2yGroupEligible")
CELL_FIELDS = ("bank", "date", "publisher", "verifiedArticles", "candidateCount", "originalHostCount",
               "reviewStatus", "checkedOn", "method", "evidenceUrl")


def read_json(name):
    return json.loads((DATA / name).read_text())


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def export_csv(rows, fields):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fields, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode("utf-8-sig")


def event_frame():
    events = {}
    cohorts = read_json("stance-cohorts.json")["banks"]
    for bank in cohorts:
        key = bank["id"]
        release = {r["date"]: r for r in read_json(key+"-cross-asset-events.json")["records"]
                   if r["stage"] == "release" and r["type"] == "decision"}
        for r in bank["records"]:
            day = r["date"]
            event_id = f"{key}-decision-{day}"
            market = release.get(day, {})
            events[event_id] = dict(eventId=event_id, bank=key, date=day, type="decision",
                                    speaker=r["leader"], title=r["title"], officialSource=r.get("releaseUrl") or r["url"],
                                    actionBp=r.get("actionBp"), priorMoveBp=r.get("priorMoveBp"),
                                    pricingGapBp=r.get("pricingGapBp"), release2yBp=market.get("values",{}).get("yield2y"),
                                    release2yGroupEligible=bool(market.get("groupEligible")))
    for r in read_json("fed-leader-speeches.json")["records"]:
        url = r["sourceUrl"]
        ident = "fed-speech-" + hashlib.sha256(url.encode()).hexdigest()[:16]
        events[ident] = dict(eventId=ident, bank="fed", date=r["date"], type="speech", title=r["title"],
                             speaker=r["speaker"], officialSource=url)
    for r in read_csv(DATA / "ecb-news-speech-frame.csv"):
        if r["president_speaks"].lower() not in {"true", "1", "yes"}:
            continue
        ident = "ecb-speech-" + r["event_id"]
        events[ident] = dict(eventId=ident, bank="ecb", date=r["date"], type="speech", title=r["title"],
                             speaker=r["speaker"], officialSource=r["url"])
    return events


def link_news(events, news):
    by_day = defaultdict(list)
    for event in events.values():
        by_day[event["bank"], event["date"], event["type"]].append(event)
    linked = defaultdict(Counter)
    unmatched = defaultdict(list)
    for row in news:
        options = by_day[row["bank"], row["date"], row["type"]]
        if row["type"] == "speech":
            surname = row["speaker"].casefold()
            options = [r for r in options if surname in r["speaker"].casefold()]
            path = urlsplit(row.get("officialSource") or "").path
            exact = [r for r in options if path and urlsplit(r["officialSource"]).path == path]
            if exact:
                options = exact
        if len(options) == 1:
            linked[options[0]["eventId"]][row["publisher"]] += 1
        else:
            unmatched[row["bank"]].append(row["id"])
    for event in events.values():
        publishers = linked[event["eventId"]]
        event.update(verifiedArticles=sum(publishers.values()), publishersWithNews=len(publishers))
    return linked, unmatched


def stats(values):
    return {"n": len(values), "medianAbsBp": round(median(values), 4) if values else None}


def selection(bank, meetings):
    actions = defaultdict(list)
    for event in meetings:
        bp = event["actionBp"]
        action = "unclassified" if bp is None else ("hike" if bp > 0 else "cut" if bp < 0 else "hold")
        actions[action].append(event)
    covered, uncovered = [], []
    for r in meetings:
        if r["date"][:4] > "2025" or not r["release2yGroupEligible"] or r["release2yBp"] is None:
            continue
        (covered if r["verifiedArticles"] else uncovered).append(abs(r["release2yBp"]))
    return {"byAction": [{"action": key, "covered": sum(r["verifiedArticles"] > 0 for r in group), "total": len(group)}
                         for key, group in sorted(actions.items())],
            "yieldStudy": {"instrument": "2-year US Treasury yield" if bank == "fed" else "2-year German sovereign yield",
                           "period": "2000–2025", "window": "statement −10 to +20 minutes" if bank == "fed" else "ECB decision release, Frankfurt quote windows",
                           "all": stats(covered+uncovered), "covered": stats(covered), "uncovered": stats(uncovered)}}


def summarise(bank, rows, unmatched, last_year):
    speech_scope = ("Published speeches from the sitting Fed Chair catalogue, counted by original document."
                    if bank == "fed" else "Published speeches by the sitting ECB President, including joint speeches, counted by original document.")
    scope = speech_scope + " Rate decisions use the dated policy chronology. Pricing requires a comparable action-minus-prior figure."
    years = []
    for year in range(2000, last_year+1):
        rs = [r for r in rows if int(r["date"][:4]) == year]
        m = [r for r in rs if r["type"] == "decision"]
        s = [r for r in rs if r["type"] == "speech"]
        priced = [r for r in m if r["pricingGapBp"] is not None]
        years.append(dict(year=year, decisionTotal=len(m), decisionWithNews=sum(bool(r["verifiedArticles"]) for r in m),
                          speechTotal=len(s), speechWithNews=sum(bool(r["verifiedArticles"]) for r in s),
                          multiDecision=sum(r["publishersWithNews"] >= 2 for r in m), pricedDecision=len(priced),
                          matchedPricedDecision=sum(bool(r["verifiedArticles"]) for r in priced)))
    return dict(scope=scope, years=years, unmatchedNewsCount=len(unmatched), unmatchedNewsIds=unmatched,
                latestSpeech=max(r["date"] for r in rows if r["type"]=="speech"),
                latestDecision=max(r["date"] for r in rows if r["type"]=="decision"),
                selection=selection(bank, [r for r in rows if r["type"]=="decision"]))


def cells(events, linked):
    counts = {(r["bank"],r["date"],r["publisher"]):r for r in read_csv(DATA / "news-candidate-counts.csv")}
    log_rows = json.loads((ROOT / "scripts" / "news-search-log.json").read_text())
    searches = {(r["bank"],r["date"],r["publisher"]):r for r in log_rows}
    if len(searches) != len(log_rows):
        raise ValueError("Duplicate outlet search")
    rows = []
    for r in events:
        if r["type"] != "decision":
            continue
        for publisher in OUTLETS:
            key = r["bank"],r["date"],publisher
            found = linked[r["eventId"]][publisher]
            hits = counts.get(key)
            audit = searches.get(key,{})
            n = int(hits["candidateCount"]) if hits else None
            original = int(hits["originalHostCount"]) if hits else None
            if hits and not 0 <= original <= n:
                raise ValueError(f"Inconsistent candidates: {key}")
            if found:
                status = "Verified event-linked coverage"
            elif audit:
                status = "Searched; original event coverage unresolved"
            elif hits is None:
                status = "Outside the recorded candidate screen"
            elif n:
                status = "Candidate leads await original-source review"
            else:
                status = "No candidate under screen; publisher search not logged"
            rows.append(dict(bank=key[0], date=key[1], publisher=publisher, verifiedArticles=found,
                             candidateCount=n, originalHostCount=original, reviewStatus=status,
                             checkedOn=audit.get("checkedOn"), method=audit.get("method"), evidenceUrl=audit.get("evidenceUrl")))
    valid = {(r["bank"],r["date"],r["publisher"]) for r in rows}
    if (set(searches) | set(counts)) - valid:
        raise ValueError("Source-search dates differ from the decision frame")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    source = read_json("news-framing.json")
    frame = event_frame()
    linked, unmatched = link_news(frame, source["records"])
    rows = sorted(frame.values(), key=lambda r:(r["bank"],r["date"],r["type"],r["eventId"]))
    cell_rows = cells(rows, linked)
    audit = {"asOf": source["asOf"], "banks": {}, "method": [
        "The frame starts from documented policy-rate decision dates and published chair or president speeches. The 2026 observation period ends at the archive cutoff. Other board members, minutes and separate press-conference stages are outside these denominators.",
        "Standalone emergency programmes fall outside the rate-decision frame, including the ECB’s 18 March 2020 PEPP launch. The frame includes the Fed’s seven intermeeting target decisions during this period.",
        "Each verified headline is linked to an identifiable event. Each meeting counts once regardless of publisher or article count. Missing coverage means that this archive has yet to verify a report.",
        "The source ledger crosses each decision with the four eligible newsrooms. Candidate counts use bank-tagged, decision-related leads near the recorded date. A recorded date may be an index observation. A zero does not establish absence of reporting.",
        "The documented pilot searches the first regular 2020 and 2022 meetings of each bank at Reuters, Bloomberg and the Financial Times. Coverage elsewhere may have been found by other search methods.",
        "The two-year yield comparison uses observed, aggregation-eligible release windows for full years through 2025. The covered and uncovered groups can differ in policy action and economic conditions. The comparison describes selection in this sample.",
        "Fed action uses the target or upper bound where comparable. ECB action uses the deposit facility rate. An unchanged deposit rate can accompany changes to asset purchases or other instruments."
    ]}
    for bank in ("fed","ecb"):
        audit["banks"][bank] = summarise(bank,[r for r in rows if r["bank"]==bank],unmatched[bank],int(source["asOf"][:4]))
    outputs = {"news-coverage-frame.csv": export_csv(rows, FRAME_FIELDS),
               "news-source-checks.csv": export_csv(cell_rows, CELL_FIELDS),
               "news-coverage-audit.json": (json.dumps(audit, ensure_ascii=False, indent=2)+"\n").encode()}
    for name, value in outputs.items():
        dest = DATA / name
        if args.check:
            if not dest.exists() or dest.read_bytes()!=value: raise ValueError("Refresh "+name)
        else:
            dest.write_bytes(value)
    print(f"{len(rows)} official events; {len(cell_rows)} meeting-outlet cells; {sum(map(len,unmatched.values()))} unmatched readings")


if __name__ == "__main__":
    main()
