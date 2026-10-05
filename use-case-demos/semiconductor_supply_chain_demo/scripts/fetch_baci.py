"""Download and filter real trade data from CEPII BACI.

BACI reports annual bilateral trade flows (exporter, importer, product, value,
quantity). This script reads the pinned BACI release, keeps only products in the
semiconductor and AI server supply chain, drops small flows, and writes three
tables to the output folder:

    country.csv     iso3, iso2, name
    product.csv     hs_code, description, stage
    trade_flow.csv  year, exporter, importer, hs_code, value_usd, quantity_tonnes

The BACI archive is ~800 MB. Only the members we need are read, using HTTP range
requests, so a full download is not required. Zip CRC checks run on every member
read, so a corrupted transfer fails instead of producing bad data.

Source: CEPII BACI (Etalab Open Licence 2.0). Gaulier, G. and Zignago, S. (2010),
CEPII Working Paper N°2010-23.

Usage:
    python3 scripts/fetch_baci.py --out csv_data
"""
from __future__ import annotations

import argparse
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

BACI_VERSION = "202601"
HS_REVISION = "HS17"
BACI_URL = f"https://www.cepii.fr/DATA_DOWNLOAD/baci/data/BACI_{HS_REVISION}_V{BACI_VERSION}.zip"
YEARS = range(2017, 2025)

# Flows below this value (USD) are dropped to keep the graph readable.
MIN_FLOW_USD = 10_000_000

# HS code prefix -> supply chain stage.
PRODUCT_STAGES = {
    "280461": "material",   # polysilicon
    "3818": "material",     # doped silicon wafers
    "8486": "equipment",    # chip-making equipment
    "8541": "chip",         # discrete semiconductors
    "8542": "chip",         # integrated circuits (processors, memory, ...)
    "847150": "server",     # servers / processing units
    "847330": "server",     # computer parts, including GPU boards
}

# BACI reports Taiwan as "Other Asia, n.e.s." (S19).
ISO3_OVERRIDES = {"S19": ("TWN", "TW", "Taiwan")}


class HttpRangeFile(io.RawIOBase):
    """Read-only, seekable file over HTTP range requests."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.pos = 0
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD")) as resp:
            self.size = int(resp.headers["Content-Length"])

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self.pos, io.SEEK_END: self.size}[whence]
        self.pos = base + offset
        return self.pos

    def readinto(self, buffer) -> int:
        if self.pos >= self.size:
            return 0
        end = min(self.pos + len(buffer), self.size) - 1
        request = urllib.request.Request(self.url, headers={"Range": f"bytes={self.pos}-{end}"})
        with urllib.request.urlopen(request) as resp:
            data = resp.read()
        buffer[: len(data)] = data
        self.pos += len(data)
        return len(data)


def find_member(archive: zipfile.ZipFile, fragment: str) -> str:
    matches = [name for name in archive.namelist() if fragment in name]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one archive member matching {fragment!r}, found {matches}")
    return matches[0]


def read_trade_year(archive: zipfile.ZipFile, year: int) -> pd.DataFrame:
    member = find_member(archive, f"_Y{year}_")
    prefixes = tuple(PRODUCT_STAGES)
    kept = []
    with archive.open(member) as handle:
        for chunk in pd.read_csv(handle, dtype={"k": str}, chunksize=2_000_000):
            chunk["k"] = chunk["k"].str.zfill(6)
            kept.append(chunk[chunk["k"].str.startswith(prefixes)])
    return pd.concat(kept, ignore_index=True)


def build_countries(archive: zipfile.ZipFile) -> tuple[pd.DataFrame, dict[int, str]]:
    raw = pd.read_csv(archive.open(find_member(archive, "country_codes")), keep_default_na=False)
    rows = []
    for rec in raw.itertuples():
        iso3, iso2, name = ISO3_OVERRIDES.get(
            rec.country_iso3, (rec.country_iso3, rec.country_iso2, rec.country_name)
        )
        rows.append({"code": rec.country_code, "iso3": iso3, "iso2": iso2, "name": name})
    table = pd.DataFrame(rows)
    code_to_iso3 = dict(zip(table["code"], table["iso3"]))
    countries = table.drop(columns="code").drop_duplicates("iso3").sort_values("iso3")
    return countries, code_to_iso3


def build_products(archive: zipfile.ZipFile, hs_codes: set[str]) -> pd.DataFrame:
    raw = pd.read_csv(archive.open(find_member(archive, "product_codes")), dtype={"code": str})
    raw["code"] = raw["code"].str.zfill(6)
    products = raw[raw["code"].isin(hs_codes)].rename(columns={"code": "hs_code"})
    products["stage"] = [
        next(stage for prefix, stage in PRODUCT_STAGES.items() if code.startswith(prefix))
        for code in products["hs_code"]
    ]
    return products[["hs_code", "description", "stage"]].sort_values("hs_code")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path("csv_data"), help="output folder (default: csv_data)")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    print(f"Reading {BACI_URL}")
    archive = zipfile.ZipFile(io.BufferedReader(HttpRangeFile(BACI_URL), buffer_size=8 * 1024 * 1024))

    countries, code_to_iso3 = build_countries(archive)

    flows = []
    for year in YEARS:
        year_flows = read_trade_year(archive, year)
        print(f"  {year}: {len(year_flows):,} semiconductor-related flows")
        flows.append(year_flows)
    trade = pd.concat(flows, ignore_index=True)

    trade = pd.DataFrame({
        "year": trade["t"],
        "exporter": trade["i"].map(code_to_iso3),
        "importer": trade["j"].map(code_to_iso3),
        "hs_code": trade["k"],
        "value_usd": (trade["v"] * 1000).round().astype("int64"),  # BACI values are in thousand USD
        "quantity_tonnes": pd.to_numeric(trade["q"], errors="coerce").round(3),
    })
    if trade[["exporter", "importer"]].isna().any().any():
        raise RuntimeError("Some BACI country codes have no ISO3 mapping")
    trade = trade[trade["value_usd"] >= MIN_FLOW_USD].sort_values(["year", "hs_code", "exporter", "importer"])

    products = build_products(archive, set(trade["hs_code"]))
    used = set(trade["exporter"]) | set(trade["importer"])
    countries = countries[countries["iso3"].isin(used)]

    countries.to_csv(args.out / "country.csv", index=False)
    products.to_csv(args.out / "product.csv", index=False)
    trade.to_csv(args.out / "trade_flow.csv", index=False)
    print(
        f"Wrote {len(countries)} countries, {len(products)} products and "
        f"{len(trade):,} trade flows (>= ${MIN_FLOW_USD / 1e6:.0f}M) to {args.out}/"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
