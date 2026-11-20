"""Build ECB communication readings, keeping each document aligned with its own price window.

python scripts/build-ecb-stance-history.py --cache /path/to/ECB-pages --workbook Dataset_EA-MPD.xlsx --deposit-csv DFR.csv
The official English release and conference URLs are pinned in ecb-stance-sources.json.
Missing HTML is downloaded and cached. Use --offline to require a populated cache.
The ECB Data Portal series FM.D.U2.EUR.4F.KR.DFR.LEV supplies daily deposit rates.
"""
import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

from lxml import html
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "dist/data"
MARKET = "https://www.ecb.europa.eu/pub/pdf/other/Dataset_EA-MPD.xlsx"
DEPOSIT = "https://data-api.ecb.europa.eu/service/data/FM/D.U2.EUR.4F.KR.DFR.LEV?startPeriod=1999-12-01&format=csvdata"
ARCHIVE = "https://www.ecb.europa.eu/press/govcdec/mopo/html/index.en.html"
CONFERENCES = "https://www.ecb.europa.eu/press/press_conference/monetary-policy-statement/html/index.en.html"
RULES = [
    ("further-increase", 2, r"(?:intend to raise|expects? to raise|further normalisation of interest rates will be appropriate|interest rates will still have to rise significantly)", "The Council set out a further tightening path in its own assessment."),
    ("conditional-withdrawal", 1, r"(?:progressive|further) withdrawal of monetary accommodation (?:will|would|may|might) (?:remain|be) (?:warranted|necessary|appropriate)", "Further withdrawal of accommodation depended on confirmation of the baseline."),
    ("conditional-cut", -1, r"(?:appropriate to reduce the current level of monetary policy restriction|not exclude further monetary policy easing)", "The Council identified circumstances under which it could ease further."),
    ("lower-option", -1, r"(?:remain|stay|be) at (?:their |the )?(?:present|current) or lower levels", "The announced rate path explicitly allowed a lower rate as well as a hold."),
    ("low-rate-promise", -2, r"(?:remain|stay) at (?:their |the )?(?:present|current) levels until (?:it sees|we see|we have seen) inflation", "The Council committed to retaining the prevailing low rates until an inflation threshold was reached."),
    ("dated-hold", 0, r"(?:remain|stay) at (?:their |the )?(?:present|current) levels (?:at least through|for an extended period|at least until)", "The Council gave an explicit horizon for holding its policy rates."),
    ("plateau", 0, r"(?:interest rates|rates) have reached levels that, maintained for a sufficiently long duration", "The Council signalled a rate plateau conditional on the inflation outlook."),
    ("vigilance", 1, r"strong vigilance (?:is|remains|is of)", "Trichet used the Council’s strong-vigilance formulation, a conditional tightening signal without a commitment to a meeting or an increment."),
]
# Audited replies in early press conferences, before the Council adopted formal forward guidance.
# Each short quotation is validated against the source when the series is rebuilt.
EARLY_REPLIES = {
    "2004-05-06": (0, "we keep all our options open and we have no bias", "Asked about the future policy stance, Trichet explained that the Council had no preferred direction."),
    "2004-06-03": (0, "we have no bias and that we are vigilant", "Trichet distinguished attention to inflation risks from the Council’s expressly neutral policy bias."),
    "2004-07-01": (0, "we have no bias, full stop", "In his reply about policy direction, Trichet explicitly ruled out a directional bias."),
    "2008-07-03": (0, "I said already that we have no bias", "After raising rates, Trichet declined to signal a continuing upward path and stated that the Council had no directional bias."),
    "2008-08-07": (0, "as candidly as possible, we have no bias", "Discussing the current policy stance, Trichet described an explicitly balanced position."),
    "2008-09-04": (0, "to the market, I repeat: we have no bias", "Asked about markets expecting unchanged rates that year, Trichet described a neutral bias without endorsing a particular path."),
    "2009-12-03": (0, "we are neutral and the present rates are appropriate", "Explaining the indexation of a refinancing operation, Trichet said that the rate signal he wanted markets to receive was neutral."),
    "2000-04-13": (1, "the direction in which the next move will go", "Asked why he had delayed a further increase, Duisenberg referred to the two preceding hikes and signalled the same direction without giving a date."),
    "2001-10-11": (0, 'we prefer to "keep our powder dry"', "Duisenberg said that uncertainty and limited room for manoeuvre favoured waiting, even if some room existed."),
    "2002-11-07": (-1, "the size nor the moment of a rate cut, I say again, sometime in the future", "Explaining why the Council had disclosed its discussion of a cut, Duisenberg referred to a possible future cut while leaving its size and timing open."),
    "2003-04-03": (0, "on the monetary policy stance, but without a bias in any direction", "Asked whether the Council had considered a cut, Duisenberg explicitly described its discussion as having no directional bias."),
}
PRE = {
    "2015-12-03": (-10, "Pre-meeting briefing recorded in the December Governing Council account", "https://www.ecb.europa.eu/press/accounts/2016/html/mg160114.en.html", "The ECB reported that the EONIA forward curve fully priced a 10 bp deposit-rate cut at this meeting and a further 10 bp by September 2016. The exact quote time is unavailable."),
    "2024-12-12": (-25, "11 December 2024, end of ECB bulletin review period", "https://www.ecb.europa.eu/press/economic-bulletin/html/eb202408.en.html", "The ECB reported that market pricing on the preceding day fully incorporated a 25 bp December cut. The later bulletin identifies the date and the meeting."),
    "2025-03-06": (-25, "5 March 2025, end of ECB bulletin review period", "https://www.ecb.europa.eu/press/economic-bulletin/html/eb202502.en.html", "The ECB reported that the forward curve fully priced a 25 bp cut in March. The end-of-period observation precedes the meeting, while the bulletin was published afterwards."),
    "2023-07-27": (25, "Pre-meeting market briefing summarised in the Governing Council account", "https://www.ecb.europa.eu/press/accounts/2023/html/ecb.mg230831~b04764f45f.en.html", "The ECB recorded market pricing for a 25 bp increase at this meeting and a 56% probability of a further 25 bp increase in September. The account was published on 31 August. The exact quote time is unavailable."),
    "2024-09-12": (-25, "11 September 2024, end of ECB bulletin review period", "https://www.ecb.europa.eu/press/economic-bulletin/html/eb202406.en.html", "The ECB reported that the €STR forward curve fully priced a 25 bp cut at the September meeting. The pricing date precedes the announcement. The bulletin reporting it was published afterwards."),
}
WINDOWS = {
    "release": ("13:25–13:35 to 14:00–14:10", "13:55–14:05 to 14:30–14:40"),
    "conference": ("14:15–14:25 to 15:40–15:50", "14:30–14:40 to 15:55–16:05"),
}
FORMAT = {"release": "decision-release", "conference": "press-conference"}
def official_text(path, kind):
    doc = html.fromstring(path.read_bytes().decode("utf-8", errors="replace"))
    parts = []
    for p in doc.xpath("//main//*[self::p or self::li[not(.//p)] or self::h2 or self::h3]"):
        t = " ".join(p.text_content().replace("’", "'").split())
        if kind == "conference" and len(parts) > 3:
            if re.search(r"(?:now|glad|happy|ready|available|at your disposal|pleased).{0,65}(?:take|answer|welcome|hear|open|disposal|your|any) (?:your |any )?questions", t, re.I):
                break
            if re.match(r"(?:Question\s*[:(]|My first question|Transcript of the questions|Questions and answers|Q\s*:|\* \* \*)", t, re.I):
                break
        if t:
            parts.extend(re.split(r"(?<=[.!?])\s+", t))
    if len(parts) < 2:
        raise ValueError(f"Cannot extract official text from {path}")
    return parts

