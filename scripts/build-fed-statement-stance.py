"""Rebuild the FOMC wording panel from official releases (Python 3 and lxml).

python scripts/build-fed-statement-stance.py --cache /path/to/statement-html
Sources are pinned in fed-statement-sources.json. When adding a meeting, verify
the FOMC calendar, release date, majority wording, target and any unmatched text.
A cache can be populated online and reused offline with --offline.
"""
import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from urllib.request import Request, urlopen

from lxml import html


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = "https://www.federalreserve.gov/monetarypolicy/fomc_historical.htm"
CALENDAR = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
SCALE = {
    "-2": "Explicit accommodation", "-1": "Conditional easing tilt",
    "0": "Explicit wait or steady stance", "1": "Conditional tightening tilt",
    "2": "Explicit tightening path",
}
# Ordered by precedence. In particular, a new normalization signal takes
# precedence over quotations of the Committee's earlier low-rate guidance.
RULES = [
    ("patient-normalization", 1, "Patience before normalization",
     "The Committee named withdrawal of accommodation and said it could wait before starting.",
     r"patient in (?:removing its policy accommodation|beginning to normalize the stance of monetary policy)"),
    ("cut-hurdle", -1, "Condition for a future cut",
     "A reduction was the specific adjustment under discussion. The Committee set a disinflation hurdle before it could proceed.",
     r"does not expect it will be appropriate to reduce the target range until"),
    ("liftoff-hurdle", 1, "Conditions for a future increase",
     "The Committee identified a rate increase and conditioned it on further progress in the economy.",
     r"appropriate to raise the target range for the federal funds rate when it has seen"),
    ("additional-firming", 1, "Additional firming under consideration",
     "The Committee singled out possible additional tightening and left the need for it conditional.",
     r"(?:some further policy firming may (?:yet )?be needed|any additional firming that may be needed|(?:some |any )?additional policy firming (?:that )?may be appropriate)"),
    ("upcoming-increase", 2, "Increase expected soon",
     "The statement explicitly anticipated near-term liftoff.",
     r"expects it will soon be appropriate to raise the target range"),
    ("ongoing-increases", 2, "Ongoing rate increases",
     "The Committee expected a sequence of rate increases.",
     r"ongoing increases in the target range will be appropriate"),
    ("measured-tightening", 2, "Measured removal of accommodation",
     "The Committee envisaged removing accommodation at a measured pace.",
     r"policy accommodation can be removed at a pace that is likely to be measured|further measured policy firming is likely to be needed"),
    ("gradual-increases", 2, "Gradual rate increases expected",
     "The Committee explicitly described a path of gradual increases in the policy rate.",
     r"(?:will warrant (?:only |further )?|(?:some )?further )gradual increases in the (?:federal funds rate|target range for the federal funds rate)"),
    ("low-rate-threshold", -2, "Low rates until specified conditions",
     "The Committee expected the exceptionally low target range to persist until an economic condition was met.",
     r"this exceptionally low range for the federal funds rate will be appropriate at least as long as|maintain (?:the current target range for the federal funds rate well past the time|this target range until (?:labor market conditions|it is confident))"),
    ("low-rate-horizon", -2, "Low rates for an extended horizon",
     "The Committee explicitly envisaged a sustained period of accommodation or exceptionally low policy rates.",
     r"policy accommodation can be maintained for a considerable period|exceptionally low levels (?:of|for) the federal funds rate (?:are likely to be warranted )?(?:for some time|for an extended period|at least through (?:mid-|late )?\d{4})|target range for the federal funds rate for a considerable time"),
    ("patient-two-sided", 0, "Wait before deciding on adjustments",
     "The Committee explicitly signalled patience about future adjustments without singling out increases or cuts.",
     r"will be patient as it determines what future adjustments to the target range"),
]
FALLBACK = [
    ("support-economy", "Economic support, instrument open", "The Committee pledged to respond to economic conditions while leaving its next policy-rate adjustment open.",
     r"will act as appropriate to sustain the expansion|will use its tools and act as appropriate to support the economy|will act in a timely manner as needed to address those risks|will act as needed to promote sustainable economic growth and price stability"),
    ("current-stance", "Current stance judged appropriate", "The Committee endorsed its current setting without specifying how long it expected to maintain the policy rate.",
     r"the current stance of monetary policy is appropriate to support sustained expansion"),
    ("open-path", "Path left open", "The majority described future assessment or flexibility and specified no rate direction or holding horizon.",
     r"(?:extent and timing of |considering )additional adjustments to the target range|future policy adjustments will depend on the evolution of the outlook|as it assesses the appropriate path of the target range|more information will help the Committee determine the policy stance appropriate|timing and size of future adjustments to the target range"),
]
UNSPECIFIED = "No prospective rate direction, holding horizon or explicit wait signal was identified in the majority's statement."
# Context tags are evidence of risk language, independent of the wording score.
# Mixed risk references take precedence over individual concerns within them.
RISKS = [
    ("Both inflation and unemployment risks rose", r"risks of higher unemployment and higher inflation have risen"),
    ("Growth and inflation risks both identified", r"upside risks to inflation roughly balance the downside risks to growth|upside risks to inflation are also of significant concern|upside risks to inflation are both of significant concern|upside risks to inflation and inflation expectations (?:have )?increased"),
    ("Employment downside", r"downside risks to employment (?:have risen|rose in recent months)"),
    ("Inflation upside", r"heightened inflation pressures in the foreseeable future|predominant policy concern remains the risk that inflation will fail to moderate|highly attentive to inflation risks"),
    ("Growth downside", r"may generate economic weakness|weighted toward weakness over the foreseeable future|downside risks to growth remain|significant downside risks to the economic outlook|downside risks to the economic outlook have increased|continues to see downside risks to the economic outlook"),
    ("Unduly low inflation", r"risk of inflation becoming undesirably low|an unwelcome substantial fall in inflation exceeds"),
    ("Both mandate risks broadly balanced", r"employment and inflation goals are roughly in balance|risks are balanced with respect to the prospects for both goals|both sustainable growth and price stability for the next few quarters are roughly equal"),
    ("Mandate risks moving toward balance", r"(?:are moving|have moved|continue to move) (?:into|toward) better balance"),
    ("Two-sided mandate risks", r"attentive to the risks to both sides of its dual mandate"),
    ("Outlook risks broadly balanced", r"risks to the economic outlook (?:appear|are) roughly balanced"),
    ("Price stability emphasis", r"the Committee will deliver price stability"),
]
METHOD = [
    "The unit is the collective FOMC funds-rate decision statement as published on the release date. Each record links to the Board and identifies the wording used. Individual dissents, press conferences, minutes, portfolio policy and subsequent outcomes are excluded from the wording score.",
    "The ordinal score measures prospective policy-rate inclination. Positive values signal tightening and negative values signal accommodation. An explicit low-for-long commitment can score −2 even when the rate stays unchanged. A conditional future cut scores −1. Only explicit patience about undirected rate changes qualifies for 0 in this sample. Broad economic support or a commitment to price stability alone leaves the rate score unavailable.",
    "The first applicable wording rule wins. For example, the December 2014 statement introduced eventual normalization while explicitly recalling its earlier low-rate pledge. The new policy wording takes precedence. Different horizons, conditionality within a category and dissent can matter even when two scores coincide.",
    "The shift subtracts the immediately preceding funds-rate statement's score from the current score. Both must be available. The scale is ordinal. A two-step shift is a change of rubric categories and has no basis-point or probability interpretation.",
    "Short extracts preserve the source wording with normalized whitespace, apostrophes and dashes. An ellipsis marks an omission. A release time appears when the statement explicitly prints Eastern time.",
    "The action is the change in the announced federal funds point target or the upper bound of a target range, in basis points. A hold is zero. The February 2000 change is stated in the release. The December 2008 switch from a point to a range has no comparable single change.",
    "Risk tags reproduce a separate, limited set of majority risk-balance and emphasis formulations. An untagged statement can still discuss macroeconomic risks. The price-stability emphasis tag records explicit emphasis only. Target actions, risk tags and market prices never enter the wording rules.",
    "The rubric was developed retrospectively. Scores use only the dated statement, but the rules themselves were not available historically. They are descriptive, and have no claimed out-of-sample accuracy or predictive interpretation.",
]
NUMBER = r"(?:\d+[- ]\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)"
RANGE = rf"({NUMBER}) to ({NUMBER}) percent\b"

