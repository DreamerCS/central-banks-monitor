"""Compare fixed US historical training samples on identical later inflation targets."""
import json
from math import sqrt
from pathlib import Path
from statistics import mean

DATA = Path(__file__).resolve().parents[1] / "dist/data"
TRAIN = (("1973–1982", 1973, 1982), ("2000–2007", 2000, 2007),
         ("2000–2008", 2000, 2008), ("2009–2019", 2009, 2019))
TEST = (("2020–2021", 2020, 2021), ("2022–2026", 2022, 2026))


def pairs(rows):
    """Dates are calendar months. Never bridge gaps in the input releases."""
    observations = []
    for t in range(12, len(rows) - 6):
        r = rows[t]
        pi, u, last_u, target = (r["cpiYoY"], r["unemployment"],
                                 rows[t-12]["unemployment"], rows[t+6]["cpiYoY"])
        if None not in (pi, u, last_u, target):
            observations.append((r["month"], rows[t+6]["month"], pi, u-last_u, target))
    return observations


def coefficients(sample):
    x, z, y = (mean(row[col] for row in sample) for col in (2, 3, 4))
    xx = sum((r[2]-x)**2 for r in sample)
    zz = sum((r[3]-z)**2 for r in sample)
    xz = sum((r[2]-x)*(r[3]-z) for r in sample)
    xy = sum((r[2]-x)*(r[4]-y) for r in sample)
    zy = sum((r[3]-z)*(r[4]-y) for r in sample)
    det = xx*zz-xz*xz
    if det <= 0:
        raise ValueError("Historical regressors are collinear")
    b, c = (xy*zz-zy*xz)/det, (zy*xx-xy*xz)/det
    return [y-b*x-c*z, b, c]


def main():
    source = json.loads((DATA / "cycle-context.json").read_text())
    rows = pairs(source["rows"])
    models = [{"name": "Unchanged inflation", "coefficients": [0, 1, 0]}]
    for name, start, end in TRAIN:
        sub = [r for r in rows if int(r[0][:4]) >= start and int(r[1][:4]) <= end]
        models.append({"name": name, "n": len(sub), "coefficients": coefficients(sub)})
    evaluations = []
    for label, start, end in TEST:
        # Keep origins after the last training outcome, even for the earliest test targets.
        sub = [r for r in rows if r[0] >= "2020-01" and start <= int(r[1][:4]) <= end]
        scores = []
        for model in models:
            a, b, c = model["coefficients"]
            errors = [a+b*pi+c*du-target for _, _, pi, du, target in sub]
            scores.append({"name": model["name"], "mae": round(mean(map(abs, errors)), 3),
                           "rmse": round(sqrt(mean(e*e for e in errors)), 3)})
        evaluations.append({"period": label, "firstTarget": sub[0][1], "lastTarget": sub[-1][1],
                            "n": len(sub), "scores": scores})
    result = {"vintage": source["asOf"], "horizonMonths": 6, "models": models, "tests": evaluations}
    (DATA / "regime-test.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")


if __name__ == "__main__":
    main()
