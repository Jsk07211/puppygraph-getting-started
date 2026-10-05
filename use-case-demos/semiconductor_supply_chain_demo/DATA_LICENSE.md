# Data Licences

The code in this demo is covered by the repository's Apache 2.0 licence. The data has its own terms.

## Real data: CEPII BACI

`csv_data/country.csv`, `csv_data/product.csv` and `csv_data/trade_flow.csv` are derived from CEPII BACI (HS17, version 202601, released 2026-01-22). They were filtered to semiconductor and AI server products and flows of at least $10M, and Taiwan was relabelled from `S19` to `TWN`.

- Source: CEPII, https://www.cepii.fr/CEPII/en/bdd_modele/bdd_modele_item.asp?id=37
- Licence: Etalab Open Licence 2.0 (Licence Ouverte 2.0), https://www.etalab.gouv.fr/licence-ouverte-open-licence/
- Citation: Gaulier, G. and Zignago, S. (2010). *BACI: International Trade Database at the Product-Level. The 1994-2007 Version.* CEPII Working Paper N°2010-23.

CEPII does not endorse this demo.

## Synthetic data

All `csv_data/synthetic_*` files and `scripts/reference/company_names.json` were created for this demo and are covered by the repository's Apache 2.0 licence. They describe fictional companies, facilities, products and events. See the Dataset section of the [README](README.md).
