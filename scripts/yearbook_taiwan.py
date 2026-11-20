"""Read Taiwan DGBAS national accounts and cross-check full-year CPI against index levels."""
from decimal import Decimal, ROUND_HALF_UP
import io
import re
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from zipfile import ZipFile

ROOT = "https://ws.dgbas.gov.tw/001/Upload/"
GDP = ROOT + "463/relfile/10315/2711/table(060a).ods"
CPI = ROOT + "464/relfile/10320/2727/cpiidxc.ods"
LEVELS = ROOT + "464/relfile/10320/2727/cpiidx.ods"
TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
MONTH_NAMES = ["Jan.", "Feb.", "Mar.", "Apr.", "May", "June", "July", "Aug.", "Sept.", "Oct.", "Nov.", "Dec."]
PERCENT_PRECISION = Decimal("0.01")


def read_table(url, folder, filename, sheet_name):
    if folder:
        data = (folder / filename).read_bytes()
    else:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0 (public statistical tables)"})
        with urlopen(request, timeout=60) as response:
            data = response.read()
    with ZipFile(io.BytesIO(data)) as book:
        document = ET.fromstring(book.read("content.xml"))
    sheet = next(t for t in document.iter(TABLE + "table") if t.get(TABLE + "name") == sheet_name)
    rows = []
    for row in sheet.iter(TABLE + "table-row"):
        values = []
        for cell in row:
            if cell.tag not in (TABLE + "table-cell", TABLE + "covered-table-cell"):
                continue
            value = " ".join("".join(p.itertext()).strip() for p in cell.findall(TEXT + "p")).strip()
            # Large nominal blank regions occur in ODS. All required fields fit in 16 columns.
            repeat = min(int(cell.get(TABLE + "number-columns-repeated", 1)), 16 - len(values))
            values.extend([value] * repeat)
            if len(values) == 16:
                break
        rows.append(values)
    return rows


def growth(rows):
    header = next(r for r in rows if any("經濟成長" == x.replace(" ", "") for x in r))
    column = next(i for i, x in enumerate(header) if x.replace(" ", "") == "經濟成長")
    stamp = next(re.search(r"更新[：:]\s*(\d{4}/\d{1,2}/\d{1,2})", cell).group(1)
                 for row in rows for cell in row if re.search(r"更新[：:]\s*\d{4}/", cell))
    annual = {}
    for pos, row in enumerate(rows):
        label = re.fullmatch(r"(\d{2,3})年", row[0]) if row else None
        if not label or not row[column] or row[column] == "－":
            continue
        quarters = [r[0] for r in rows[pos + 1:pos + 5] if len(r) > column and r[column]]
        # Accept only full historic annual observations followed by four reported,
        # unflagged calendar quarters. Projections or incomplete years are excluded.
        if quarters == ["Ⅰ", "Ⅱ", "Ⅲ", "Ⅳ"]:
            year = 1911 + int(label.group(1))
            if year in annual:
                raise ValueError(f"Duplicate GDP year {year}")
            annual[year] = Decimal(row[column])
    return annual, stamp.replace("/", "-")


def cpi(rows, title):
    if not any(title == x for x in rows[0]):
        raise ValueError(f"Unexpected source file: {title}")
    labels = next(r for r in rows if r[:2] == ["Year", "Jan."])
    yearly = next(r.index("Yearly") for r in rows if "Yearly" in r)
    if labels[1:13] != MONTH_NAMES or yearly != 13:
        raise ValueError("The CPI calendar and yearly columns have changed")
    annual = {}
    latest_month = ""
    for row in rows:
        if not row or not re.fullmatch(r"\d{4}", row[0]):
            continue
        year = int(row[0])
        months = [m for m, value in enumerate(row[1:13], 1) if value]
        if months:
            latest_month = max(latest_month, f"{year}-{max(months):02d}")
        if len(months) == 12 and row[yearly]:
            if year in annual:
                raise ValueError(f"Duplicate CPI year {year}")
            annual[year] = Decimal(row[yearly])
    return annual, latest_month


def read_annual(start_year, end_year, input_dir=None):
    gdp, gdp_update = growth(read_table(GDP, input_dir, "gdp.ods", "資料"))
    inflation, latest_cpi = cpi(read_table(CPI, input_dir, "cpi.ods", "Sheet1"), "Annual Change of Consumer Price Indices")
    levels, latest_levels = cpi(read_table(LEVELS, input_dir, "cpi-levels.ods", "Sheet1"), "Time Series of Consumer Price Indices")
    if latest_cpi != latest_levels:
        raise ValueError("Price index level and change tables come from different releases")
    paired = {}
    for year in range(start_year, end_year + 1):
        if year not in gdp or year not in inflation or year - 1 not in levels or year not in levels:
            raise ValueError(f"No complete pair of official annual observations for {year}")
        calculated = ((levels[year] / levels[year - 1] - 1) * 100).quantize(PERCENT_PRECISION, rounding=ROUND_HALF_UP)
        if calculated != inflation[year]:
            raise ValueError(f"Published CPI rate for {year} differs from the ratio of annual indices")
        paired[str(year)] = [float(gdp[year]), float(inflation[year])]
    return {
        "sourceUrls": {"gdp": GDP, "inflation": CPI},
        "vintage": f"DGBAS national accounts updated {gdp_update}; consumer prices through {latest_cpi}.",
        "rows": paired,
        "notes": "Percent change on the preceding calendar year. GDP uses DGBAS reported real economic growth. Inflation uses the change in the all-items annual-average consumer price index (2021=100), verified against the ratio of full-year average indices. Includes only years with four reported GDP quarters and twelve CPI months. Taiwan figures are DGBAS observations and may be revised."
    }