def number(value):
    return float(sum(Fraction(term) for term in re.split(r"[- ]", value)))

def normalize(value):
    table = str.maketrans({"’": "'", "‘": "'", "‑": "-", "‐": "-", "–": "-", "—": "-"})
    return " ".join(unicodedata.normalize("NFKC", value).translate(table).split())

def statement(raw, date):
    # Current and legacy Board releases have different HTML structure.
    parser = html.HTMLParser(encoding="utf-8") if b"utf-8" in raw[:2400].lower() else None
    doc = html.fromstring(raw, parser=parser)
    region = (doc.xpath('//*[@id="article"]') or doc.xpath("//body"))[0]
    heading = region.xpath('.//*[contains(@class,"article__time")]')
    if heading:
        source_date = datetime.strptime(normalize(heading[0].text_content()), "%B %d, %Y").date().isoformat()
        if source_date != date:
            raise ValueError(f"Release date mismatch for {date}: {source_date}")
    for item in region.xpath(".//script|.//style|.//nav|.//noscript"):
        item.drop_tree()
    full = normalize(" ".join(region.itertext()))
    start = re.search(r"For immediate release|For release at", full, re.I)
    if start:
        full = full[start.start():]
    if date == "2008-10-08":
        # In the coordinated release, only the FOMC portion speaks for this committee.
        full_policy = full[full.index("The Federal Open Market Committee has decided"):]
    else:
        full_policy = full
    body = re.split(r"Voting (?:for|against)|Votes for|In taking the discount rate action|For media inquiries|Last Update:", full_policy, flags=re.I)[0].strip()
    clock = re.search(r"For release at (\d{1,2}(?::\d\d)?\s*[ap]\.m\.\s+E[SD]T)", full, re.I)
    if "federal funds rate" not in body.lower():
        raise ValueError(f"Missing policy text for {date}")
    return body, clock[1] if clock else None

