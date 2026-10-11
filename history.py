"""Non-destructive historical Tattersalls Book 2 sales collector.
Run: python history.py. Writes output/historical_sales.csv and a diagnostic JSON.
Requires requests, beautifulsoup4, pandas, lxml (already used by V2).
Only published hammer prices; excludes unsold/vendor lots where identifiable.
"""
import json, re, datetime
from pathlib import Path
from urllib.parse import urljoin
import requests
import pandas as pd
from bs4 import BeautifulSoup

OUT=Path(__file__).resolve().parent/'output'
ROOT='https://db.tattersalls.com'
YEARS=(2023,2024,2025)
HEADERS={'User-Agent':'Mozilla/5.0 (compatible; BloodstockValueEngine/0.3; research)'}

def norm(s):
    return re.sub(r'\s+',' ',s or '').strip()


def sale_url(year):
    # Whole Sale URL confirmed in browser for 2025.
    return (
        ROOT
        + '/4DCGI/Entry/List?30%096%09=%20OC2%20'
        + str(year)[-2:]
        + '%09by8'
    )



def parse_page(html, url, year):
    soup = BeautifulSoup(html, 'lxml')
    rows = []

    for tr in soup.select('tr'):
        cells = tr.find_all('td', recursive=False)
        if len(cells) < 5:
            continue

        vals = [
            norm(c.get_text(' ', strip=True))
            for c in cells
        ]

        lot_match = re.match(r'^(\d{2,4}[A-Z]?)$', vals[0], re.I)
        if not lot_match:
            continue

        pedigree = vals[1]
        if '/' not in pedigree:
            continue

        # Tattersalls historical results columns:
        # LOT | NAME BY SIRE EX DAM | CONSIGNOR | PURCHASER | PRICE
        sire, tail = pedigree.split('/', 1)

        sex_match = re.search(
            r'\b(?:B|Br|Ch|Gr|Ro|Bl)(?:/Br|/Gr|/Ro)?'
            r'\.?\s*([CFG])\.',
            tail,
            re.I
        )

        dam = tail[:sex_match.start()] if sex_match else tail

        purchaser = vals[-2]
        price_text = vals[-1].replace(',', '').strip()

        if not re.fullmatch(r'\d+', price_text):
            continue

        price = int(price_text)
        if price <= 0:
            continue

        # Exclude bought-in and private-sale records.
        if re.search(
            r'vendor|withdrawn|not sold|bought in|\(P\.S\.\)',
            purchaser,
            re.I
        ):
            continue

        rows.append({
            'sale_year': year,
            'lot': lot_match.group(1).upper(),
            'sire': norm(sire),
            'dam': norm(dam),
            'sex': (
                {'C': 'Colt', 'F': 'Filly', 'G': 'Gelding'}
                .get(sex_match.group(1).upper(), '')
                if sex_match else ''
            ),
            'consignor': vals[-3],
            'purchaser': purchaser,
            'price_gns': price,
            'source_url': url,
            'source_type': 'official_tattersalls_results'
        })

    return pd.DataFrame(rows)



def main():
    OUT.mkdir(exist_ok=True)

    session = requests.Session()
    session.headers.update(HEADERS)

    # Establish a Tattersalls session.
    try:
        session.get(
            ROOT + "/4DCGI/Entry/MenuCatalogues",
            timeout=25
        )
    except requests.RequestException as exc:
        print("Session initialization warning:", exc)

    print(
        "Tattersalls session cookie names:",
        list(session.cookies.keys())
    )

    collected = []
    reports = []

    for year in YEARS:
        url = sale_url(year)

        try:
            r = session.get(url, timeout=40)
            r.raise_for_status()

            page_title = BeautifulSoup(r.text, "lxml").title
            title = (
                page_title.get_text(" ", strip=True)
                if page_title else ""
            )

            if "no cookie" in title.lower():
                raise RuntimeError(
                    "Tattersalls returned a No Cookie page "
                    "instead of sale results."
                )

            frame = parse_page(r.text, r.url, year)

            if len(frame) < 300:
                raise ValueError(
                    f"Only {len(frame)} sold records parsed; "
                    "check page layout or cookie response."
                )

            if frame.duplicated(["sale_year", "lot"]).any():
                raise ValueError("Duplicate lot IDs in response")

            collected.append(frame)

            reports.append({
                "year": year,
                "status": "ok",
                "rows": len(frame),
                "url": r.url
            })

        except Exception as exc:
            reports.append({
                "year": year,
                "status": "failed",
                "error": str(exc),
                "url": url
            })

    report = {
        "run_utc": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(),
        "results": reports,
        "note": (
            "Historical hammer comparables, "
            "not fair values or bid recommendations."
        )
    }

    (OUT / "historical_import_status.json").write_text(
        json.dumps(report, indent=2)
    )

    if len(collected) != len(YEARS):
        raise RuntimeError(
            "Historical import incomplete; existing data retained. "
            + json.dumps(reports)
        )

    data = pd.concat(collected, ignore_index=True)

    target = OUT / "historical_sales.csv"
    tmp = OUT / "historical_sales.csv.tmp"

    data.to_csv(tmp, index=False)
    tmp.replace(target)

    print(json.dumps(report, indent=2))

    return data


if __name__ == "__main__":
    main()