def excerpt(sentence, match):
    words = list(re.finditer(r"\S+", sentence))
    if len(words) <= 23:
        return sentence.strip()
    anchor = next((i for i, m in enumerate(words) if m.end() > match.start()), 0)
    start = max(0, min(anchor - 3, len(words) - 23))
    end = start + 23
    return ("…" if start else "") + sentence[words[start].start():words[end-1].end()].strip() + ("…" if end < len(words) else "")

def reading(path, kind, day, reviewed):
    if kind=="conference" and day in EARLY_REPLIES:
        level, evidence, reason = EARLY_REPLIES[day]
        doc=html.fromstring(path.read_bytes().decode("utf-8", errors="replace"))
        contents=" ".join(doc.xpath("//main")[0].text_content().replace("’","'").split())
        assert evidence in contents, day
        return level, "reviewed-early-reply", evidence, reason, "Official Q&A wording"
    sentences = official_text(path, kind)
    for key, level, pattern, reason in RULES:
        # The shorthand is an historically specific signal. Restrict to its documented usage.
        if key == "vigilance" and not ("2005-01-01" <= day <= "2011-10-31"):
            continue
        for s in sentences:
            m = re.search(pattern, s, re.I)
            if m:
                return level, key, excerpt(s, m), reason, "Official wording"
    if reviewed and reviewed["state"] != "unclear":
        level = {"easing": -1, "balanced": 0, "tightening": 1}[reviewed["state"]]
        return level, "reviewed-" + reviewed["state"], reviewed["evidence"], reviewed["analysis"], "Editorial paraphrase of official document"
    if reviewed:
        return None, "unscored", reviewed["evidence"], reviewed["analysis"], "Editorial paraphrase of official document"
    for pattern, reason in [(r"not pre.commit", "The Council explicitly kept its future rate path open."), (r"(?:stance of monetary policy|monetary policy stance|level of (?:key )?(?:ECB )?interest rates).{0,35}(?:appropriate|unchanged)", "The Council assessed the prevailing stance. This passage gives no prospective direction or holding horizon."), (r"risks? to price stability.{0,35}(?:upside|downside)|upside risks? to price stability", "The inflation risk assessment alone supplies no preferred direction for the next rate decision.")]:
        for s in sentences:
            m = re.search(pattern, s, re.I)
            if m:
                return None, "unscored", excerpt(s,m), reason, "Official wording"
    return None, "unscored", "", "The review found no qualifying guidance on the future rate path in this text.", "No qualifying passage"

