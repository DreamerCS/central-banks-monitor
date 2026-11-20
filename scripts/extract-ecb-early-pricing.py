"""Rebuild rounded estimates from ECB Working Paper 192, Figure 1 (printed p. 49).

Requires PyMuPDF. Run with the original PDF, a generated ECB stance history JSON,
and an output path. Download the PDF from SOURCE. It is not redistributed here.
"""

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path

import fitz


SOURCE = "https://www.ecb.europa.eu/pub/pdf/scpwps/ecbwp192.pdf#page=50"
SHA256 = "695d67d6a2ce42f2df9361ba23be0b75c9e31866d499811672dd951676c59b82"
FIRST = dt.date(2000, 1, 1)
LAST = dt.date(2002, 6, 6)

# Two solid circles named on the figure anchor its calendar-day axis, in PDF points.
DATE_A, X_A = dt.date(2000, 4, 13), 349.316
DATE_B, X_B = dt.date(2001, 5, 10), 556.460
# Left-axis tick at 0; top and bottom grid lines at +75 and -75 bp.
ZERO_Y, TOP_Y, BOTTOM_Y = 252.48, 82.160, 422.684
ACTION_CHECKS = {
    "1999-04-08": -50, "1999-11-04": 50,
    "2000-02-03": 25, "2000-03-16": 25, "2000-04-27": 25,
    "2000-06-08": 50, "2000-08-31": 25, "2000-10-05": 25,
    "2001-05-10": -25, "2001-08-30": -25, "2001-09-17": -50, "2001-11-08": -50,
}


def date_at(x):
    days = (x - X_A) * (DATE_B - DATE_A).days / (X_B - X_A)
    if abs(days - round(days)) > 0.30:
        raise ValueError("Drawing position does not resolve to a unique calendar day")
    return DATE_A + dt.timedelta(days=round(days))


def bp_at(y):
    return (ZERO_Y - y) * 150 / (BOTTOM_Y - TOP_Y)


def extract(pdf, archive):
    data = pdf.read_bytes()
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError("Unexpected revision of the source PDF")
    dots, bars, failures = {}, {}, set()
    with fitz.open(stream=data, filetype="pdf") as doc:
        page = doc[49]
        if "Figure 1:" not in page.get_text():
            raise ValueError("Figure 1 could not be identified")
        for drawing in page.get_drawings():
            box = drawing["rect"]
            x = (box.x0 + box.x1) / 2
            items = drawing["items"]
            if 8.8 < box.width < 9.1 and len(items) == 4 and all(p[0] == "c" for p in items):
                date = date_at(x).isoformat()
                if date in dots:
                    raise ValueError("Two source circles resolve to the same meeting")
                dots[date] = round(bp_at((box.y0 + box.y1) / 2))
                if drawing["fill"] is not None:
                    failures.add(date)
            if drawing["type"] == "fs" and len(items) == 1 and items[0][0] == "re" and box.width < 0.4 and box.height > 50:
                edge = max([box.y0, box.y1], key=lambda y: abs(y - ZERO_Y))
                bars[date_at(x).isoformat()] = round(bp_at(edge))
    if len(dots) != 78 or bars != ACTION_CHECKS:
        raise ValueError("Counts or control dates/amounts of the twelve policy changes disagree")
    if failures != {"1999-10-07", "2000-04-13", "2000-05-11", "2000-05-25", "2001-05-10"}:
        raise ValueError("Labeled dates of filled circles disagree")
    in_scope = {date: value for date, value in sorted(dots.items())
                if FIRST.isoformat() <= date <= LAST.isoformat()}
    releases = json.loads(archive.read_text())["records"]
    dates = {r["date"] for r in releases if FIRST.isoformat() <= r["date"] <= LAST.isoformat()}
    if len(in_scope) != 54 or dates != in_scope.keys():
        raise ValueError("Source dates differ from the published ECB decisions archive")
    return {
        "source": SOURCE,
        "sourceTitle": "Gabriel Pérez-Quirós and Jorge Sicilia (2002), ECB Working Paper 192, Figure 1",
        "sourceSha256": SHA256,
        "sourceRights": "ECB Working Paper 192 permits reproduction for educational and non-commercial purposes with acknowledgement. The figure and the PDF are not redistributed.",
        "method": "Authors’ previous-observation, two-week EONIA swap adjusted downward by 5 bp relative to the prevailing MRO rate. Values recovered from the figure and rounded to whole bp. Allow approximately ±1 bp for chart reading. The assumed EONIA–MRO spread, term and liquidity effects introduce additional uncertainty. No intraday observation time is supplied. The emergency decision on 17 September 2001 is included.",
        "priorInstrumentKey": "MRO",
        "sourceObservations": len(dots),
        "valuesBp": in_scope,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = extract(args.pdf, args.archive)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
