"""Tattersalls Book 2 catalogue importer and transparent screening model.
Run: python engine.py ; dashboard: streamlit run dashboard.py
No fabricated racing statistics or valuation estimates.
"""
import io, re, json, datetime, pathlib, hashlib
from urllib.parse import urljoin
import requests
import pandas as pd
from bs4 import BeautifulSoup

BASE='https://db.tattersalls.com/4DCGI/Entry/List'
OUT=pathlib.Path(__file__).resolve().parent/'output'
HEADERS={'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36'}
# URL verified from Tattersalls' own Day 1/2/3 navigation.
DAY_URLS={day: BASE+'?30%096%09=%20OC2%2026%09%250A30%0912%09=%20'+str(day)+'%09by8' for day in (1,2,3)}

def _parse_html(html,day,url):
    soup=BeautifulSoup(html,'lxml')
    if 'No Cookie' in soup.get_text(' ',strip=True)[:300] or 'set up to allow you to access' in soup.get_text(' ',strip=True)[:600]:
        raise RuntimeError('Tattersalls requires a session cookie')
    best=[]
    for table in soup.find_all('table'):
        rows=[]
        for tr in table.find_all('tr'):
            cells=tr.find_all('td',recursive=False)
            if len(cells)<3:continue
            cols=[c.get_text(' ',strip=True) for c in cells]
            m=re.search(r'^\s*(\d{3,4}[A-Z]?)\b',cols[0],re.I)
            if not m:continue
            pedigree=cols[1]
            if '/' not in pedigree:continue
            sire,rest=pedigree.split('/',1)
            match=re.search(r'\b(?:B/Br|B/Gr|Br/Gr|Gr/Ro|Ch|Gr|Br|Ro|Bl|B)\.([CFG])\.',rest,re.I)
            dam=rest[:match.start()].strip() if match else re.split(r'\s+Lot\s+Withdrawn|\s+UPDATE',rest)[0].strip()
            rows.append({'lot':m.group(1).upper(),'sire':sire.strip(),'dam':dam,
                         'sex':{'C':'Colt','F':'Filly','G':'Gelding'}.get(match.group(1).upper(),'') if match else '',
                         'consignor':cols[2],'stabling':cols[3] if len(cols)>3 else '',
                         'withdrawn':'withdrawn' in pedigree.lower(),
                         'pedigree_update':'UPDATE' in pedigree.upper(),
                         'day':day,'source_url':url,'source_type':'official_catalogue'})
        if len(rows)>len(best):best=rows
    return pd.DataFrame(best)

def _parse_xls(content,day,url):
    frames=pd.read_excel(io.BytesIO(content),sheet_name=None)
    for frame in frames.values():
        frame.columns=[str(c).strip().lower() for c in frame.columns]
        if not {'lot','sire','dam'}.issubset(frame.columns):continue
        frame=frame.dropna(subset=['lot','sire','dam']).copy()
        frame['lot']=frame['lot'].astype(str).str.replace(r'\.0$','',regex=True).str.strip().str.upper()
        frame=frame[frame['lot'].str.fullmatch(r'\d{3,4}[A-Z]?',na=False)]
        if len(frame)<100:continue
        out=pd.DataFrame({'lot':frame.lot,'sire':frame.sire.astype(str),'dam':frame.dam.astype(str),
          'sex':frame.sex.astype(str).str.upper().map({'C':'Colt','F':'Filly','G':'Gelding'}).fillna('') if 'sex' in frame else '',
          'consignor':frame.consignor.fillna('').astype(str) if 'consignor' in frame else '',
          'stabling':frame.stabling.fillna('').astype(str) if 'stabling' in frame else '',
          'withdrawn':False,'pedigree_update':False,'day':day,
          'source_url':url,'source_type':'official_xls'})
        for col in ['colour','date foaled','grandsire','damsire']:
            if col in frame:out[col.replace(' ','_')]=frame[col].values
        return out
    raise RuntimeError('XLS columns or rows not recognised')

def catalogue_html():
    session=requests.Session();session.headers.update(HEADERS)
    # Initial navigation establishes any cookie before following session links.
    try:session.get('https://db.tattersalls.com/4DCGI/Entry/MenuCatalogues',timeout=25)
    except requests.RequestException:pass
    all_days=[];diagnostics=[]
    for day,url in DAY_URLS.items():
        try:
            response=session.get(url,timeout=35);response.raise_for_status()
            frame=_parse_html(response.text,day,response.url)
            if len(frame)<150:
                # Follow the official XLS link using the SAME cookie session.
                soup=BeautifulSoup(response.text,'lxml')
                link=next((a.get('href') for a in soup.find_all('a',href=True) if a.get_text(' ',strip=True).upper()=='XLS'),None)
                if link:
                    export=session.get(urljoin(response.url,link),timeout=35);export.raise_for_status()
                    frame=_parse_xls(export.content,day,export.url)
            if len(frame)<150:raise RuntimeError(f'only {len(frame)} parsed rows')
            all_days.append(frame)
        except Exception as exc:diagnostics.append(f'Day {day}: {exc}')
    if diagnostics:raise RuntimeError(' | '.join(diagnostics))
    result=pd.concat(all_days,ignore_index=True)
    if len(result)<700 or result.lot.duplicated().any():
        raise RuntimeError(f'Incomplete or duplicate sale: {len(result)} rows, {result.lot.duplicated().sum()} duplicates')
    return result