def numeric(x):
    return round(x, 4) if isinstance(x, (int, float)) else None

def prices(path):
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = iter(wb["EA-EMPD"].values)
    headers = next(ws)
    out = {}
    for raw in ws:
        r = dict(zip(headers, raw))
        if r["Event_type"] not in ("GC_PR", "GC_PC"):
            continue
        kind = "release" if r["Event_type"] == "GC_PR" else "conference"
        key = (r["Date_time"].date().isoformat(), kind)
        if key in out:
            raise ValueError(f"Duplicate ECB event {key}")
        de2, de10 = numeric(r["DE2Y"]), numeric(r["DE10Y"])
        out[key] = {"ois1mBp":numeric(r["OIS_1M"]), "ois1yBp":numeric(r["OIS_1Y"]), "de2yBp":de2, "de10yBp":de10, "de2s10sBp": round(de10-de2,4) if de2 is not None and de10 is not None else None}
    wb.close()
    return out

def load_fixes(path):
    with path.open(encoding="utf-8-sig") as f:
        return {r["TIME_PERIOD"]: float(r["OBS_VALUE"]) for r in csv.DictReader(f) if r["OBS_VALUE"]}

def action(day, next_day, fixes):
    # Decisions generally take effect at the following maintenance-period start.
    d = date.fromisoformat(day)
    prior = d - timedelta(days=1)
    last = min(d + timedelta(days=10), date.fromisoformat(next_day)-timedelta(days=1)) if next_day else d+timedelta(days=10)
    values = [(k, v) for k,v in fixes.items() if prior.isoformat() <= k <= last.isoformat()]
    if not values or values[0][0] != prior.isoformat():
        return None, None
    changes = [(k,v) for (_,v0),(k,v) in zip(values,values[1:]) if v0 != v]
    # The coordinated cut took effect on 8 October 2008. A separate corridor-narrowing
    # operation on 9 October reversed the deposit change.
    if day == "2008-10-08":
        changes = [(k, v) for k, v in changes if k == day]
    if len(changes) > 1:
        raise ValueError("Multiple effective-rate changes for "+day)
    effective, rate = changes[0] if changes else (None, values[0][1])
    return round((rate-values[0][1])*100), effective

