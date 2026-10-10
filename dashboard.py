import pathlib
import pandas as pd
import streamlit as st
from engine import main, OUT
st.set_page_config(page_title='Book 2 | Bloodstock Value Engine',layout='wide')
st.title('Tattersalls Book 2 — Bloodstock Value Engine')
st.caption('Official catalogue screening • Racing and pinhook valuation awaiting licensed outcome/comparable data')
if not (OUT/'all_lots.csv').exists():
    with st.spinner('Importing official catalogue for the first time...'):
        try: main()
        except Exception as e: st.warning(f'Automatic import unavailable: {e}')
if st.button('Refresh official catalogue'):
    try:main();st.success('Catalogue refreshed')
    except Exception as e:st.error(str(e))
f=OUT/'all_lots.csv'
if not f.exists():
    st.info('Click Refresh official catalogue to import the lots. No manual entry required.')
else:
    df=pd.read_csv(f)
    c1,c2,c3=st.columns(3)
    c1.metric('Imported entries',len(df));c2.metric('Withdrawn',int(df.withdrawn.sum()));c3.metric('Pedigree updates',int(df.pedigree_update.sum()))
    show=st.checkbox('Include withdrawn',False)
    if not show:df=df[~df.withdrawn]
    sire=st.multiselect('Sire filter',sorted(df.sire.dropna().unique()))
    if sire:df=df[df.sire.isin(sire)]
    st.dataframe(df,hide_index=True,use_container_width=True)
    st.download_button('Download filtered CSV',df.to_csv(index=False),'book2_filtered.csv')
    st.warning('Inspection priority is not a prediction of racing ability or value. No financial bidding recommendations are produced without verified comparables.')
