import json
import pathlib
import pandas as pd
import streamlit as st
from engine import main, OUT

st.set_page_config(page_title='Book 2 | Bloodstock Value Engine', layout='wide')
st.title('Tattersalls Book 2 — Bloodstock Value Engine')
st.caption('Official catalogue screening • No validated racing predictions or lot valuations yet')

manifest_file = OUT / 'manifest.json'
file = OUT / 'all_lots.csv'

def load_manifest():
    if manifest_file.exists():
        try:
            return json.loads(manifest_file.read_text())
        except (OSError, ValueError):
            pass
    return None

if 'last_refresh_error' not in st.session_state:
    st.session_state.last_refresh_error = None

if not file.exists():
    with st.spinner('Attempting initial official catalogue import...'):
        try:
            main()
            st.session_state.last_refresh_error = None
        except Exception as exc:
            st.session_state.last_refresh_error = str(exc)

if st.button('Refresh official catalogue'):
    with st.spinner('Fetching and validating the official catalogue...'):
        try:
            main()
            st.session_state.last_refresh_error = None
            st.success('New catalogue imported successfully.')
        except Exception as exc:
            st.session_state.last_refresh_error = str(exc)

manifest = load_manifest()
if st.session_state.last_refresh_error:
    st.error('Latest refresh FAILED. Any rows shown below are from a PREVIOUS saved import, not a successful live refresh.')
    with st.expander('Importer error details'):
        st.code(st.session_state.last_refresh_error)

if manifest:
    st.info(f"Last successful saved import (UTC): {manifest.get('retrieved_utc', 'unknown')} | Source: {manifest.get('source', 'unknown')} | Rows: {manifest.get('rows', 'unknown')}")
    if manifest.get('warnings'):
        with st.expander('Warnings from successful import'):
            st.write(manifest['warnings'])
elif file.exists():
    st.warning('Saved catalogue rows exist, but no import manifest was found. Freshness cannot be verified.')

if not file.exists():
    st.warning('No validated catalogue has been saved yet. The importer needs repair before rankings can be generated.')
    st.stop()

try:
    df = pd.read_csv(file, dtype={'lot': str})
except Exception as exc:
    st.error(f'Unable to read saved catalogue: {exc}')
    st.stop()

required = {'lot', 'sire', 'dam', 'withdrawn', 'pedigree_update'}
if not required.issubset(df.columns):
    st.error(f'Saved file is missing columns: {sorted(required - set(df.columns))}')
    st.stop()

c1, c2, c3 = st.columns(3)
c1.metric('Saved entries', len(df))
c2.metric('Withdrawn', int(df['withdrawn'].fillna(False).sum()))
c3.metric('Pedigree updates', int(df['pedigree_update'].fillna(False).sum()))

show = st.checkbox('Include withdrawn', False)
if not show:
    df = df[~df['withdrawn'].fillna(False)]
sire = st.multiselect('Sire filter', sorted(df['sire'].dropna().unique()))
if sire:
    df = df[df['sire'].isin(sire)]
st.dataframe(df, hide_index=True, use_container_width=True)
st.download_button('Download filtered CSV', df.to_csv(index=False), 'book2_filtered.csv')
st.warning('These are catalogue screening records, NOT validated racing or pinhooking value rankings. Do not use them to set bids.')
