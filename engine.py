"""Tattersalls Book 2 catalogue importer and transparent screening model.
Run: python engine.py ; dashboard: streamlit run dashboard.py
No fabricated racing statistics or valuation estimates.
"""
import io, re, json, datetime, pathlib, hashlib
from urllib.parse import urljoin
import requests
import pandas as pd
from bs4 import BeautifulSoup

BASE='https://db.tattersalls.com/4DCGI/Sale/OC2%2026'
OUT=pathlib.Path(__file__).resolve().parent/'output'
HEADERS={'User-Agent':'Mozilla/5.0 (compatible; BloodstockResearch/1.0; personal analysis)'}

def get(url):
    r=requests.get(url,headers=HEADERS,timeout=35);r.raise_for_status();return r

def catalogue_html():
    r=get(BASE); soup=BeautifulSoup(r.text,'lxml')
    for tag in soup(['script','style']):tag.decompose()
    tables=soup.find_all('table')
    best=[]
    for table in tables:
        rows=[]
        for tr in table.find_all('tr'):
            cells=tr.find_all(['td'],recursive=False)
            if len(cells)<3:continue
            cols=[c.get_text(' ',strip=True) for c in cells]
            m=re.search(r'\b(\d{3,4}[A-Z]?)\b',cols[0])
            if not m:continue
            pedigree=cols[1]
            if '/' not in pedigree:continue
            sire,rest=pedigree.split('/',1)
            dam=re.split(r'\b(?:B|Ch|Gr|Br|Ro|Blk|B/Gr|B/Br)\.(?:C|F|G)\.',rest,maxsplit=1)[0]
            sexmatch=re.search(r'\b(?:B|Ch|Gr|Br|Ro|Blk|B/Gr|B/Br)\.(C|F|G)\.',rest)
            lot=m.group(1)
            rows.append({'lot':lot,'sire':sire.strip(),'dam':dam.strip(),
                         'sex':{'C':'Colt','F':'Filly','G':'Gelding'}.get(sexmatch.group(1),'') if sexmatch else '',
                         'consignor':cols[2] if len(cols)>2 else '',
                         'stabling':cols[3] if len(cols)>3 else '',
                         'withdrawn':'withdrawn' in pedigree.lower(),
                         'pedigree_update':'UPDATE' in pedigree,
                         'source_url':BASE,'source_type':'official_catalogue'})
        if len(rows)>len(best):best=rows
    return pd.DataFrame(best)

def catalogue_xls():
    html=get(BASE).text
    soup=BeautifulSoup(html,'lxml')
    for a in soup.find_all('a',href=True):
        if a.get_text(' ',strip=True).upper()!='XLS':continue
        url=urljoin(BASE,a['href'])
        r=get(url)
        try:
            frames=pd.read_excel(io.BytesIO(r.content),sheet_name=None)
            for frame in frames.values():
                frame.columns=[str(x).strip().lower() for x in frame.columns]
                cols=frame.columns
                def pick(*opts):
                    return next((x for x in opts if x in cols),None)
                lot,sire,dam=pick('lot','lot no','lot number'),pick('sire'),pick('dam')
                if not all([lot,sire,dam]):continue
                out=pd.DataFrame({'lot':frame[lot].astype(str).str.replace(r'\.0$','',regex=True),
                  'sire':frame[sire].astype(str),'dam':frame[dam].astype(str),
                  'sex':frame[pick('sex')].astype(str) if pick('sex') else '',
                  'consignor':frame[pick('consignor','vendor')].astype(str) if pick('consignor','vendor') else '',
                  'stabling':frame[pick('stabling')].astype(str) if pick('stabling') else '',
                  'withdrawn':False,'pedigree_update':False,'source_url':url,'source_type':'official_xls'})
                if len(out)>100:return out
        except Exception:pass
    return pd.DataFrame()

def source_diagnostics():
    """Report response structure without exposing cookies or credentials."""
    try:
        r=get(BASE)
        soup=BeautifulSoup(r.content,'lxml')
        tables=soup.find_all('table')
        anchors=soup.find_all('a',href=True)
        xls=[a.get('href','') for a in anchors if 'xls' in a.get_text(' ',strip=True).lower() or 'xls' in a.get('href','').lower()]
        title=soup.title.get_text(' ',strip=True)[:100] if soup.title else '(none)'
        return ('source diagnostic: HTTP '+str(r.status_code)+
                '; final_host='+str(requests.utils.urlparse(r.url).hostname)+
                '; content_type='+str(r.headers.get('content-type','unknown'))[:80]+
                '; bytes='+str(len(r.content))+
                '; tables='+str(len(tables))+
                '; rows='+str(sum(len(t.find_all('tr')) for t in tables))+
                '; links='+str(len(anchors))+
                '; xls_links='+str(len(xls))+
                '; title='+title)
    except Exception as exc:
        return 'source diagnostic failed: '+type(exc).__name__+': '+str(exc)[:180]

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
        raise RuntimeError('Official catalogue could not be parsed. No rankings fabricated. '+ ' | '.join(errors) + ' | ' + source_diagnostics())
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
