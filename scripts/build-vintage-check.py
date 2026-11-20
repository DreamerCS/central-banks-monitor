"""Recreate six-month US inflation forecasts using Philadelphia Fed data as available at each origin.

Usage: python scripts/build-vintage-check.py /path/to/three/workbooks
Links and SHA-256 of the evaluated workbook editions are recorded in the output.
Dependencies: openpyxl and numpy.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

import numpy as np
from openpyxl import load_workbook

DATA = Path(__file__).resolve().parents[1] / "dist/data"
DOWNLOAD_ROOT = "https://www.philadelphiafed.org/-/media/FRBP/Assets/Surveys-And-Data/real-time-data/data-files/xlsx/"
EDITION = {"cpiQvMd": "57d28f99b28ca9a37801fcdd5026fae9b859e58b0f3dc1e150a55c544598bc34",
           "rucQvMd": "d971e59d3ed5f1322a46631743508fb1ad5eee39bfbe12425a641a277fdd9b9a",
           "pcpiMvMd": "2edd776f458f0c6d563e038ba364f0702d86b0b1da7e37fa3b097a0419076ece"}
SPEC = {"unchanged": "Unchanged inflation", "expanding": "Expanding history",
        "pre08": "2000–2007", "through08": "2000–2008", "post08": "2009–2019"}
H = 6


def month(year, number):
    return year * 12 + number - 1


def label(i):
    year, m = divmod(i, 12)
    return f"{year:04d}-{m+1:02d}"


def matrix(directory, stem):
    file = directory / (stem + ".xlsx")
    if hashlib.sha256(file.read_bytes()).hexdigest() != EDITION[stem]:
        raise ValueError(f"Edition has changed: {file.name}. Review the source vintage boundary before updating.")
    book = load_workbook(file, read_only=True, data_only=True)
    rows = iter(book.active.values)
    columns = {}
    for code in next(rows)[1:]:
        m = re.fullmatch(r"[A-Z]+(\d{2})([QM])(\d+)", code)
        yy, f, n = m.groups()
        year = int(yy) + (1900 if int(yy) >= 45 else 2000)
        columns[month(year, int(n)*3-1 if f == "Q" else int(n))] = {}
    for row in rows:
        at = month(*map(int, row[0].split(":")))
        for v, value in zip(columns.values(), row[1:]):
            if isinstance(value, (int, float)):
                v[at] = value
    book.close()
    return columns


def inflation(price):
    return {t:100*(p/price[t-12]-1) for t, p in price.items() if t-12 in price}


def make_forecasts(pi, unemployment, origin):
    results = {"unchanged": pi[origin]}
    if origin - 12 not in unemployment:
        return results
    intervals = {"expanding": (month(1960, 1), origin)}
    if origin >= month(2020, 1):
        intervals.update({"pre08": (month(2000, 1), month(2007, 12)),
                          "through08": (month(2000, 1), month(2008, 12)),
                          "post08": (month(2009, 1), month(2019, 12))})
    x_now = [1, pi[origin], unemployment[origin]-unemployment[origin-12]]
    for key, (begin, end) in intervals.items():
        origins = [t for t in sorted(pi) if begin <= t and t+H <= end and t+H in pi
                   and t in unemployment and t-12 in unemployment]
        if len(origins) < 60:
            continue
        x = [[1, pi[t], unemployment[t]-unemployment[t-12]] for t in origins]
        y = [pi[t+H] for t in origins]
        coef, _, rank, _ = np.linalg.lstsq(x, y, rcond=None)
        if rank != 3:
            raise ValueError("Unidentified regression")
        results[key] = float(x_now @ coef)
    return results


def score(rows, models):
    # Paired cohort in all three comparisons: same dates, same first-vintage outcome.
    common = [r for r in rows if all(m in r["asKnown"] and m in r["revised"] for m in models)]
    def mae(seq):
        return round(float(np.mean(np.abs(seq))), 4)
    def metrics(m):
        return {"model": m,
                "realTime": mae([r["asKnown"][m]-r["initial"] for r in common]),
                "revisedInput": mae([r["revised"][m]-r["initial"] for r in common]),
                "revisedOutcome": mae([r["asKnown"][m]-r["latest"] for r in common])}
    if not common:
        raise ValueError("Empty evaluation")
    return {"n": len(common), "first": common[0]["target"], "last": common[-1]["target"],
            "scores": [metrics(m) for m in models],
            "meanAbsoluteRevision": mae([r["initial"]-r["latest"] for r in common])}


def build(directory):
    cp = matrix(directory, "cpiQvMd")
    un = matrix(directory, "rucQvMd")
    monthly = {v:inflation(p) for v,p in matrix(directory, "pcpiMvMd").items()}
    context = json.loads((DATA/"cycle-context.json").read_text())
    rows = {month(*map(int,r["month"].split("-"))):r for r in context["rows"]}
    final_pi = inflation({t:r["cpi"] for t,r in rows.items() if r["cpi"] is not None})
    final_u = {t:r["unemployment"] for t,r in rows.items() if r["unemployment"] is not None}
    records, excluded = [], []
    for v in sorted(cp.keys() & un.keys()):
        if v < month(2000, 1):
            continue
        pi = inflation(cp[v])
        observed = pi.keys() & un[v].keys()
        if not observed:
            continue
        t = max(observed)
        assert t < v
        target = t + H
        first = next((d for d,p in monthly.items() if d>v and d>target and target in p), None)
        if first is None or target not in final_pi:
            reason = "Future target" if target > max(rows) else "Missing CPI observation or year-on-year base"
            excluded.append({"vintage":label(v),"origin":label(t),"target":label(target),"reason":reason})
            continue
        if t not in final_pi or t not in final_u:
            continue
        original = make_forecasts(pi,un[v],t)
        revised = make_forecasts(final_pi,final_u,t)
        records.append({"vintage":label(v), "origin":label(t), "target":label(target),
                        "outcomeVintage":label(first),"initial":monthly[first][target],
                        "latest":final_pi[target],"asKnown":original,"revised":revised})
    if len({r["origin"] for r in records}) != len(records):
        raise ValueError("Repeated forecast origin")
    basic = ["unchanged","expanding"]
    periods = [("all","2000 onwards",records,basic),
               ("gfc","Financial crisis",[r for r in records if "2007-12"<=r["target"]<="2009-06"],basic),
               ("pandemic","2020–2021",[r for r in records if r["origin"]>="2020-01" and r["target"]<"2022"],list(SPEC)),
               ("recent","2022 onwards",[r for r in records if r["target"]>="2022"],list(SPEC))]
    return {"asOf":context["asOf"], "frequency":"Quarterly information sets, monthly CPI observations",
            "models":SPEC,"sources":[{"file":x+".xlsx","url":DOWNLOAD_ROOT+x+".xlsx","sha256":sha} for x,sha in EDITION.items()],
            "periods":[dict(id=key,label=desc,**score(sample,models)) for key,desc,sample,models in periods],
            "unscored":excluded,"observations":[{**r,"initial":round(r["initial"],4),"latest":round(r["latest"],4),
            "asKnown":{k:round(v,4) for k,v in r["asKnown"].items()},
            "revised":{k:round(v,4) for k,v in r["revised"].items()}} for r in records]}


if __name__ == "__main__":
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("directory",type=Path)
    result = build(args.parse_args().directory)
    (DATA/"vintage-check.json").write_text(json.dumps(result,ensure_ascii=False,separators=(",",":"))+"\n")
