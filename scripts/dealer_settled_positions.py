"""Measure changes in the on-the-run nominal ten-year note at regular reopenings."""
from bisect import bisect_right
from statistics import median

SERIES = "PDSI10NSP"
HORIZONS = ("preSettlement", "settlement", "week1", "week2", "week3")


def build_same_security(events, treasury_rows, observations):
    """Reuse the main event calendar and award groups, retaining a common CUSIP."""
    new_issues = sorted(
        (row["issueDate"][:10], row["cusip"])
        for row in treasury_rows
        if row.get("originalSecurityTerm") == "10-Year"
        and row.get("securityTerm") == "10-Year"
        and row.get("securityType") == "Note"
        and row.get("inflationProtected") == "No"
        and row.get("reopening") == "No"
    )
    issue_dates = [day for day, _ in new_issues]

    def current_cusip(day):
        i = bisect_right(issue_dates, day) - 1
        return new_issues[i][1] if i >= 0 else None

    positions = {
        row["asofdate"]: int(row["value"]) for row in observations
        if row["keyid"] == SERIES and row["value"] not in (None, "", "*")
    }
    matches = {}
    groups = {}
    for event in events:
        if event["issueType"] != "Reopening":
            continue
        reports = event["reports"]
        if not reports["preSettlement"]:
            continue
        cusip = event["cusip"]
        baseline = reports["preSettlement"]["date"]
        if current_cusip(baseline) != cusip or baseline not in positions:
            continue
        marks = {}
        for horizon in HORIZONS:
            report = reports[horizon]
            if not report:
                continue
            day = report["date"]
            if current_cusip(day) == cusip and day in positions:
                marks[horizon] = {
                    "date": day, "positionBn": positions[day] / 1000,
                    "changeBn": (positions[day] - positions[baseline]) / 1000,
                }
        if "settlement" in marks:
            matches[event["auctionDate"]] = {"cusip": cusip, "reports": marks}
            groups[event["auctionDate"]] = event["awardGroup"]

    summary = []
    for group in ("All", "High", "Middle", "Low"):
        selected = [e["reports"] for day, e in matches.items() if group == "All" or groups[day] == group]
        horizons = {}
        for h in HORIZONS:
            observations_h = [r[h] for r in selected if h in r]
            changes = [r["changeBn"] for r in observations_h]
            horizons[h] = {
                "n": len(changes),
                "medianChangeBn": round(median(changes), 5) if changes else None,
                "aboveBaseline": sum(change > 0 for change in changes),
            }
        summary.append({"awardGroup": group, "horizons": horizons})
    return {
        "series": SERIES, "events": matches, "summary": summary,
        "method": "At a regular reopening the same nominal ten-year note is already trading. Match its CUSIP using the Treasury schedule of original ten-year issues on each observation date. For the first Wednesday on or after issue and subsequent Wednesdays, subtract the last Wednesday strictly before issue. Keep observations in the same reporting period before the next regular ten-year auction. Source data aggregate all dealers’ net settled positions in the current issue at par, in millions of US dollars. Changes can reflect short covering or secondary-market trading. The public series does not tag individual dealers or lots.",
        "sources": [
            {"label": "New York Fed · current ten-year net settled positions, FR 2004SI", "url": "https://markets.newyorkfed.org/api/pd/get/PDSI10NSP.json"},
            {"label": "New York Fed · FR 2004SI reporting guide", "url": "https://www.newyorkfed.org/financial-institution-supervision/reporting-forms-and-instructions/reporting-forms/fr-2004si-guide-sheet"},
            {"label": "Federal Reserve Board · net settled positions, settlement-date accounting and par values", "url": "https://www.federalreserve.gov/reportforms/forms/FR_200420201231_i.pdf"},
        ],
    }
