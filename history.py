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
    soup=BeautifulSoup(html,'lxml')
    rows=[]
    for tr in soup.select('tr'):
        cells=tr.find_all('td',recursive=False)
        if len(cells)<4: continue
        vals=[norm(c.get_text(' ',strip=True)) for c in cells]
        lot_match=re.match(r'^(\d{2,4}[A-Z]?)\b',vals[0],re.I)
        if not lot_match or '/' not in vals[1]: continue
        pedigree=vals[1]
        sire,tail=pedigree.split('/',1)
        sex_match=re.search(r'\b(?:B/Br|B/Gr|Br/Gr|Gr/Ro|Ch|Gr|Br|Ro|Bl|B)\.([CFG])\.',tail,re.I)
        dam=tail[:sex_match.start()] if sex_match else tail
        # Historical table typically: lot, pedigree, consignor, purchaser, price.
        price_text=vals[-1].replace(',','').replace('gns','').strip()
        if not re.fullmatch(r'\d+(?:\.0+)?',price_text): continue
        price=int(float(price_text))
        if price<=0: continue
        purchaser=vals[-2] if len(vals)>=5 else ''
        if re.search(r'\b(?:vendor|not sold|withdrawn|bought in)\b',purchaser,re.I):
            # Private sales may follow vendor entries; exclude ambiguous records.
            continue
        rows.append({'sale_year':year,'lot':lot_match.group(1).upper(),
            'sire':norm(sire),'dam':norm(dam),
            'sex':{'C':'Colt','F':'Filly','G':'Gelding'}.get(sex_match.group(1).upper(),'') if sex_match else '',
            'consignor':vals[2],'purchaser':purchaser,'price_gns':price,
            'source_url':url,'source_type':'official_tattersalls_results'})
    return pd.DataFrame(rows)

def main():
    OUT.mkdir(exist_ok=True)
    session=requests.Session();session.headers.update(HEADERS)
    try:session.get(ROOT+'/4DCGI/Entry/MenuCatalogues',timeout=25)
    except requests.RequestException:pass
    collected=[];reports=[]
    for year in YEARS:
        url=sale_url(year)
        try:
            r=session.get(url,timeout=40);r.raise_for_status()
            frame=parse_page(r.text,r.url,year)
            # Never silently accept partial or cookie/error pages.
            if len(frame)<300:raise ValueError(f'Only {len(frame)} sold records parsed; check day filter, table layout and cookie response')
            if frame.duplicated(['sale_year','lot']).any():raise ValueError('Duplicate lot IDs in response')
            collected.append(frame)
            reports.append({'year':year,'status':'ok','rows':len(frame),'url':r.url})
        except Exception as e:
            reports.append({'year':year,'status':'failed','error':str(e),'url':url})
    report={'run_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'results':reports,'note':'Prices are historical hammer comparables, not fair values or bid recommendations.'}
    (OUT/'historical_import_status.json').write_text(json.dumps(report,indent=2))
    if len(collected)!=len(YEARS):
        raise RuntimeError('Historical import incomplete; existing data retained. '+json.dumps(reports))
    data=pd.concat(collected,ignore_index=True)
    target=OUT/'historical_sales.csv'
    tmp=OUT/'historical_sales.csv.tmp'
    data.to_csv(tmp,index=False)
    tmp.replace(target)
    print(json.dumps(report,indent=2))
    return data

if __name__=='__main__':main()