def target(body):
    # Some zero-bound statements put "0 to 1/4 percent" ahead of "target range".
    for item in re.split(r"(?<=[.?!])\s+", body):
        if "federal funds rate" not in item.lower():
            continue
        if "target range" in item.lower():
            m = re.search(RANGE, item)
            if m:
                return number(m[1]), number(m[2]), "range"
        if "target for the federal funds rate" in item.lower():
            m = re.search(rf"target for the federal funds rate[^.;]{{0,75}}?\b(?:at|to) ({NUMBER}) percent\b", item)
            if m:
                return number(m[1]), number(m[1]), "point"
    raise ValueError("Could not read majority target")

def excerpt(match, limit):
    # Keep excerpts short, even when a matched grammatical clause is longer.
    words = match[0].split()
    if len(words) <= limit:
        return " ".join(words)
    leading = (limit + 1) // 2
    trailing = limit - leading
    return " ".join(words[:leading]) + " … " + " ".join(words[-trailing:])

def rulebook():
    result = {key: dict(score=score, label=label, rationale=why) for key, score, label, why, _ in RULES}
    for key, label, why, _ in FALLBACK:
        result[key] = dict(score=None, label=label, rationale=why)
    result["unspecified"] = dict(score=None, label="No explicit rate outlook", rationale=UNSPECIFIED)
    return result

def wording(body):
    for key, _, _, _, pattern in RULES:
        match = re.search(pattern, body, re.I)
        if match:
            return key, excerpt(match, 16)
    for key, _, _, pattern in FALLBACK:
        match = re.search(pattern, body, re.I)
        if match:
            return key, excerpt(match, 16)
    return "unspecified", None

def risk(body):
    for label, pattern in RISKS:
        match = re.search(pattern, body, re.I)
        if match:
            return label, excerpt(match, 9)
    return None, None

def get_release(cache, source, offline):
    path = cache / (source["date"] + ".html")
    if not path.is_file():
        if offline:
            raise FileNotFoundError(path)
        req = Request(source["url"], headers={"User-Agent": "Mozilla/5.0 (FOMC statement research)"})
        with urlopen(req, timeout=35) as reply:
            raw = reply.read()
        statement(raw, source["date"])
        path.write_bytes(raw)
    return path.read_bytes()

def build(sources, cache, offline):
    metadata = rulebook()
    records = []
    if [r["date"] for r in sources] != sorted({r["date"] for r in sources}):
        raise ValueError("Dates must be unique and chronological")
    for source in sources:
        date = source["date"]
        try:
            body, clock = statement(get_release(cache, source, offline), date)
            lo, hi, kind = target(body)
        except Exception as exc:
            raise ValueError(f"Unable to read {date}: {exc}") from exc
        key, evidence = wording(body)
        score = metadata[key]["score"]
        tag, risk_evidence = risk(body)
        prior = records[-1] if records else None
        action = None
        if prior and prior["targetType"] == kind:
            action = round(100 * (hi - prior["targetUpper"]))
        elif date == "2000-02-02" and "raise its target for the federal funds rate by 25 basis points" in body:
            action = 25
        shift = score - prior["score"] if prior and score is not None and prior["score"] is not None else None
        records.append(dict(id="fed-" + date, date=date, title="FOMC monetary policy statement",
                            url=source["url"], publicationET=clock, targetLower=lo, targetUpper=hi,
                            targetType=kind, actionBp=action, score=score, shift=shift,
                            previousDate=prior["date"] if prior else None, rule=key, evidence=evidence,
                            rationale=metadata[key]["rationale"], riskSignal=tag, riskEvidence=risk_evidence,
                            textSha256=hashlib.sha256(body.encode("utf-8")).hexdigest()))
    scores = Counter(r["score"] for r in records)
    coverage = dict(start=records[0]["date"], end=records[-1]["date"], documents=len(records),
                    scored=len(records)-scores[None], unscored=scores[None],
                    comparableShifts=sum(r["shift"] is not None for r in records), source=CALENDAR,
                    historicalArchive=ARCHIVE,
                    scope="Scheduled and intermeeting funds-rate decision statements. Operational, liquidity-only and balance-sheet-only releases are outside this series.")
    return dict(schemaVersion=1, institution="Federal Reserve", series="FOMC statement policy-rate inclination",
                method=METHOD, scale=SCALE, coverage=coverage, rules=metadata, records=records)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "dist/data/fed-statement-stance.json")
    args = parser.parse_args()
    args.cache.mkdir(exist_ok=True, parents=True)
    sources = json.loads(Path(__file__).with_name("fed-statement-sources.json").read_text())
    panel = build(sources, args.cache, args.offline)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(panel, indent=2, ensure_ascii=False) + "\n")
    print(panel["coverage"])
