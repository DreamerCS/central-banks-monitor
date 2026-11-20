"""Read forward guidance and inflation risk as two distinct features.

Run scripts/build-ecb-stance-history.py first to populate --ecb-cache, then:
python scripts/build-stance-risk-signals.py --ecb-cache /path/to/ECB-pages
"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

from lxml import html

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "dist/data"
SUBJECT = r"risks? (?:to|surrounding|for) (?:the )?(?:(?:medium-term |near-term )?outlook for |baseline )?(?:price stability|price developments|inflation(?: outlook| scenario)?)"
QUALIFIER = r"(?: (?:in|over|at) (?:the )?(?:short|medium|longer|near|policy-relevant)(?:[- ]to[- ](?:medium|longer))?[- ](?:term|run|horizon)(?: horizon)?)?"
VERB = r"(?: (?:are|were viewed as still remaining|are viewed as still remaining|are expected to be still|remain|appear|are considered to be|are seen to be|to be|still to be|prevail|continues? to be|are assessed to be|are judged to be))"
DEGREE = r"(?: (?:still|clearly|broadly|rather|at present|primarily|mainly|firmly|predominantly|tilted|somewhat|slightly|largely)){0,3}"
AGGREGATE = re.compile(r"(?P<quote>" + SUBJECT + QUALIFIER + VERB + DEGREE + r" (?P<direction>(?:towards? |on |to )?the (?:upside|downside)|balanced|two[- ]sided))\b", re.I)
NAMED = re.compile(r"(?P<quote>(?P<direction>upside|downside) risks? (?:to|for) (?:the )?(?:medium-term )?(?:outlook for )?(?:price stability|inflation(?: outlook)?))",re.I)
HIGH = re.compile(r"inflation (?:may surprise on the upside|(?:could|might|may) (?:surprise|(?:turn out )?(?:to be |be )?)(?:on the upside|higher)(?: than (?:expected|anticipated|projected))?)",re.I)
LOW = re.compile(r"inflation (?:may surprise on the downside|(?:could|might|may) (?:surprise|(?:turn out )?(?:to be |be )?)(?:on the downside|lower)(?: than (?:expected|anticipated|projected))?)",re.I)
STOP = re.compile(r"^(?:Question\s*[:(]|My first question|Transcript of the questions|Questions and answers|Q\s*:|\* \* \*)|(?:now|glad|happy|ready|available|at your disposal|pleased).{0,65}(?:take|answer|welcome|hear|open|disposal|your|any) (?:your |any )?questions", re.I)
LABEL = {"upside":"Inflation upside","downside":"Inflation downside","balanced":"Inflation risks balanced","two-sided":"Two-sided inflation risks"}
def opening(path):
    doc=html.fromstring(path.read_bytes().decode("utf-8",errors="replace"))
    paragraphs=[]
    for p in doc.xpath("//main//*[self::p or self::li[not(.//p)] or self::h2 or self::h3]"):
        t=" ".join(p.text_content().replace("’","'").split())
        if len(paragraphs)>3 and STOP.search(t):
            break
        if t:
            paragraphs.append(t)
    return paragraphs

def signal(paragraphs):
    candidates = {}
    named = {}
    paired = None
    for paragraph in paragraphs:
        for sentence in re.split(r"(?<=[.!?])\s+",paragraph):
            for m in AGGREGATE.finditer(sentence):
                # Only present assessments. Comparative balance can coexist with a tilt.
                before = sentence[:m.start()]
                if re.search(r"\b(?:then|previously|former|last year|in the past|at that time|if|should|could|would|might|whether)\b",before,re.I):
                    continue
                if re.search(r"\b(?:no longer|more|less)\b",m[0],re.I):
                    continue
                side=m["direction"].lower().split()[-1].replace("two sided","two-sided")
                if side in LABEL:
                    candidates.setdefault(side,m["quote"])
            for m in NAMED.finditer(sentence):
                # For single-sided calls, require language explicitly establishing prevailing risk.
                before=sentence[:m.start()]
                after=sentence[m.end():]
                prefix = re.search(r"(?:prevailing|continued|predominance of)\s+$", before, re.I)
                if prefix or re.match(r"\s+(?:prevail|have intensified|remain predominant|are predominant)\b",after,re.I):
                    if not re.search(r"if |would |could |during the |in the past|countering|against",before,re.I):
                        tail=re.match(r"\s+(?:prevail|have intensified|remain predominant|are predominant)\b",after,re.I)
                        named.setdefault(m["direction"].lower(),(prefix[0] if prefix else "")+m[0]+(tail[0] if tail else ""))
        ups = HIGH.search(paragraph)
        downs = LOW.search(paragraph)
        if ups and downs:
            paired=ups[0]+" / "+downs[0]
    if len(candidates)==1:
        side,quote=next(iter(candidates.items()))
        return LABEL[side], quote
    if candidates:
        # Opposing horizon assessments have no unique sign without a horizon-specific series.
        return None, ""
    if paired:
        return LABEL["two-sided"],paired
    if len(named)==1:
        side,quote=next(iter(named.items()))
        return LABEL[side],quote
    return None, ""

def summaries(rows):
    counts=[]
    for leader in dict.fromkeys(r["leader"] for r in rows):
        sample=[r for r in rows if r["leader"]==leader]
        observed=[r for r in sample if r["signal"]]
        counts.append(dict(leader=leader,events=len(sample),identified=len(observed),guidanceMissing=sum(r["score"] is None for r in sample),identifiedWithGuidanceMissing=sum(r["score"] is None for r in observed),bySignal=dict(Counter(r["signal"] for r in observed))))
    return counts

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--ecb-cache",type=Path,required=True)
    parser.add_argument("--data",type=Path,default=DATA)
    parser.add_argument("--output",type=Path,default=DATA/"stance-risk-signals.json")
    args=parser.parse_args()
    eur=json.loads((args.data/"ecb-stance-history.json").read_text())["records"]
    us=json.loads((args.data/"fed-statement-stance.json").read_text())["records"]
    leaders=json.loads((args.data/"fed-leadership.json").read_text())["profiles"]
    erows=[]
    for r in eur:
        day=r["date"]
        conferenced=r["sourceType"]=="conference"
        rate,proof=signal(opening(args.ecb_cache/("conference-"+day+".html"))) if conferenced else (None,"")
        erows.append(dict(date=day,leader=r["leader"],signal=rate,evidence=proof,sourceUrl=r["sourceUrl"],score=r["score"],sourceType="conference" if conferenced else "release"))
    frows=[]
    for r in us:
        day=r["date"]
        leader=next((p["name"] for p in leaders if p["start"]<=day and (p["end"] is None or day<=p["end"])),None)
        if leader is None:raise ValueError("Missing Fed term "+day)
        frows.append(dict(date=day, leader=leader, signal=r["riskSignal"],evidence=r["riskEvidence"] or "",sourceUrl=r["url"],score=r["score"],sourceType="statement"))
    results={"banks":{
        "ecb":{"label":"Inflation risk balance","scope":"ECB opening statements only. An observation requires an explicit assessment of risks to inflation or price stability. Two-sided means the same passage identifies both upside and downside inflation scenarios. It need not mean equal weight. Rate-only releases, growth risks and comparative language without a clear tilt remain unclassified. Opposing explicit tilts at different horizons are left open.","records":erows,"byLeader":summaries(erows)},
        "fed":{"label":"FOMC balance of risks","scope":"FOMC decision statements use the archive’s original wording rules. Categories can concern inflation, employment, growth, or the balance of both mandates. They have different meanings from the ECB categories.","records":frows,"byLeader":summaries(frows)}}}
    args.output.write_text(json.dumps(results,ensure_ascii=False,separators=(",",":"))+"\n")
    for bank,v in results["banks"].items():
        print(bank,[(s["leader"],s["identified"],s["identifiedWithGuidanceMissing"]) for s in v["byLeader"]])

if __name__=="__main__":
    main()
