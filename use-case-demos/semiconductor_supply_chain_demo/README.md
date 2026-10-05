## Prerequisites:
- Docker
- Docker Compose
- Python 3 (only to rebuild the data)

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

## Running the Demo

1. Start the services and load the data into Iceberg:
```bash
./init.sh
```
This starts the containers, converts `csv_data/` to Parquet, creates the Iceberg tables and checks that every table loaded completely. It runs entirely in Docker, takes under a minute, and is safe to re-run.

2. Create the graph schema in PuppyGraph:
   - Open http://localhost:8081 and sign in (username `puppygraph`, password `puppygraph123`).
   - Build the schema with PuppyGraph's schema builder, following [SCHEMA.md](SCHEMA.md) for the catalog connection, vertices and edges.

3. Run the queries in [QUERIES.md](QUERIES.md): SQL for simple questions, Cypher for the multi-hop ones.

To stop the demo, run `docker compose down`. Add `-v` to also delete the loaded tables.

## Rebuilding the Data (Optional)

The ready-to-use data is already in `csv_data/`. To rebuild it, install the Python dependencies and run the two scripts, then run `./init.sh` again:
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Real data: download and filter CEPII BACI trade flows (reads ~800 MB remotely; takes a few minutes)
python3 scripts/fetch_baci.py --out csv_data

# Synthetic data: generate the fictional network, calibrated to the real trade flows.
# The generator validates the data and writes nothing if any check fails.
python3 scripts/generate.py --scale small --seed 42 --out csv_data
```
The same seed and scale always produce identical files. `--scale large` creates a network about 8 times bigger for performance testing; its money totals are not calibrated to real market sizes.

## Project Layout

| Path | Purpose |
|---|---|
| `csv_data/` | Real tables (`country`, `product`, `trade_flow`) and synthetic tables (`synthetic_*`) |
| `scripts/fetch_baci.py` | Downloads and filters the real BACI trade data |
| `scripts/generate.py` | Generates and validates the synthetic network |
| `scripts/reference/company_names.json` | Fixed list of screened fictional company names used by the generator |
| `init.sh` | Starts the services and loads the data into Iceberg |
| `init.sql` | Iceberg table definitions, run by `init.sh` |
| `SCHEMA.md` | Recommended PuppyGraph graph schema over the Iceberg tables |
| `QUERIES.md` | SQL and Cypher queries for each question |
| `DATA_LICENSE.md` | Licences for the data |