def source_file(src, typ, args):
    day, url = src["date"], src[typ]
    path = args.cache / f"{typ}-{day}.html"
    if not path.exists():
        if args.offline:
            raise ValueError(f"Missing source {url}")
        request = Request(url, headers={"User-Agent":"ECB communication research"})
        content = urlopen(request,timeout=30).read()
        path.write_bytes(content)
    return path

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache",required=True,type=Path)
    parser.add_argument("--workbook",required=True,type=Path)
    parser.add_argument("--deposit-csv",required=True,type=Path)
    parser.add_argument("--offline",action="store_true")
    args=parser.parse_args()
    args.cache.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((Path(__file__).with_name("ecb-stance-sources.json")).read_text())
    dates=[s["date"] for s in manifest]
    assert dates==sorted(set(dates))
    leaders=json.loads((DATA/"ecb-leadership.json").read_text())["profiles"]
    reviewed={(r["date"],r["sourceType"]):r for r in json.loads((DATA/"ecb-guidance.json").read_text())["observations"]}
    markets=prices(args.workbook)
    fixes=load_fixes(args.deposit_csv)
    def build(i):
        src=manifest[i]
        day=src["date"]
        kind="conference" if "conference" in src else "release"
        path=source_file(src,kind,args)
        old=reviewed.get((day,FORMAT[kind]))
        if old and old["url"]!=src[kind]:
            old=None
        score,rule,evidence,rationale,evidence_kind=reading(path,kind,day,old)
        action_bp,effective=action(day,dates[i+1] if i+1<len(dates) else None,fixes)
        if old and old.get("rateChangeBps") is not None and old["rateChangeBps"] != action_bp:
            raise ValueError(f"Deposit rate mismatch {day} {old['rateChangeBps']} vs {action_bp}")
        quotes=markets.get((day,kind),{})
        leader=next(p["name"] for p in leaders if p["start"]<=day and (p["end"] is None or day<=p["end"]))
        row=dict(bank="ecb",date=day,leader=leader,score=score,rule=rule,evidence=evidence,rationale=rationale,evidenceKind=evidence_kind,sourceType=kind,sourceUrl=src[kind],actionBp=action_bp,effectiveDate=effective,releaseUrl=src["release"],marketBp=quotes.get("ois1yBp"),marketInstrument="1-year euro OIS",marketWindow=WINDOWS[kind][day>="2022-07-01"]+" Frankfurt time",marketSource=MARKET,marketMeasures=quotes)
        if kind=="conference":
            row["releaseMeasures"]=markets.get((day,"release"),{})
            review=reviewed.get((day,FORMAT["release"]))
            if review and review["url"] != src["release"]:
                review=None
            r_score,r_rule,r_evidence,r_reason,r_kind=reading(source_file(src,"release",args),"release",day,review)
            row["releaseReading"]={"score":r_score,"rule":r_rule,"evidence":r_evidence,"rationale":r_reason,"evidenceKind":r_kind,"sourceUrl":src["release"],"marketBp":row["releaseMeasures"].get("ois1yBp"),"marketWindow":WINDOWS["release"][day>="2022-07-01"]+" Frankfurt time"}
        if day in PRE:
            step,asof,url,note=PRE[day]
            row["priorMoveBp"]=step
            row["priorPricingDate"]=asof
            row["priorPricingSource"]=url
            row["priorPricingNote"]=note
        return row
    with ThreadPoolExecutor(max_workers=6) as pool:
        records=list(pool.map(build,range(len(manifest))))
    for i,r in enumerate(records):
        prev=records[i-1] if i else None
        r["previousDate"]=prev["date"] if prev else None
        r["shift"]=(r["score"]-prev["score"]) if prev and prev["sourceType"]==r["sourceType"] and prev["score"] is not None and r["score"] is not None else None
    counts=Counter(r["sourceType"] for r in records)
    result=dict(bank="ecb",source=ARCHIVE,conferenceSource=CONFERENCES,marketSource=MARKET,depositSource=DEPOSIT,marketSourceSha256=hashlib.sha256(args.workbook.read_bytes()).hexdigest(),depositSourceSha256=hashlib.sha256(args.deposit_csv.read_bytes()).hexdigest(),coverage={"decisions":len(records),"scored":sum(r["score"] is not None for r in records),"marketMatched":sum(r["marketBp"] is not None for r in records),"shifts":sum(r["shift"] is not None for r in records),"documentTypes":counts},method=["One observation per dated rate decision in the ECB monetary decisions archive. The primary text is the Council’s public opening statement where available, supplemented by individually checked official Q&A where the speaker explicitly described the Council’s view. Where no conference is archived, the decision release supplies the text. The change requires adjacent meetings with the same document type and two numeric scores.","Positive scores indicate tightening bias and negative scores easing bias or a low-rate commitment. Zero requires an explicit steady path or a balanced assessment of the future rate path. A ‘strong vigilance’ reading during Trichet’s presidency (2005–11) is coded +1. Generic warnings about inflation, asset purchases alone and a description of the policy just announced are insufficient.","The decision is the deposit facility rate change from the official daily series. The observation window runs from the prior day to the earlier of ten calendar days after the announcement or the day before the next decision. Before the floor-system era, other key rates also mattered.","Market readings are changes in the 1-year euro OIS in basis points around the selected release or conference. This tenor spans multiple policy meetings. A conference move starts after the earlier decision release. Each conference record carries a separate reading of the earlier decision release. Distinct decision-release and conference OIS and Bund changes are available where the EA-EMPD covers them. The sources state quote windows in Frankfurt time. Quoted meeting-specific prior expectations are recorded separately only when identified in official accounts or bulletins."],records=records)
    (DATA/"ecb-stance-history.json").write_text(json.dumps(result,ensure_ascii=False,separators=(",",":"))+"\n")
    print(result["coverage"])

if __name__=="__main__":
    main()
