"""Book 2 iPad-friendly dashboard. Keeps existing engine.py unchanged."""
import json
import pathlib
import pandas as pd
import streamlit as st
from engine import main, OUT

st.set_page_config(page_title='Book 2 | Bloodstock Value Engine', page_icon='🐎', layout='wide')
st.title('🐎 Bloodstock Value Engine')
st.caption('Tattersalls October Book 2 • Catalogue screening, not validated valuation or racing prediction')
OUT.mkdir(parents=True, exist_ok=True)
manifest_file = OUT / 'manifest.json'
file = OUT / 'all_lots.csv'

if 'last_refresh_error' not in st.session_state:
    st.session_state.last_refresh_error = None
if 'inspection_notes' not in st.session_state:
    st.session_state.inspection_notes = {}

def refresh():
    try:
        main()
        st.session_state.last_refresh_error = None
        return True
    except Exception as exc:
        st.session_state.last_refresh_error = str(exc)
        return False

if not file.exists():
    with st.spinner('Importing official catalogue...'):
        refresh()

col_a, col_b = st.columns([1, 3])
with col_a:
    if st.button('↻ Refresh catalogue', use_container_width=True):
        with st.spinner('Fetching all Book 2 sessions...'):
            if refresh():
                st.success('Catalogue imported successfully')
            else:
                st.error('Refresh failed; saved data retained')

if st.session_state.last_refresh_error:
    st.error('Latest refresh failed. Any displayed records are from the last saved import.')
    with st.expander('Import error details'):
        st.code(st.session_state.last_refresh_error)

if not file.exists():
    st.warning('No catalogue data yet. Check the importer error above.')
    st.stop()
try:
    raw = pd.read_csv(file, dtype={'lot': str})
except Exception as exc:
    st.error(f'Cannot read catalogue: {exc}')
    st.stop()
required = {'lot', 'sire', 'dam', 'withdrawn', 'pedigree_update'}
if not required.issubset(raw.columns):
    st.error(f'Catalogue missing required columns: {sorted(required - set(raw.columns))}')
    st.stop()

for flag in ('withdrawn', 'pedigree_update'):
    raw[flag] = raw[flag].astype(str).str.strip().str.lower().isin(['true', '1', 'yes'])
raw['lot'] = raw['lot'].fillna('').astype(str).str.strip()
raw = raw[raw['lot'].ne('')].drop_duplicates('lot').copy()
for name in ('sire','dam','sex','consignor','stabling'):
    if name not in raw:
        raw[name] = ''
    raw[name] = raw[name].fillna('').astype(str)
if 'day' not in raw:
    raw['day'] = pd.NA

try:
    manifest = json.loads(manifest_file.read_text()) if manifest_file.exists() else {}
except (ValueError, OSError):
    manifest = {}
st.caption(f"Last successful import (UTC): {manifest.get('retrieved_utc', 'unverified')} • Source: {manifest.get('source', 'unknown')}")
if manifest.get('warnings'):
    with st.expander('Import warnings'):
        st.write(manifest['warnings'])

active = raw.loc[~raw.withdrawn].copy()
m1,m2,m3,m4 = st.columns(4)
m1.metric('Catalogue lots', len(raw))
m2.metric('Active lots', len(active))
m3.metric('Withdrawn', int(raw.withdrawn.sum()))
m4.metric('Pedigree updates', int(raw.pedigree_update.sum()))

st.info('Scores and valuations require independently verified racing outcomes and comparable transactions. Current priority lists are catalogue review queues only.')

tab_r, tab_p, tab_i, tab_all = st.tabs(['🏇 Racing research', '📈 Pinhooking research', '📝 My inspections', '📚 Full catalogue'])

# Both research queues are explicitly heuristic; catalogue signals alone cannot estimate racing merit or profit.
active['review_flag'] = active.pedigree_update.astype(int)
active['sire_count'] = active.groupby('sire')['lot'].transform('size')
active['research_priority'] = active['review_flag'] * 2 + (active['sire_count'] <= 3).astype(int)
active = active.sort_values(['research_priority','lot'], ascending=[False,True])
show_cols = [x for x in ['lot','day','sire','dam','sex','consignor','stabling','pedigree_update','research_priority'] if x in active.columns]

with tab_r:
    st.subheader('Top 20 — pedigree review queue')
    st.caption('Sorted by pedigree-update flag and low sire representation in this catalogue. NOT a ranking of expected racing ability.')
    st.dataframe(active.head(20)[show_cols], hide_index=True, use_container_width=True)
    st.download_button('Download racing research queue', active.head(20)[show_cols].to_csv(index=False), 'book2_racing_research.csv', mime='text/csv')
    st.warning('No validated racing score is available yet. A pedigree update is a prompt to investigate, not evidence of ability.')