def catalogue_xls():
    # XLS fallback is integrated into catalogue_html to preserve the same session.
    return pd.DataFrame()

def load_comparables():
    """Optional licensed, automatically supplied CSV; never required for catalogue ingestion.
    Required: sire, sex, price_gns, sale_year. This is NOT user entry: plug in an authorised export/feed.
    """
    f=OUT/'licensed_sales_history.csv'
    if not f.exists():return pd.DataFrame()
    df=pd.read_csv(f)
    required={'sire','sex','price_gns','sale_year'}
    return df if required.issubset(df.columns) else pd.DataFrame()

def rank(df):
    df=df.copy()
    for col in ['sire','dam','sex','consignor']:
        df[col]=df[col].fillna('').astype(str).str.strip()
    df=df.drop_duplicates('lot').sort_values('lot').reset_index(drop=True)
    # Transparent screening heuristics only; never pass these off as predictive racing probabilities.
    sire_count=df.groupby('sire')['lot'].transform('count')
    sire_count=sire_count.clip(lower=1)
    df['sire_catalogue_count']=sire_count
    # Sire frequency is a catalogue feature, NOT a proxy for stallion merit.
    # Unverified family merit and racing outcomes are deliberately left unscored.
    df['racing_score']=pd.NA
    df['pinhook_score']=pd.NA
    df['estimated_value_gns']=pd.NA
    df['max_bid_gns']=pd.NA
    df['confidence']='insufficient linked performance / comparables'
    df['pedigree_review_priority']=df['pedigree_update'].astype(int)*2 + (sire_count<=3).astype(int)
    df['inspection_priority']=df['pedigree_review_priority'].where(~df['withdrawn'],-1)
    df['reason']=df.apply(lambda r: ('WITHDRAWN; ' if r.withdrawn else '')+
        ('Pedigree update flagged; ' if r.pedigree_update else '')+
        ('Low catalogue sire representation; ' if r.sire_catalogue_count<=3 else '')+
        'requires verified performance and physical inspection',axis=1)
    comp=load_comparables()
    if len(comp):
        comp=comp.copy()
        comp['price_gns']=pd.to_numeric(comp['price_gns'],errors='coerce')
        comp=comp[(comp.price_gns>0)&(comp.sale_year.between(2022,2025))]
        comp['sire_key']=comp.sire.astype(str).str.replace(r'\s*\([^)]*\)','',regex=True).str.casefold().str.strip()
        df['sire_key']=df.sire.str.replace(r'\s*\([^)]*\)','',regex=True).str.casefold().str.strip()
        for i,row in df.iterrows():
            subset=comp[(comp.sire_key==row.sire_key)&(comp.sex.str.casefold()==str(row.sex).casefold())]
            if len(subset)>=8:
                df.at[i,'comparable_median_gns']=round(subset.price_gns.median())
                df.at[i,'comparable_n']=len(subset)
                df.at[i,'confidence']='sire/sex historical median only; not a lot valuation'
    return df.sort_values(['withdrawn','inspection_priority','lot'],ascending=[True,False,True])

def main():
    OUT.mkdir(exist_ok=True)
    errors=[]
    for source in (catalogue_html,catalogue_xls):
        try:
            df=source()
            if len(df)>=100:break
            errors.append(f'{source.__name__}: only {len(df)} parsed rows')
        except Exception as exc:errors.append(f'{source.__name__}: {exc}')
    else:
        raise RuntimeError('Official catalogue could not be parsed. No rankings fabricated. '+ ' | '.join(errors))
    if not (df['lot'].astype(str).str.match(r'^\d{3,4}[A-Z]?$')).all():
        raise RuntimeError('Unexpected lot numbers: refusing to publish output')
    ranked=rank(df)
    ranked.to_csv(OUT/'all_lots.csv',index=False)
    ranked[~ranked.withdrawn].head(30).to_csv(OUT/'inspection_shortlist.csv',index=False)
    with pd.ExcelWriter(OUT/'book2_shortlist.xlsx',engine='openpyxl') as writer:
        ranked.to_excel(writer,index=False,sheet_name='All lots')
        ranked[~ranked.withdrawn].head(30).to_excel(writer,index=False,sheet_name='Inspection priorities')
        pd.DataFrame([{'note':'Screening priority is NOT a predicted racing score or valuation. Do not bid based on it alone.'},
                      {'note':'No invented progeny statistics, expected hammer prices or profit projections.'}]).to_excel(writer,index=False,sheet_name='Methodology')
    manifest={'retrieved_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
      'source':BASE,'rows':len(ranked),'withdrawn':int(ranked.withdrawn.sum()),
      'data_sha256':hashlib.sha256(df.to_csv(index=False).encode()).hexdigest(),
      'status':'catalogue_screen_only','warnings':errors}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest,indent=2))
if __name__=='__main__':main()
