"""Generate the synthetic AI chip supply chain network.

Creates a fictional network of companies, facilities, chip parts and AI server
products, calibrated to the real CEPII BACI trade flows written by
fetch_baci.py. Every output table is prefixed `synthetic_`. See the README's Dataset
section for what is real and what is synthetic.

The supply chain modelled, from raw inputs to end markets:

    equipment / materials companies --supply--> facilities (fabs, packaging plants)
    facilities --fabricate / package--> chip parts (AI accelerators, HBM, CPUs, ...)
    HBM and substrates --are components of--> AI accelerators
    chip parts --are used in (bill of materials)--> AI servers
    assembly plants --assemble--> AI servers --are sold into--> end markets

Calibration to real data: when a facility picks its equipment and materials
suppliers, the supplier's country is weighted by real BACI trade from that
country into the facility's country. Server assembly plants are located in
proportion to real BACI server exports.

Validation runs before anything is written; if any check fails, no files are
written. Output is deterministic for a given --seed and --scale.

Usage:
    python3 scripts/generate.py --scale small --out csv_data
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

GENERATOR_VERSION = "1.0.0"
NAMES_FILE = Path(__file__).parent / "reference" / "company_names.json"
CALIBRATION_YEAR = 2024
YEARS = range(2017, 2026)

# Company counts per role at scale "small". Scale "large" multiplies these.
ROLE_COUNTS = {
    "materials": 50, "equipment": 50, "eda_ip": 10, "foundry": 16, "memory": 10,
    "packaging": 24, "chip_designer": 100, "server_maker": 40,
}
SCALE_FACTORS = {"small": 1, "large": 8}

# Where each role's companies are headquartered (illustrative weights shaped like the real industry).
ROLE_HQ_WEIGHTS = {
    "materials": {"JPN": 35, "USA": 15, "TWN": 12, "KOR": 12, "DEU": 12, "CHN": 14},
    "equipment": {"USA": 28, "JPN": 28, "NLD": 12, "KOR": 8, "DEU": 8, "CHN": 16},
    "eda_ip": {"USA": 70, "GBR": 30},
    "foundry": {"TWN": 40, "CHN": 25, "USA": 15, "KOR": 12, "JPN": 8},
    "memory": {"KOR": 45, "USA": 20, "CHN": 20, "JPN": 15},
    "packaging": {"TWN": 35, "CHN": 25, "MYS": 10, "KOR": 10, "USA": 10, "SGP": 10},
    "chip_designer": {"USA": 50, "CHN": 15, "TWN": 12, "ISR": 6, "GBR": 5, "KOR": 5, "JPN": 4, "CAN": 3},
    "server_maker": {"TWN": 40, "USA": 30, "CHN": 20, "JPN": 10},
}

# Subtypes within a role: (share of the role's companies, HQ weights override or None).
ROLE_SUBTYPES = {
    "materials": {
        "wafers": (0.18, None), "polysilicon": (0.08, {"DEU": 40, "USA": 30, "CHN": 30}),
        "photoresist": (0.14, {"JPN": 70, "USA": 15, "KOR": 15}), "specialty_gases": (0.16, None),
        "wet_chemicals": (0.16, None), "substrates": (0.16, {"JPN": 40, "TWN": 35, "KOR": 25}),
        "cmp_slurry": (0.12, None),
    },
    "equipment": {
        "lithography": (0.08, {"NLD": 60, "JPN": 40}), "etch": (0.18, None), "deposition": (0.2, None),
        "metrology": (0.16, None), "cleaning": (0.12, None), "ion_implant": (0.1, None),
        "assembly_tools": (0.16, {"JPN": 30, "SGP": 25, "USA": 20, "NLD": 15, "KOR": 10}),
    },
    "eda_ip": {"eda": (0.6, None), "ip": (0.4, None)},
    "foundry": {"foundry": (1.0, None)},
    "memory": {"dram_hbm": (0.6, {"KOR": 55, "CHN": 20, "USA": 15, "JPN": 10}), "nand": (0.4, None)},
    "packaging": {"advanced_packaging": (0.4, {"TWN": 70, "KOR": 10, "USA": 10, "CHN": 10}),
                  "standard_packaging": (0.6, None)},
    "chip_designer": {"ai": (0.25, None), "cpu": (0.15, None), "network": (0.25, None), "power": (0.35, None)},
    "server_maker": {"server_maker": (1.0, None)},
}

# Role word appended to the brand. All of these were ignored during name screening.
ROLE_WORDS = {
    "wafers": "Wafers", "polysilicon": "Silicon", "photoresist": "Chemicals", "specialty_gases": "Materials",
    "wet_chemicals": "Chemicals", "substrates": "Materials", "cmp_slurry": "Materials",
    "lithography": "Lithography", "etch": "Systems", "deposition": "Equipment", "metrology": "Instruments",
    "cleaning": "Solutions", "ion_implant": "Equipment", "assembly_tools": "Precision", "eda": "Design",
    "ip": "Labs", "foundry": "Foundry", "dram_hbm": "Memory", "nand": "Memory",
    "advanced_packaging": "Packaging", "standard_packaging": "Technologies", "ai": "Compute",
    "cpu": "Microsystems", "network": "Photonics", "power": "Devices", "server_maker": "Servers",
}

# Supply categories each facility type buys, with the HS code used for calibration and
# the share of the facility's annual purchase spend.
EQUIPMENT_HS = "848620"   # machines for processing wafers into devices
MATERIALS_HS = "381800"   # doped wafers and chemical compounds for electronics
FACILITY_NEEDS = {
    "front_end_fab": {"lithography": 0.24, "etch": 0.18, "deposition": 0.18, "metrology": 0.1,
                      "cleaning": 0.07, "ion_implant": 0.05, "wafers": 0.06, "photoresist": 0.04,
                      "specialty_gases": 0.03, "wet_chemicals": 0.03, "cmp_slurry": 0.02},
    "memory_fab": {"lithography": 0.2, "etch": 0.2, "deposition": 0.2, "metrology": 0.1, "cleaning": 0.07,
                   "ion_implant": 0.05, "wafers": 0.07, "photoresist": 0.04, "specialty_gases": 0.04,
                   "wet_chemicals": 0.03},
    "packaging_plant": {"assembly_tools": 0.45, "substrates": 0.4, "wet_chemicals": 0.15},
    "materials_plant": {"polysilicon": 0.6, "specialty_gases": 0.4},
}
CATEGORY_HS = {c: EQUIPMENT_HS for c in ["lithography", "etch", "deposition", "metrology", "cleaning", "ion_implant"]}
CATEGORY_HS.update({c: MATERIALS_HS for c in ["wafers", "polysilicon", "photoresist", "specialty_gases",
                                              "wet_chemicals", "cmp_slurry"]})

# Real chip-industry cities (approximate city-centre coordinates). Facilities are fictional.
CITIES = {
    "TWN": [("Hsinchu", 24.80, 120.97), ("Tainan", 22.99, 120.21), ("Taichung", 24.15, 120.67),
            ("Kaohsiung", 22.63, 120.30), ("Taoyuan", 24.99, 121.30)],
    "KOR": [("Pyeongtaek", 36.99, 127.11), ("Icheon", 37.27, 127.44), ("Hwaseong", 37.20, 126.83),
            ("Cheongju", 36.64, 127.49), ("Yongin", 37.24, 127.18)],
    "JPN": [("Kumamoto", 32.80, 130.71), ("Yokkaichi", 34.97, 136.62), ("Hiroshima", 34.39, 132.46),
            ("Kitakami", 39.29, 141.11), ("Chitose", 42.82, 141.65), ("Tokyo", 35.68, 139.69)],
    "CHN": [("Shanghai", 31.23, 121.47), ("Beijing", 39.90, 116.40), ("Wuhan", 30.59, 114.31),
            ("Shenzhen", 22.54, 114.06), ("Wuxi", 31.49, 120.31), ("Hefei", 31.82, 117.23),
            ("Nanjing", 32.06, 118.80), ("Xi'an", 34.34, 108.94)],
    "USA": [("Phoenix", 33.45, -112.07), ("Austin", 30.27, -97.74), ("Boise", 43.62, -116.20),
            ("Hillsboro", 45.52, -122.99), ("Malta", 42.98, -73.79), ("Santa Clara", 37.35, -121.96),
            ("Columbus", 39.96, -83.00), ("Dallas", 32.78, -96.80)],
    "NLD": [("Veldhoven", 51.42, 5.40), ("Eindhoven", 51.44, 5.47), ("Nijmegen", 51.84, 5.85)],
    "DEU": [("Dresden", 51.05, 13.74), ("Munich", 48.14, 11.58), ("Regensburg", 49.01, 12.10),
            ("Jena", 50.93, 11.59)],
    "SGP": [("Singapore", 1.35, 103.82)],
    "MYS": [("Penang", 5.41, 100.33), ("Kulim", 5.37, 100.56), ("Kuala Lumpur", 3.14, 101.69)],
    "VNM": [("Bac Ninh", 21.19, 106.08), ("Ho Chi Minh City", 10.82, 106.63)],
    "THA": [("Bangkok", 13.76, 100.50), ("Chonburi", 13.36, 100.98)],
    "MEX": [("Guadalajara", 20.66, -103.35), ("Ciudad Juarez", 31.69, -106.42), ("Monterrey", 25.69, -100.32)],
    "ISR": [("Haifa", 32.79, 34.99), ("Kiryat Gat", 31.61, 34.76)],
    "GBR": [("Cambridge", 52.21, 0.12), ("Bristol", 51.45, -2.59)],
    "IRL": [("Leixlip", 53.37, -6.49)],
    "FRA": [("Crolles", 45.28, 5.88), ("Grenoble", 45.19, 5.72)],
    "IND": [("Bengaluru", 12.97, 77.59), ("Hyderabad", 17.39, 78.49)],
    "PHL": [("Manila", 14.60, 120.98), ("Laguna", 14.17, 121.33)],
    "CAN": [("Ottawa", 45.42, -75.70), ("Toronto", 43.65, -79.38)],
}

# Facility types each role operates, with (facilities per company range, where they are located).
# Location: "hq" keeps most facilities in the HQ country; a dict gives weights for other countries.
ROLE_FACILITIES = {
    "materials": ("materials_plant", (1, 2), {"hq": 75, "SGP": 5, "MYS": 5, "CHN": 5, "USA": 5, "KOR": 5}),
    "equipment": ("equipment_plant", (1, 2), {"hq": 80, "SGP": 10, "MYS": 5, "KOR": 5}),
    "foundry": ("front_end_fab", (2, 6), {"hq": 70, "USA": 8, "JPN": 7, "DEU": 6, "SGP": 5, "CHN": 4}),
    "memory": ("memory_fab", (2, 5), {"hq": 80, "CHN": 8, "SGP": 6, "USA": 6}),
    "packaging": ("packaging_plant", (1, 4), {"hq": 50, "MYS": 12, "TWN": 10, "CHN": 8, "VNM": 6,
                                              "SGP": 5, "PHL": 5, "KOR": 4}),
    "server_maker": ("server_assembly", (1, 4), "baci_server_exports"),
}

LOGIC_NODES_NM = [3, 5, 7, 16, 28, 40, 65, 130]
# How likely a fab in each country is to run an advanced (<= 5nm) node, relative to mature nodes.
# Leading-edge logic is concentrated in Taiwan; China has no access to <= 5nm tools.
ADVANCED_NODE_WEIGHT = {"TWN": 6.0, "KOR": 1.0, "USA": 0.5, "JPN": 0.3}
# Countries whose DRAM fabs make leading-edge HBM.
HBM_COUNTRIES = {"KOR", "USA", "JPN", "TWN"}
# Fabs at or below this node (and DRAM fabs) need EUV lithography, which only Dutch suppliers make.
EUV_NODE_NM = 7

PART_TYPES = {
    # part_type: (designer role, designer subtype, hs_code, node range nm, unit price range USD)
    "ai_accelerator": ("chip_designer", "ai", "854231", (3, 7), (10_000, 40_000)),
    "cpu": ("chip_designer", "cpu", "854231", (3, 7), (1_000, 12_000)),
    "network_chip": ("chip_designer", "network", "854239", (5, 16), (300, 3_000)),
    "power_ic": ("chip_designer", "power", "854239", (40, 130), (1, 20)),
    "hbm_stack": ("memory", "dram_hbm", "854232", None, (300, 1_500)),
    "substrate": ("materials", "substrates", None, None, (50, 400)),
}
PARTS_PER_DESIGNER = {"ai": (2, 5), "cpu": (2, 4), "network": (2, 5), "power": (4, 10),
                      "dram_hbm": (2, 4), "substrates": (2, 4)}

PRODUCT_TYPES = {
    # product_type: (unit price range, annual units range, BOM: part_type -> (distinct parts, units each))
    "ai_training_rack": ((2_000_000, 4_000_000), (80, 1_000),
                         {"ai_accelerator": (1, 72), "cpu": (1, 36), "network_chip": (2, 18), "power_ic": (3, 240)}),
    "ai_inference_server": ((200_000, 500_000), (400, 6_000),
                            {"ai_accelerator": (1, 8), "cpu": (1, 2), "network_chip": (1, 4), "power_ic": (2, 60)}),
    "general_server": ((10_000, 40_000), (5_000, 60_000),
                       {"cpu": (1, 2), "network_chip": (1, 2), "power_ic": (2, 30)}),
}
PRODUCTS_PER_MAKER = (2, 7)
HBM_PER_ACCELERATOR = (4, 8)

END_MARKETS = [
    ("M1", "hyperscale_cloud", "Large public cloud and AI platform operators"),
    ("M2", "enterprise_ai", "Enterprises running AI in their own data centres"),
    ("M3", "sovereign_ai", "Government-backed national AI compute programmes"),
    ("M4", "edge_ai", "AI inference at the network edge and on premises"),
]
MARKET_MIX = {
    "ai_training_rack": {"M1": 0.70, "M3": 0.15, "M2": 0.15},
    "ai_inference_server": {"M1": 0.40, "M2": 0.40, "M4": 0.20},
    "general_server": {"M2": 0.60, "M1": 0.40},
}

# Hypothetical disruption scenarios. Natural events affect facilities within radius_km.
SCENARIOS = [
    dict(name="Hypothetical earthquake near Hsinchu", event_type="earthquake", country="TWN",
         latitude=24.70, longitude=121.10, radius_km=90, severity=4, start_date="2025-03-10"),
    dict(name="Hypothetical earthquake near Kumamoto", event_type="earthquake", country="JPN",
         latitude=32.80, longitude=130.75, radius_km=60, severity=3, start_date="2025-06-02"),
    dict(name="Hypothetical grid failure in Gyeonggi", event_type="power_outage", country="KOR",
         latitude=37.15, longitude=127.15, radius_km=40, severity=2, start_date="2025-08-18"),
    dict(name="Hypothetical flood around Bangkok", event_type="flood", country="THA",
         latitude=13.70, longitude=100.60, radius_km=80, severity=3, start_date="2025-10-06"),
    dict(name="Hypothetical typhoon in Southern Taiwan", event_type="typhoon", country="TWN",
         latitude=22.80, longitude=120.30, radius_km=70, severity=2, start_date="2025-09-01"),
    dict(name="Hypothetical export control on wafer fab equipment to China", event_type="export_control",
         country="CHN", imposing_country="USA", hs_code=EQUIPMENT_HS, severity=4, start_date="2025-04-01"),
    dict(name="Hypothetical export control on lithography tools to China", event_type="export_control",
         country="CHN", imposing_country="NLD", hs_code=EQUIPMENT_HS, severity=4, start_date="2025-05-01"),
]
SEVERITY_RECOVERY_FACTOR = {1: 0.25, 2: 0.5, 3: 0.8, 4: 1.0, 5: 1.4}


@dataclass
class Tables:
    data: dict[str, pd.DataFrame] = field(default_factory=dict)

    def __setitem__(self, name: str, rows: list[dict] | pd.DataFrame) -> None:
        self.data[name] = rows if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)

    def __getitem__(self, name: str) -> pd.DataFrame:
        return self.data[name]


class ValidationError(RuntimeError):
    pass


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


class Generator:
    def __init__(self, seed: int, scale: str, real_dir: Path) -> None:
        self.rng = np.random.default_rng(seed)
        self.seed, self.scale = seed, scale
        self.factor = SCALE_FACTORS[scale]
        self.trade = pd.read_csv(real_dir / "trade_flow.csv", dtype={"hs_code": str})
        self.countries = set(pd.read_csv(real_dir / "country.csv", keep_default_na=False)["iso3"])
        names = json.loads(NAMES_FILE.read_text(encoding="utf-8"))
        self.names_screened_at = names["screened_at"]
        self.brands = list(self.rng.permutation(names["names"]))
        self.t = Tables()

    # ---------- helpers ----------
    def choice(self, options, weights=None):
        options = list(options)
        p = None if weights is None else np.asarray(weights, dtype=float) / np.sum(weights)
        return options[self.rng.choice(len(options), p=p)]

    def uniform(self, low: float, high: float) -> float:
        return float(self.rng.uniform(low, high))

    def integer(self, low: int, high: int) -> int:
        return int(self.rng.integers(low, high + 1))

    def split_shares(self, n: int) -> list[float]:
        """Split 100% across n parties, rounded to 0.1 and summing to exactly 100."""
        raw = self.rng.dirichlet(np.full(n, 1.5)) * 100
        shares = [round(x, 1) for x in raw]
        shares[int(np.argmax(shares))] += round(100 - sum(shares), 1)
        return [round(s, 1) for s in shares]

    def flow_value(self, exporter: str, importer: str, hs_prefix: str) -> float:
        rows = self.flows_by_hs.get(hs_prefix)
        return 0.0 if rows is None else float(rows.get((exporter, importer), 0.0))

    def city(self, country: str) -> tuple[str, float, float]:
        name, lat, lon = self.choice(CITIES[country])
        # Spread facilities around the city centre so they do not overlap on a map.
        return name, round(lat + self.uniform(-0.06, 0.06), 4), round(lon + self.uniform(-0.06, 0.06), 4)

    # ---------- companies ----------
    def allocate_countries(self, n: int, weights: dict[str, float]) -> list[str]:
        """Allocate n companies to countries, never leaving a country with exactly one."""
        countries = sorted(weights)
        counts = dict(zip(countries, self.rng.multinomial(n, np.array([weights[c] for c in countries]) / sum(weights.values()))))
        for c in countries:
            if counts[c] == 1:
                largest = max(countries, key=lambda k: (counts[k], k))
                if largest != c and counts[largest] >= 3:
                    counts[largest] -= 1
                    counts[c] = 2
                else:
                    counts[c] = 0
                    counts[largest] += 1
        return [c for c in countries for _ in range(counts[c])]

    def build_companies(self) -> None:
        rows = []
        for role, base_count in ROLE_COUNTS.items():
            total = base_count * self.factor
            for subtype, (share, override) in ROLE_SUBTYPES[role].items():
                n = max(2, round(total * share))
                for country in self.allocate_countries(n, override or ROLE_HQ_WEIGHTS[role]):
                    brand = self.brands.pop()
                    state_owned = country == "CHN" and self.rng.random() < 0.35
                    rows.append({
                        "company_id": f"C{len(rows) + 1:05d}",
                        "name": f"{brand} {ROLE_WORDS[subtype]}",
                        "brand": brand,
                        "role": role,
                        "subtype": subtype,
                        "hq_country": country,
                        "ownership": "state_owned" if state_owned else self.choice(["public", "private"], [0.6, 0.4]),
                        "founded_year": self.integer(1965, 2021),
                        "employees": int(self.rng.lognormal(7.5, 1.2)),
                    })
        self.t["synthetic_company"] = rows

    # ---------- facilities ----------
    def facility_profile(self, ftype: str, subtype: str, country: str) -> dict:
        profile = {"domain": None, "process_node": None, "process_node_nm": None, "wafer_size_mm": None}
        if ftype == "front_end_fab":
            advanced = ADVANCED_NODE_WEIGHT.get(country, 0.0)
            nodes = [n for n in LOGIC_NODES_NM if n > 5 or advanced > 0]
            weights = [advanced if n <= 5 else 1.5 if n <= 16 else 1.0 for n in nodes]
            node = self.choice(nodes, weights)
            profile.update(domain="logic", process_node=f"{node}nm", process_node_nm=node,
                           wafer_size_mm=300 if node <= 40 or self.rng.random() < 0.5 else 200)
            capacity, unit = self.integer(15, 110) * 1000, "wafer_starts_per_month"
            ttr = (20, 40) if node <= 7 else (12, 30)
        elif ftype == "memory_fab":
            profile.update(domain=subtype, process_node=self.choice(["1a", "1b", "1c"]) + (" DRAM" if subtype == "dram_hbm" else " NAND"),
                           wafer_size_mm=300)
            capacity, unit = self.integer(40, 180) * 1000, "wafer_starts_per_month"
            ttr = (16, 36)
        elif ftype == "packaging_plant":
            profile.update(domain=subtype)
            if subtype == "advanced_packaging":
                capacity, unit, ttr = self.integer(5, 40) * 1000, "interposer_wafers_per_month", (12, 26)
            else:
                capacity, unit, ttr = self.integer(50, 600) * 1_000_000, "packages_per_month", (6, 16)
        elif ftype == "equipment_plant":
            profile.update(domain=subtype)
            capacity, unit, ttr = self.integer(50, 1200), "tools_per_year", (10, 26)
        elif ftype == "materials_plant":
            profile.update(domain=subtype)
            capacity, unit, ttr = self.integer(500, 20_000), "tonnes_per_year", (6, 20)
        else:  # server_assembly
            profile.update(domain="ai_servers")
            capacity, unit, ttr = self.integer(500, 12_000), "racks_per_month", (2, 8)
        profile.update(capacity=capacity, capacity_unit=unit, time_to_recover_weeks=self.integer(*ttr))
        return profile

    def build_facilities(self) -> None:
        server = self.trade[(self.trade["year"] == CALIBRATION_YEAR) & (self.trade["hs_code"] == "847150")]
        exports = server.groupby("exporter")["value_usd"].sum()
        self.server_export_weights = {c: float(exports.get(c, 0)) for c in CITIES if exports.get(c, 0) > 0}

        rows = []
        companies = self.t["synthetic_company"]
        for company in companies.itertuples():
            spec = ROLE_FACILITIES.get(company.role)
            if spec is None:
                continue
            ftype, count_range, placement = spec
            for i in range(self.integer(*count_range)):
                if placement == "baci_server_exports":
                    country = self.choice(list(self.server_export_weights), list(self.server_export_weights.values()))
                else:
                    weights = dict(placement)
                    hq_weight = weights.pop("hq")
                    weights[company.hq_country] = weights.get(company.hq_country, 0) + hq_weight
                    country = self.choice(list(weights), list(weights.values()))
                city, lat, lon = self.city(country)
                status = self.choice(["operating", "ramping", "under_construction", "planned"], [80, 10, 7, 3])
                start = {"operating": self.integer(1995, 2023), "ramping": self.integer(2024, 2025),
                         "under_construction": self.integer(2026, 2027), "planned": self.integer(2028, 2029)}[status]
                label = {"front_end_fab": "Fab", "memory_fab": "Fab", "packaging_plant": "Packaging Plant",
                         "equipment_plant": "Plant", "materials_plant": "Plant", "server_assembly": "Assembly"}[ftype]
                rows.append({
                    "facility_id": f"F{len(rows) + 1:05d}",
                    "company_id": company.company_id,
                    "name": f"{company.brand} {city} {label} {i + 1}",
                    "facility_type": ftype,
                    "city": city,
                    "country": country,
                    "latitude": lat,
                    "longitude": lon,
                    "status": status,
                    "hvm_start_year": start,
                    **self.facility_profile(ftype, company.subtype, country),
                })
        self.t["synthetic_facility"] = rows

        capacity_rows = []
        for f in self.t["synthetic_facility"].itertuples():
            growth = 1.35 if f.domain == "advanced_packaging" else 1.04  # advanced packaging expanded fast with AI demand
            for year in YEARS:
                if year < f.hvm_start_year:
                    value = 0
                else:
                    ramp = min(1.0, 0.4 + 0.3 * (year - f.hvm_start_year))
                    value = round(f.capacity * ramp / growth ** max(0, 2025 - max(year, f.hvm_start_year)))
                capacity_rows.append({"facility_id": f.facility_id, "year": year, "capacity": value,
                                      "capacity_unit": f.capacity_unit})
        self.t["synthetic_facility_capacity"] = capacity_rows

    # ---------- supply contracts (equipment and materials into facilities) ----------
    def build_supply(self) -> None:
        recent = self.trade[self.trade["year"] == CALIBRATION_YEAR]
        self.flows_by_hs = {
            hs: recent[recent["hs_code"].str.startswith(hs)].groupby(["exporter", "importer"])["value_usd"].sum()
            for hs in (EQUIPMENT_HS, MATERIALS_HS)
        }
        # BACI has no domestic flows, so a domestic supplier gets the weight of the
        # importing country's largest foreign partner for that product.
        largest_import = {hs: flows.groupby(level="importer").max() for hs, flows in self.flows_by_hs.items()}
        companies = self.t["synthetic_company"]
        by_subtype = {s: g for s, g in companies.groupby("subtype")}
        facilities = self.t["synthetic_facility"]
        supply, alternatives = [], []
        for f in facilities.itertuples():
            needs = FACILITY_NEEDS.get(f.facility_type)
            if not needs or f.status == "planned":
                continue
            annual_spend = {"front_end_fab": 9_000, "memory_fab": 6_000, "packaging_plant": 30,
                            "materials_plant": 40_000}[f.facility_type] * f.capacity
            needs_euv = f.facility_type == "memory_fab" and f.domain == "dram_hbm" or (
                f.facility_type == "front_end_fab" and f.process_node_nm <= EUV_NODE_NM)
            for category, spend_share in needs.items():
                candidates = by_subtype[category]
                if category == "lithography" and needs_euv:
                    candidates = candidates[candidates["hq_country"] == "NLD"]
                hs = CATEGORY_HS.get(category)
                weights = []
                for c in candidates.itertuples():
                    if hs is None:
                        w = 1.0
                    elif c.hq_country == f.country:
                        w = float(largest_import[hs].get(f.country, 1.0))
                    else:
                        w = self.flow_value(c.hq_country, f.country, hs)
                    weights.append(w + 1e-3)
                k = min(len(candidates), self.choice([1, 2, 3], [0.3, 0.45, 0.25]))
                p = np.asarray(weights) / np.sum(weights)
                picked = self.rng.choice(len(candidates), size=k, replace=False, p=p)
                shares = self.split_shares(k)
                # Equipment is ordered ahead of production, so contracts may predate the start year.
                start = self.integer(min(max(2017, f.hvm_start_year - 1), 2025), 2025)
                for idx, share in zip(sorted(picked), shares):
                    supplier = candidates.iloc[idx]
                    supply.append({
                        "supply_id": f"S{len(supply) + 1:06d}",
                        "supplier_company_id": supplier.company_id,
                        "facility_id": f.facility_id,
                        "supply_category": category,
                        "hs_code": hs,
                        "annual_value_usd": int(annual_spend * spend_share * share / 100),
                        "share_of_need_pct": share,
                        "lead_time_weeks": self.integer(*((26, 78) if category == "lithography" else (8, 40) if hs == EQUIPMENT_HS else (2, 16))),
                        "inventory_weeks_on_hand": self.integer(2, 16),
                        "contract_start": f"{start}-{self.integer(1, 12):02d}-01",
                        "contract_end": f"{start + self.integer(2, 6)}-12-31",
                    })
                unused = [i for i in range(len(candidates)) if i not in set(picked)]
                if unused and self.rng.random() < 0.35:
                    alt = candidates.iloc[self.choice(unused)]
                    alternatives.append({
                        "supplier_company_id": alt.company_id, "facility_id": f.facility_id,
                        "supply_category": category,
                        "qualification_months": self.integer(*((12, 30) if category == "lithography" else (3, 15))),
                        "spare_capacity_pct": round(self.uniform(5, 35), 1),
                    })
        self.t["synthetic_supply"] = supply
        self.t["synthetic_alt_supplier"] = alternatives

    # ---------- chip parts ----------
    def build_parts(self) -> None:
        companies = self.t["synthetic_company"]
        rows = []
        for part_type, (role, subtype, hs, node_range, price_range) in PART_TYPES.items():
            designers = companies[(companies["role"] == role) & (companies["subtype"] == subtype)]
            if part_type == "hbm_stack":
                designers = designers[designers["hq_country"].isin(HBM_COUNTRIES)]
            for d in designers.itertuples():
                for _ in range(self.integer(*PARTS_PER_DESIGNER[subtype])):
                    node = None
                    if node_range:
                        node = self.choice([n for n in LOGIC_NODES_NM if node_range[0] <= n <= node_range[1]])
                    prefix = "".join(ch for ch in d.brand.upper() if ch not in "AEIOU")[:3].ljust(3, "X")
                    rows.append({
                        "part_id": f"P{len(rows) + 1:05d}",
                        "part_number": f"{prefix}-{part_type[:2].upper()}{len(rows) + 100:04d}",
                        "part_type": part_type,
                        "designer_company_id": d.company_id,
                        "hs_code": hs,
                        "process_node_nm": node,
                        "unit_price_usd": round(self.uniform(*price_range), 2),
                        # Popularity drives which parts many products use (a few parts dominate).
                        "popularity": float(self.rng.pareto(1.2) + 1),
                    })
        self.t["synthetic_chip_part"] = rows

    def build_manufacturing(self) -> None:
        parts = self.t["synthetic_chip_part"]
        facilities = self.t["synthetic_facility"]
        companies = self.t["synthetic_company"].set_index("company_id")
        live = facilities[facilities["status"] != "planned"]
        fabs = live[live["facility_type"] == "front_end_fab"]
        hbm_fabs = live[(live["facility_type"] == "memory_fab") & (live["domain"] == "dram_hbm")
                        & live["country"].isin(HBM_COUNTRIES)]
        substrate_plants = live[(live["facility_type"] == "materials_plant") & (live["domain"] == "substrates")]
        adv_pkg = live[(live["facility_type"] == "packaging_plant") & (live["domain"] == "advanced_packaging")]
        std_pkg = live[(live["facility_type"] == "packaging_plant") & (live["domain"] == "standard_packaging")]

        fabrication, packaging, components, alternatives = [], [], [], []

        def assign(part, pool: pd.DataFrame, step: str, out: list, max_sites: int) -> None:
            if pool.empty:
                raise ValidationError(f"No facility can perform {step} for {part.part_type} {part.part_id}")
            k = min(len(pool), self.choice(list(range(1, max_sites + 1)), [0.45, 0.35, 0.2][:max_sites]))
            # Larger facilities win more parts.
            picked = self.rng.choice(len(pool), size=k, replace=False, p=pool["capacity"] / pool["capacity"].sum())
            for idx, share in zip(sorted(picked), self.split_shares(k)):
                site = pool.iloc[idx]
                row = {"facility_id": site.facility_id, "part_id": part.part_id, "share_of_part_volume_pct": share,
                       "lead_time_weeks": self.integer(*((12, 20) if step == "fabrication" else (4, 10))),
                       "inventory_weeks_on_hand": self.integer(1, 10)}
                if step == "fabrication" and site.capacity_unit == "wafer_starts_per_month":
                    row["wafers_per_month"] = int(site.capacity * self.uniform(0.02, 0.15) * share / 100)
                out.append(row)
            unused = [i for i in range(len(pool)) if i not in set(picked)]
            if unused and self.rng.random() < 0.4:
                alt = pool.iloc[self.choice(unused)]
                alternatives.append({"facility_id": alt.facility_id, "part_id": part.part_id, "step": step,
                                     "qualification_months": self.integer(*((6, 18) if step == "fabrication" else (3, 9))),
                                     "spare_capacity_pct": round(self.uniform(5, 30), 1)})

        for part in parts.itertuples():
            if part.part_type == "hbm_stack":
                own = hbm_fabs[hbm_fabs["company_id"] == part.designer_company_id]
                assign(part, own if not own.empty else hbm_fabs, "fabrication", fabrication, 2)
            elif part.part_type == "substrate":
                own = substrate_plants[substrate_plants["company_id"] == part.designer_company_id]
                assign(part, own if not own.empty else substrate_plants, "fabrication", fabrication, 2)
            else:
                capable = fabs[fabs["process_node_nm"] <= part.process_node_nm]
                assign(part, capable, "fabrication", fabrication, 3)
                assign(part, adv_pkg if part.part_type == "ai_accelerator" else std_pkg, "packaging", packaging, 2)

        hbm = parts[parts["part_type"] == "hbm_stack"]
        substrates = parts[parts["part_type"] == "substrate"]
        for acc in parts[parts["part_type"] == "ai_accelerator"].itertuples():
            components.append({"component_part_id": self.choice(hbm["part_id"], hbm["popularity"]),
                               "parent_part_id": acc.part_id, "quantity": self.integer(*HBM_PER_ACCELERATOR)})
            components.append({"component_part_id": self.choice(substrates["part_id"], substrates["popularity"]),
                               "parent_part_id": acc.part_id, "quantity": 1})
        for cpu in parts[parts["part_type"].isin(["cpu", "network_chip"])].itertuples():
            components.append({"component_part_id": self.choice(substrates["part_id"], substrates["popularity"]),
                               "parent_part_id": cpu.part_id, "quantity": 1})

        self.t["synthetic_fabrication"] = fabrication
        self.t["synthetic_packaging"] = packaging
        self.t["synthetic_part_component"] = components
        self.t["synthetic_alt_facility"] = alternatives

    # ---------- AI servers, bill of materials, assembly, end markets ----------
    def build_products(self) -> None:
        companies = self.t["synthetic_company"]
        parts = self.t["synthetic_chip_part"]
        facilities = self.t["synthetic_facility"]
        products, bom, assembly, sales = [], [], [], []
        by_type = {t: g for t, g in parts.groupby("part_type")}
        for maker in companies[companies["role"] == "server_maker"].itertuples():
            plants = facilities[(facilities["company_id"] == maker.company_id) & (facilities["status"].isin(["operating", "ramping"]))]
            if plants.empty:
                plants = facilities[facilities["company_id"] == maker.company_id]
            for n in range(self.integer(*PRODUCTS_PER_MAKER)):
                ptype = self.choice(list(PRODUCT_TYPES), [0.3, 0.35, 0.35])
                price_range, units_range, recipe = PRODUCT_TYPES[ptype]
                price = round(self.uniform(*price_range), -3)
                units = self.integer(*units_range)
                series = {"ai_training_rack": "TR", "ai_inference_server": "IX", "general_server": "GS"}[ptype]
                product_id = f"E{len(products) + 1:05d}"
                products.append({
                    "product_id": product_id, "maker_company_id": maker.company_id,
                    "name": f"{maker.brand} {series}-{100 * self.integer(1, 9) + 10 * n}",
                    "product_type": ptype, "hs_code": "847150", "unit_price_usd": price,
                    "annual_units": units, "annual_revenue_usd": int(price * units),
                })
                for part_type, (distinct, units_each) in recipe.items():
                    pool = by_type[part_type]
                    picked = self.rng.choice(len(pool), size=min(distinct, len(pool)), replace=False,
                                             p=pool["popularity"] / pool["popularity"].sum())
                    for idx in sorted(picked):
                        bom.append({"part_id": pool.iloc[idx].part_id, "product_id": product_id,
                                    "units_per_product": max(1, round(units_each * self.uniform(0.75, 1.25)))})
                k = min(len(plants), self.choice([1, 2, 3], [0.5, 0.35, 0.15]))
                for idx, share in zip(sorted(self.rng.choice(len(plants), size=k, replace=False)), self.split_shares(k)):
                    assembly.append({"facility_id": plants.iloc[idx].facility_id, "product_id": product_id,
                                     "share_of_product_volume_pct": share, "lead_time_weeks": self.integer(2, 6),
                                     "inventory_weeks_on_hand": self.integer(1, 6)})
                revenue = price * units
                for market_id, mix in MARKET_MIX[ptype].items():
                    sales.append({"product_id": product_id, "market_id": market_id,
                                  "revenue_usd": int(revenue * mix)})

        self.t["synthetic_end_market"] = [{"market_id": m, "name": n, "description": d} for m, n, d in END_MARKETS]
        self.t["synthetic_end_product"] = products
        self.t["synthetic_bom_line"] = bom
        self.t["synthetic_assembly"] = assembly
        self.t["synthetic_sales"] = sales

    def build_licenses(self) -> None:
        companies = self.t["synthetic_company"]
        vendors = companies[companies["role"] == "eda_ip"]
        rows = []
        for d in companies[companies["role"] == "chip_designer"].itertuples():
            for idx in sorted(self.rng.choice(len(vendors), size=min(len(vendors), self.integer(1, 3)), replace=False)):
                v = vendors.iloc[idx]
                rows.append({"vendor_company_id": v.company_id, "licensee_company_id": d.company_id,
                             "license_type": "eda_tools" if v.subtype == "eda" else "core_ip",
                             "annual_fee_usd": self.integer(1, 60) * 250_000})
        self.t["synthetic_license"] = rows

    # ---------- restrictions and disruption scenarios ----------
    def build_restrictions(self) -> None:
        """Fictional export restrictions on Chinese companies that sit on a path to an AI server."""
        companies = self.t["synthetic_company"]
        facilities = self.t["synthetic_facility"]
        parts = self.t["synthetic_chip_part"]
        used_parts = set(self.t["synthetic_bom_line"]["part_id"]) | set(self.t["synthetic_part_component"]["component_part_id"])
        producing_sites = set(self.t["synthetic_fabrication"]["facility_id"]) | set(self.t["synthetic_packaging"]["facility_id"])
        connected = (
            set(parts.loc[parts["part_id"].isin(used_parts), "designer_company_id"])
            | set(facilities.loc[facilities["facility_id"].isin(producing_sites), "company_id"])
            | set(self.t["synthetic_supply"]["supplier_company_id"])
        )
        targets = companies[(companies["hq_country"] == "CHN") & companies["company_id"].isin(connected)
                            & companies["role"].isin(["foundry", "memory", "chip_designer", "equipment"])]
        n = min(len(targets), max(3, round(0.15 * len(targets))))
        rows = []
        for idx in sorted(self.rng.choice(len(targets), size=n, replace=False)):
            c = targets.iloc[idx]
            rows.append({
                "restriction_id": f"R{len(rows) + 1:04d}", "imposing_country": "USA",
                "company_id": c.company_id, "list_type": "export_control_list",
                "program": self.choice(["advanced_computing", "military_end_use", "semiconductor_manufacturing"]),
                "start_date": f"{self.integer(2019, 2025)}-{self.integer(1, 12):02d}-15",
                "license_policy": self.choice(["presumption_of_denial", "case_by_case"], [0.7, 0.3]),
            })
        self.t["synthetic_restriction"] = rows

    def build_events(self) -> None:
        facilities = self.t["synthetic_facility"]
        events, impacts, countries = [], [], []
        for i, s in enumerate(SCENARIOS, start=1):
            event_id = f"V{i:03d}"
            events.append({
                "event_id": event_id, "name": s["name"], "event_type": s["event_type"],
                "scenario_note": "Hypothetical scenario for illustration; not a forecast.",
                "start_date": s["start_date"], "severity": s["severity"],
                "latitude": s.get("latitude"), "longitude": s.get("longitude"), "radius_km": s.get("radius_km"),
                "hs_code": s.get("hs_code"),
            })
            countries.append({"event_id": event_id, "country": s["country"],
                              "relation": "target" if s["event_type"] == "export_control" else "location"})
            if "imposing_country" in s:
                countries.append({"event_id": event_id, "country": s["imposing_country"], "relation": "imposing"})
            if s.get("radius_km"):
                for f in facilities.itertuples():
                    distance = haversine_km(s["latitude"], s["longitude"], f.latitude, f.longitude)
                    if distance <= s["radius_km"]:
                        closeness = 1 - distance / s["radius_km"]
                        loss = round(min(100.0, 20 + 70 * closeness * s["severity"] / 4), 1)
                        impacts.append({"event_id": event_id, "facility_id": f.facility_id,
                                        "distance_km": round(distance, 1), "capacity_loss_pct": loss,
                                        "recovery_weeks": max(1, round(f.time_to_recover_weeks
                                                                       * SEVERITY_RECOVERY_FACTOR[s["severity"]]
                                                                       * (0.5 + closeness)))})
        self.t["synthetic_disruption_event"] = events
        self.t["synthetic_event_impact"] = impacts
        self.t["synthetic_event_country"] = countries

    def build(self) -> Tables:
        self.build_companies()
        self.build_facilities()
        self.build_supply()
        self.build_parts()
        self.build_manufacturing()
        self.build_products()
        self.build_licenses()
        self.build_restrictions()
        self.build_events()
        self.t["synthetic_chip_part"] = self.t["synthetic_chip_part"].drop(columns="popularity")
        self.t["synthetic_company"] = self.t["synthetic_company"].drop(columns="brand")
        return self.t


# ---------- validation ----------
FOREIGN_KEYS = [
    # (table, column, referenced table, referenced column)
    ("synthetic_company", "hq_country", "country", "iso3"),
    ("synthetic_facility", "company_id", "synthetic_company", "company_id"),
    ("synthetic_facility", "country", "country", "iso3"),
    ("synthetic_facility_capacity", "facility_id", "synthetic_facility", "facility_id"),
    ("synthetic_supply", "supplier_company_id", "synthetic_company", "company_id"),
    ("synthetic_supply", "facility_id", "synthetic_facility", "facility_id"),
    ("synthetic_supply", "hs_code", "product", "hs_code"),
    ("synthetic_alt_supplier", "supplier_company_id", "synthetic_company", "company_id"),
    ("synthetic_alt_supplier", "facility_id", "synthetic_facility", "facility_id"),
    ("synthetic_chip_part", "designer_company_id", "synthetic_company", "company_id"),
    ("synthetic_chip_part", "hs_code", "product", "hs_code"),
    ("synthetic_fabrication", "facility_id", "synthetic_facility", "facility_id"),
    ("synthetic_fabrication", "part_id", "synthetic_chip_part", "part_id"),
    ("synthetic_packaging", "facility_id", "synthetic_facility", "facility_id"),
    ("synthetic_packaging", "part_id", "synthetic_chip_part", "part_id"),
    ("synthetic_part_component", "component_part_id", "synthetic_chip_part", "part_id"),
    ("synthetic_part_component", "parent_part_id", "synthetic_chip_part", "part_id"),
    ("synthetic_alt_facility", "facility_id", "synthetic_facility", "facility_id"),
    ("synthetic_alt_facility", "part_id", "synthetic_chip_part", "part_id"),
    ("synthetic_end_product", "maker_company_id", "synthetic_company", "company_id"),
    ("synthetic_end_product", "hs_code", "product", "hs_code"),
    ("synthetic_bom_line", "part_id", "synthetic_chip_part", "part_id"),
    ("synthetic_bom_line", "product_id", "synthetic_end_product", "product_id"),
    ("synthetic_assembly", "facility_id", "synthetic_facility", "facility_id"),
    ("synthetic_assembly", "product_id", "synthetic_end_product", "product_id"),
    ("synthetic_sales", "product_id", "synthetic_end_product", "product_id"),
    ("synthetic_sales", "market_id", "synthetic_end_market", "market_id"),
    ("synthetic_license", "vendor_company_id", "synthetic_company", "company_id"),
    ("synthetic_license", "licensee_company_id", "synthetic_company", "company_id"),
    ("synthetic_restriction", "imposing_country", "country", "iso3"),
    ("synthetic_restriction", "company_id", "synthetic_company", "company_id"),
    ("synthetic_disruption_event", "hs_code", "product", "hs_code"),
    ("synthetic_event_impact", "event_id", "synthetic_disruption_event", "event_id"),
    ("synthetic_event_impact", "facility_id", "synthetic_facility", "facility_id"),
    ("synthetic_event_country", "event_id", "synthetic_disruption_event", "event_id"),
    ("synthetic_event_country", "country", "country", "iso3"),
]
PRIMARY_KEYS = {
    "synthetic_company": ["company_id"], "synthetic_facility": ["facility_id"],
    "synthetic_facility_capacity": ["facility_id", "year"], "synthetic_supply": ["supply_id"],
    "synthetic_alt_supplier": ["supplier_company_id", "facility_id", "supply_category"],
    "synthetic_chip_part": ["part_id"], "synthetic_fabrication": ["facility_id", "part_id"],
    "synthetic_packaging": ["facility_id", "part_id"], "synthetic_part_component": ["component_part_id", "parent_part_id"],
    "synthetic_alt_facility": ["facility_id", "part_id", "step"], "synthetic_end_market": ["market_id"],
    "synthetic_end_product": ["product_id"], "synthetic_bom_line": ["part_id", "product_id"],
    "synthetic_assembly": ["facility_id", "product_id"], "synthetic_sales": ["product_id", "market_id"],
    "synthetic_license": ["vendor_company_id", "licensee_company_id"], "synthetic_restriction": ["restriction_id"],
    "synthetic_disruption_event": ["event_id"], "synthetic_event_impact": ["event_id", "facility_id"],
    "synthetic_event_country": ["event_id", "country", "relation"],
}
MIN_CALIBRATION_CORRELATION = 0.5


def validate(t: Tables, real: dict[str, pd.DataFrame], gen: Generator) -> list[str]:
    """Return a list of human-readable check results; raise ValidationError on any failure."""
    failures, report = [], []
    tables = {**t.data, **real}

    for name, cols in PRIMARY_KEYS.items():
        dupes = int(tables[name].duplicated(cols).sum())
        if dupes:
            failures.append(f"{name}: {dupes} duplicate keys on {cols}")
    report.append("primary keys unique")

    for table, col, ref, ref_col in FOREIGN_KEYS:
        values = tables[table][col].dropna()
        missing = set(values) - set(tables[ref][ref_col])
        if missing:
            failures.append(f"{table}.{col}: {len(missing)} values missing from {ref}.{ref_col}, e.g. {sorted(missing)[:3]}")
    report.append(f"{len(FOREIGN_KEYS)} foreign-key relationships resolve")

    companies = t["synthetic_company"]
    approved = set(json.loads(NAMES_FILE.read_text(encoding="utf-8"))["names"])
    brands = companies["name"].str.rsplit(" ", n=1).str[0]
    if not brands.isin(approved).all() or companies["name"].duplicated().any():
        failures.append("company names must be unique and drawn from the screened name list")
    report.append("all company names come from the screened list and are unique")

    for cols in (["role", "hq_country"], ["role", "subtype", "hq_country"]):
        sizes = companies.groupby(cols).size()
        singles = sizes[sizes == 1]
        if len(singles):
            failures.append(f"stand-in risk: groups with exactly one company by {cols}: {list(singles.index)[:5]}")
    report.append("no role/country group has a single company (no stand-ins for real firms)")

    for table, key, share in [("synthetic_supply", ["facility_id", "supply_category"], "share_of_need_pct"),
                              ("synthetic_fabrication", ["part_id"], "share_of_part_volume_pct"),
                              ("synthetic_packaging", ["part_id"], "share_of_part_volume_pct"),
                              ("synthetic_assembly", ["product_id"], "share_of_product_volume_pct")]:
        totals = t[table].groupby(key)[share].sum()
        off = totals[(totals - 100).abs() > 0.05]
        if len(off):
            failures.append(f"{table}: {len(off)} groups whose shares do not sum to 100%")
    report.append("supply, fabrication, packaging and assembly shares each sum to 100%")

    parts = t["synthetic_chip_part"]
    for check, ok in [
        ("every chip part is fabricated somewhere", parts["part_id"].isin(t["synthetic_fabrication"]["part_id"]).all()),
        ("every AI accelerator is packaged", parts.loc[parts["part_type"] == "ai_accelerator", "part_id"]
            .isin(t["synthetic_packaging"]["part_id"]).all()),
        ("every server has a bill of materials and an assembly plant",
            t["synthetic_end_product"]["product_id"].isin(t["synthetic_bom_line"]["product_id"]).all()
            and t["synthetic_end_product"]["product_id"].isin(t["synthetic_assembly"]["product_id"]).all()),
        ("all money and capacity values are non-negative",
            all((t[n][c] >= 0).all() for n, c in [("synthetic_supply", "annual_value_usd"),
                                                  ("synthetic_end_product", "annual_revenue_usd"),
                                                  ("synthetic_facility", "capacity"),
                                                  ("synthetic_chip_part", "unit_price_usd")])),
    ]:
        if not ok:
            failures.append(check)
        report.append(check)

    supply = t["synthetic_supply"].merge(companies[["company_id", "hq_country"]],
                                         left_on="supplier_company_id", right_on="company_id")
    supply = supply.merge(t["synthetic_facility"][["facility_id", "country"]], on="facility_id")
    cross = supply[(supply["hs_code"] == EQUIPMENT_HS) & (supply["hq_country"] != supply["country"])]
    synthetic_pairs = cross.groupby(["hq_country", "country"])["annual_value_usd"].sum()
    real_pairs = pd.Series({pair: gen.flow_value(pair[0], pair[1], EQUIPMENT_HS) for pair in synthetic_pairs.index})
    correlation = float(synthetic_pairs.rank().corr(real_pairs.rank()))
    if not correlation >= MIN_CALIBRATION_CORRELATION:
        failures.append(f"calibration: rank correlation with BACI equipment flows is {correlation:.2f} "
                        f"(< {MIN_CALIBRATION_CORRELATION})")
    report.append(f"cross-border equipment contracts track real BACI flows (rank correlation {correlation:.2f})")

    if failures:
        raise ValidationError("Validation failed:\n  - " + "\n  - ".join(failures))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scale", choices=sorted(SCALE_FACTORS), default="small")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--real-dir", type=Path, default=Path("csv_data"),
                        help="folder with country.csv, product.csv and trade_flow.csv from fetch_baci.py")
    parser.add_argument("--out", type=Path, default=Path("csv_data"), help="output folder")
    args = parser.parse_args()

    gen = Generator(args.seed, args.scale, args.real_dir)
    tables = gen.build()
    real = {name: pd.read_csv(args.real_dir / f"{name}.csv", dtype={"hs_code": str}, keep_default_na=False)
            for name in ("country", "product")}
    try:
        report = validate(tables, real, gen)
    except ValidationError as err:
        print(err, file=sys.stderr)
        print("No files were written.", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    for name, frame in tables.data.items():
        frame.to_csv(args.out / f"{name}.csv", index=False)
    metadata = {
        "generator_version": GENERATOR_VERSION, "seed": args.seed, "scale": args.scale,
        "calibration_year": CALIBRATION_YEAR, "company_names_screened_at": gen.names_screened_at,
        "row_counts": {name: len(frame) for name, frame in sorted(tables.data.items())},
    }
    (args.out / "synthetic_metadata.json").write_text(json.dumps(metadata, indent=1) + "\n", encoding="utf-8")

    print("Validation passed:")
    for line in report:
        print(f"  ✓ {line}")
    print(f"Wrote {len(tables.data)} synthetic tables to {args.out}/:")
    for name, frame in sorted(tables.data.items()):
        print(f"  {name:32s} {len(frame):>9,} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
