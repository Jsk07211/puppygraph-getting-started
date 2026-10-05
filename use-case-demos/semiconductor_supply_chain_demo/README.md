## Prerequisites:
- Docker
- Docker Compose
- Python 3

## Dataset

This demo combines **real** country-level trade data with a **synthetic** network of fictional companies generated to match it. Real tables have no prefix; synthetic tables start with `synthetic_`.

### Real data

| Table | Contents |
|---|---|
| `country` | Countries and ISO codes |
| `product` | Traded products (HS codes) in the chip and AI server supply chain: polysilicon, doped wafers, chip-making equipment, discrete semiconductors, integrated circuits, servers and computer parts |
| `trade_flow` | Annual exporter → importer trade value and quantity per product, 2017–2024, flows of $10M or more |

Source: CEPII BACI, HS17, version 202601 (released 2026-01-22), Etalab Open Licence 2.0. Gaulier, G. and Zignago, S. (2010), CEPII Working Paper N°2010-23. Taiwan, reported by BACI as "Other Asia, n.e.s." (`S19`), is relabelled `TWN`.

Limits of the real data:
- Trade is not production. Re-export hubs such as Singapore and Malaysia appear as large exporters even when goods were made elsewhere.
- HS codes do not separate AI chips from other chips: processors (854231) include AI accelerators, and memory (854232) includes HBM.

### Synthetic data

Everything in a `synthetic_` table is fictional: companies, facilities, chip parts, AI servers, supply contracts, restrictions and disruption events. None of it describes a real company, contract or event, and disruption events are hypothetical scenarios, not forecasts.

The synthetic network is invented but shaped by real information:
- Suppliers' countries are weighted by real BACI trade flows, and server assembly plants are placed in proportion to real BACI server exports. The generator checks that cross-border equipment contracts track the real flows.
- Facilities are placed in real chip-industry cities; the facilities themselves are fictional.
- Company names come from a fixed list of fictional names (`scripts/reference/company_names.json`), each screened against real company names and entities on the US Consolidated Screening List.

**Any figure computed from a `synthetic_` table is illustrative, even if real data is also involved.**

## Demo Data Preparation

The ready-to-use data is already in `csv_data/`, so you can go straight to step 3. Steps 1 and 2 show how to rebuild it.

1. (Optional) Set up a virtual environment and install the dependencies:
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

2. (Optional) Rebuild the data:
```bash
# Real data: download and filter CEPII BACI trade flows (reads ~800 MB remotely; takes a few minutes)
python3 scripts/fetch_baci.py --out csv_data

# Synthetic data: generate the fictional network, calibrated to the real trade flows.
# The generator validates the data and writes nothing if any check fails.
python3 scripts/generate.py --scale small --seed 42 --out csv_data
```
The same seed and scale always produce identical files. `--scale large` creates a network about 8 times bigger for performance testing; its money totals are not calibrated to real market sizes.

3. Convert the CSV files to Parquet:
```bash
python3 CsvToParquet.py ./csv_data ./parquet_data
```

4. Start the services and load the tables into Iceberg:
```bash
docker compose up -d
docker exec -i spark-iceberg spark-sql < init.sql
```

5. Upload the graph schema to PuppyGraph:
   - Open http://localhost:8081 and sign in (username `puppygraph`, password `puppygraph123`).
   - Upload `schema.json`.

6. Run the queries in [QUERIES.md](QUERIES.md): SQL for simple questions, Cypher for the multi-hop ones.

## Project Layout

| Path | Purpose |
|---|---|
| `csv_data/` | Real tables (`country`, `product`, `trade_flow`) and synthetic tables (`synthetic_*`) |
| `scripts/fetch_baci.py` | Downloads and filters the real BACI trade data |
| `scripts/generate.py` | Generates and validates the synthetic network |
| `scripts/reference/company_names.json` | Fixed list of screened fictional company names used by the generator |
| `init.sql` | Creates the Iceberg tables and loads the Parquet files |
| `schema.json` | PuppyGraph graph schema over the Iceberg tables |
| `QUERIES.md` | SQL and Cypher queries for each question |
| `DATA_LICENSE.md` | Licences for the data |