with tab_p:
    st.subheader('Top 20 — commercial review queue')
    st.caption('Provisional catalogue-review queue only. Without sale comparables and resale-market data, this cannot identify undervaluation or profit.')
    st.dataframe(active.head(20)[show_cols], hide_index=True, use_container_width=True)
    st.download_button('Download commercial research queue', active.head(20)[show_cols].to_csv(index=False), 'book2_pinhook_research.csv', mime='text/csv')
    st.warning('This list currently shares the same catalogue-only ordering as racing research. No pinhooking valuation is implied.')

with tab_i:
    st.subheader('Inspection notebook')
    st.caption('Notes are held in this browser session only. Download the CSV to keep them; cloud-persistent notes need a database.')
    options = active['lot'].tolist()
    if options:
        lot = st.selectbox('Choose a lot', options, format_func=lambda x: f"Lot {x} — {active.loc[active.lot.eq(x),'sire'].iloc[0]} / {active.loc[active.lot.eq(x),'dam'].iloc[0]}")
        current = st.session_state.inspection_notes.get(lot, {})
        with st.form('inspection_form'):
            rating = st.selectbox('Physical impression', ['Not inspected','Strong','Interesting','Average','Pass'], index=['Not inspected','Strong','Interesting','Average','Pass'].index(current.get('rating','Not inspected')))
            notes = st.text_area('Conformation, walk, temperament, vet questions', value=current.get('notes',''), height=130)
            shortlist = st.checkbox('Keep on inspection shortlist', value=current.get('shortlist',True))
            if st.form_submit_button('Save note in this session'):
                st.session_state.inspection_notes[lot] = {'lot':lot,'rating':rating,'notes':notes,'shortlist':shortlist}
                st.success(f'Lot {lot} saved in this session. Download notes before leaving.')
    note_df = pd.DataFrame(list(st.session_state.inspection_notes.values()), columns=['lot','rating','notes','shortlist'])
    st.dataframe(note_df, hide_index=True, use_container_width=True)
    st.download_button('Download my inspection notes CSV', note_df.to_csv(index=False), 'book2_my_inspections.csv', mime='text/csv')

with tab_all:
    st.subheader('Search all lots')
    query = st.text_input('Search lot number, sire, dam or consignor')
    include_withdrawn = st.checkbox('Include withdrawn lots', False)
    shown = raw if include_withdrawn else raw.loc[~raw.withdrawn]
    if query.strip():
        searchable = shown[['lot','sire','dam','consignor']].astype(str).agg(' '.join, axis=1)
        shown = shown.loc[searchable.str.contains(query.strip(), case=False, regex=False)]
    st.caption(f'{len(shown)} matching lots')
    st.dataframe(shown, hide_index=True, use_container_width=True)
    st.download_button('Download filtered catalogue', shown.to_csv(index=False), 'book2_filtered.csv', mime='text/csv')
    
st.divider()
st.subheader("Historical Sales — V3 Test")
st.caption("Test official Tattersalls Book 2 results for 2023–2025.")

if st.button("Test historical sales import"):
    from history import main as import_history

    with st.spinner("Checking historical Tattersalls results..."):
        try:
            historical = import_history()
            st.success(
                f"Imported {len(historical)} verified sale records."
            )
            st.dataframe(historical.head(20))
        except Exception as exc:
            st.error("Historical import could not be completed.")
            st.code(str(exc))

        status_file = OUT / "historical_import_status.json"
        if status_file.exists():
            st.subheader("Import diagnostics")
            st.json(json.loads(status_file.read_text()))

st.divider()
st.subheader("Tattersalls Connection Diagnostic")

if st.button("Inspect Tattersalls response"):
    import requests
    from bs4 import BeautifulSoup
    from history import sale_url

    url = sale_url(2025)

    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
            timeout=30
        )

        soup = BeautifulSoup(response.text, "lxml")

        st.write("HTTP status:", response.status_code)
        st.write("Final URL:", response.url)
        st.write("Page title:", soup.title.get_text(strip=True) if soup.title else "None")
        st.write("Number of table rows:", len(soup.select("tr")))
        st.write("Number of table cells:", len(soup.select("td")))

        st.subheader("First 15 table rows")
        for tr in soup.select("tr")[:15]:
            cells = tr.find_all(["th", "td"], recursive=False)
            st.write([
                cell.get_text(" ", strip=True)[:150]
                for cell in cells
            ])

        st.subheader("Response preview")
        st.code(soup.get_text(" ", strip=True)[:1500])

    except Exception as exc:
        st.error(str(exc))

