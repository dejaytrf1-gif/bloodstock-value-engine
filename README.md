# Bloodstock Value Engine — Tattersalls Book 2, October 2026

## First working version

- Fetches the official Tattersalls Book 2 catalogue from https://db.tattersalls.com/4DCGI/Sale/OC2%2026
- Tries to parse the public lot table and falls back to its linked XLS export.
- Captures lot, sire, dam, sex, consignor, stabling, withdrawals and pedigree-update flags where present.
- Produces `output/all_lots.csv`, `output/inspection_shortlist.csv`, `output/book2_shortlist.xlsx`, and `output/manifest.json`.
- Gives an **inspection priority**, not a bogus racing or valuation score. The engine deliberately leaves racing and pinhook scores blank until verified data is available.
- Optional licensed historical sale export at `output/licensed_sales_history.csv` can supply sire/sex comparable medians (8+ records). These are labelled descriptive medians, not lot valuations.

## Run locally (Mac / Windows / Linux)

```bash
python -m pip install -r requirements.txt
python engine.py
streamlit run dashboard.py
```

A computer with internet access is required. This package was syntax-tested, but live Tattersalls access could not be tested in the authoring environment. The official site may change its HTML, restrict automation or require permission; respect site terms, request limits and licensing. If the importer fails, it exits with an error rather than inventing lots.

## Automatic scheduling (on your own machine)

Run `python engine.py` from a scheduler such as cron, Task Scheduler, or a cloud job. The provided package does **not** set up a hosted background service by itself.

## Next data requirements

To produce defensible racing and pinhook rankings, add authorised historical sales data with dates, sire, sex, consignor and hammer prices; linked progeny racing outcomes with runner counts; and pedigree family performance. Backtest against prior sale years with time-based holdouts and price uncertainty. Physical inspection, veterinary assessment, buyer costs and realistic resale route remain mandatory.
