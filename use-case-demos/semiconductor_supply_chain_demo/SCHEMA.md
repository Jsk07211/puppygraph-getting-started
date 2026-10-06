# Recommended Graph Schema

The graph model for PuppyGraph over the Iceberg tables in `ai_chip_supply_chain`. Create it with PuppyGraph's schema builder, using the vertices and edges below. The Cypher in [QUERIES.md](QUERIES.md) assumes these labels.

## Catalog Connection

| Setting | Value |
|---|---|
| Catalog type | Apache Iceberg, REST metastore |
| Metastore URI | `http://iceberg-rest:8181` |
| Storage | S3-compatible (RustFS) |
| Endpoint | `http://rustfs:9000` |
| Access key / secret key | `admin` / `password` |
| Region | `us-east-1` |
| Path-style access | enabled (RustFS requires it) |
| SSL | disabled |
| Database | `ai_chip_supply_chain` |

## Vertices

| Label | Table | ID | Description |
|---|---|---|---|
| `Country` | `country` | `iso3` (String) | Real country (CEPII BACI) |
| `Company` | `synthetic_company` | `company_id` (String) | Fictional company and its supply chain role |
| `Facility` | `synthetic_facility` | `facility_id` (String) | Fictional fab, packaging, equipment, materials or assembly plant |
| `Part` | `synthetic_chip_part` | `part_id` (String) | Chip part: AI accelerator, HBM, CPU, network chip, power chip, substrate |
| `Server` | `synthetic_end_product` | `product_id` (String) | AI training rack, AI inference server or general server |
| `Market` | `synthetic_end_market` | `market_id` (String) | End market for servers |
| `Event` | `synthetic_disruption_event` | `event_id` (String) | Hypothetical disruption scenario |
| `CapacitySnapshot` | `synthetic_facility_capacity` | `facility_id` (String) + `year` (Int) | A facility's capacity in one year, 2017–2025 |

A `+` marks a composite ID made of several columns.

Vertex attributes (all columns other than a single-column ID; composite ID columns are also kept as attributes so they can be filtered on):

- **Country**: `iso2` (String), `name` (String)
- **Company**: `name` (String), `role` (String), `subtype` (String), `hq_country` (String), `ownership` (String), `founded_year` (Int), `employees` (Int)
- **Facility**: `company_id` (String), `name` (String), `facility_type` (String), `city` (String), `country` (String), `latitude` (Double), `longitude` (Double), `status` (String), `hvm_start_year` (Int), `domain` (String), `process_node` (String), `process_node_nm` (Double), `wafer_size_mm` (Int), `capacity` (Long), `capacity_unit` (String), `time_to_recover_weeks` (Int), `capacity_source` (String), `capacity_confidence` (String)
- **Part**: `part_number` (String), `part_type` (String), `designer_company_id` (String), `hs_code` (String), `process_node_nm` (Double), `unit_price_usd` (Double)
- **Server**: `maker_company_id` (String), `name` (String), `product_type` (String), `hs_code` (String), `unit_price_usd` (Double), `annual_units` (Int), `annual_revenue_usd` (Long)
- **Market**: `name` (String), `description` (String)
- **Event**: `name` (String), `event_type` (String), `scenario_note` (String), `start_date` (Date), `severity` (Int), `latitude` (Double), `longitude` (Double), `radius_km` (Double), `hs_code` (String)
- **CapacitySnapshot**: `facility_id` (String), `year` (Int), `capacity` (Long), `capacity_unit` (String)

## Edges

Several edges come from a vertex table's foreign-key column rather than a separate edge table (for example `HQ_IN` uses `synthetic_company.hq_country`).

| Label | From → To | Table | From key → To key | Edge ID | Meaning |
|---|---|---|---|---|---|
| `TRADES` | Country → Country | `trade_flow` | `exporter` → `importer` | `year`, `exporter`, `importer`, `hs_code` | Real annual trade flow for one product |
| `HQ_IN` | Company → Country | `synthetic_company` | `company_id` → `hq_country` | `company_id` | Company is headquartered in country |
| `OPERATES` | Company → Facility | `synthetic_facility` | `company_id` → `facility_id` | `facility_id` | Company operates facility |
| `LOCATED_IN` | Facility → Country | `synthetic_facility` | `facility_id` → `country` | `facility_id` | Facility is in country |
| `SUPPLIES` | Company → Facility | `synthetic_supply` | `supplier_company_id` → `facility_id` | `supply_id` | Equipment or materials supply contract |
| `ALT_SUPPLIER_FOR` | Company → Facility | `synthetic_alt_supplier` | `supplier_company_id` → `facility_id` | `supplier_company_id`, `facility_id`, `supply_category` | Qualified backup supplier |
| `FABRICATES` | Facility → Part | `synthetic_fabrication` | `facility_id` → `part_id` | `facility_id`, `part_id` | Facility fabricates part |
| `PACKAGES` | Facility → Part | `synthetic_packaging` | `facility_id` → `part_id` | `facility_id`, `part_id` | Packaging plant packages part |
| `ALT_FOR` | Facility → Part | `synthetic_alt_facility` | `facility_id` → `part_id` | `facility_id`, `part_id`, `step` | Qualified backup facility for a part |
| `DESIGNS` | Company → Part | `synthetic_chip_part` | `designer_company_id` → `part_id` | `part_id` | Company designs part |
| `COMPONENT_OF` | Part → Part | `synthetic_part_component` | `component_part_id` → `parent_part_id` | `component_part_id`, `parent_part_id` | Part is a component of another part (e.g. HBM in an AI accelerator) |
| `USED_IN` | Part → Server | `synthetic_bom_line` | `part_id` → `product_id` | `part_id`, `product_id` | Bill of materials line |
| `MAKES` | Company → Server | `synthetic_end_product` | `maker_company_id` → `product_id` | `product_id` | Company makes server |
| `ASSEMBLES` | Facility → Server | `synthetic_assembly` | `facility_id` → `product_id` | `facility_id`, `product_id` | Assembly plant assembles server |
| `SOLD_INTO` | Server → Market | `synthetic_sales` | `product_id` → `market_id` | `product_id`, `market_id` | Server revenue by end market |
| `HOLDS_STOCK` | Facility → Part | `synthetic_stock` | `facility_id` → `part_id` | `facility_id`, `part_id`, `as_of_date` | Stock of a part at a facility, as days of supply |
| `RESTRICTS` | Country → Company | `synthetic_restriction` | `imposing_country` → `company_id` | `restriction_id` | Fictional export restriction on a company |
| `IMPACTS` | Event → Facility | `synthetic_event_impact` | `event_id` → `facility_id` | `event_id`, `facility_id` | Disruption affects facility |
| `INVOLVES` | Event → Country | `synthetic_event_country` | `event_id` → `country` | `event_id`, `country`, `relation` | Disruption's location, target or imposing country |
| `HAS_CAPACITY` | Facility → CapacitySnapshot | `synthetic_facility_capacity` | `facility_id` → `facility_id` + `year` | `facility_id`, `year` | Facility's capacity snapshot for a year |

Edge attributes:

- **TRADES**: `year` (Int), `hs_code` (String), `value_usd` (Long), `quantity_tonnes` (Double)
- **HQ_IN**: none
- **OPERATES**: none
- **LOCATED_IN**: none
- **SUPPLIES**: `supply_id` (String), `supply_category` (String), `hs_code` (String), `annual_value_usd` (Long), `share_of_need_pct` (Double), `lead_time_weeks` (Int), `contract_start` (Date), `contract_end` (Date), `data_source` (String), `confidence` (String)
- **ALT_SUPPLIER_FOR**: `supply_category` (String), `qualification_months` (Int), `spare_capacity_pct` (Double), `data_source` (String), `confidence` (String)
- **FABRICATES**: `share_of_part_volume_pct` (Double), `lead_time_weeks` (Int), `data_source` (String), `confidence` (String), `wafers_per_month` (Int)
- **PACKAGES**: `share_of_part_volume_pct` (Double), `lead_time_weeks` (Int), `data_source` (String), `confidence` (String)
- **ALT_FOR**: `step` (String), `qualification_months` (Int), `spare_capacity_pct` (Double), `data_source` (String), `confidence` (String)
- **DESIGNS**: none
- **COMPONENT_OF**: `quantity` (Int), `data_source` (String), `confidence` (String)
- **USED_IN**: `units_per_product` (Int)
- **MAKES**: none
- **ASSEMBLES**: `share_of_product_volume_pct` (Double), `lead_time_weeks` (Int)
- **SOLD_INTO**: `revenue_usd` (Long)
- **HOLDS_STOCK**: `as_of_date` (String), `units_on_hand` (Int), `daily_usage` (Double), `days_of_supply` (Double), `data_source` (String), `confidence` (String)
- **RESTRICTS**: `restriction_id` (String), `list_type` (String), `program` (String), `start_date` (Date), `license_policy` (String), `data_source` (String), `confidence` (String)
- **IMPACTS**: `distance_km` (Double), `capacity_loss_pct` (Double), `recovery_weeks` (Int), `reported_at` (String), `data_source` (String), `confidence` (String)
- **INVOLVES**: `relation` (String)
- **HAS_CAPACITY**: none

Edge ID columns are the table's unique key. Use them if the schema builder asks for an edge ID; a composite ID uses all the listed columns.

## Where Each Fact Comes From

The data is shaped like what an AI server maker could actually assemble about its supply chain. Tables that mix sources carry two columns (for facilities they apply to capacity and are called `capacity_source` and `capacity_confidence`):

| `data_source` | Meaning |
|---|---|
| `own_system` | The company's own records: bills of materials, plants, stock, approved manufacturer list |
| `supplier_disclosed` | Provided by a supplier, e.g. which sites make a part, or a continuity-survey answer |
| `third_party` | Bought from a data provider or risk-monitoring service |
| `public` | Public reporting, filings or screening lists |

`confidence` is `confirmed` or `estimated`. Some values are always estimates regardless of the row's confidence: `share_of_part_volume_pct` on `FABRICATES` and `PACKAGES`, `annual_value_usd` and `share_of_need_pct` on `SUPPLIES`, and `time_to_recover_weeks` on `Facility` (a self-reported survey answer). Event impacts carry `reported_at`, because estimates arrive days after an event and confirmed figures later.

Tables without these columns (servers, bills of materials, sales, chip parts, assembly) are the company's own data.

## Capacity: Current Value and History

- `Facility.capacity` is the facility's full capacity. For facilities with status `under_construction` or `planned` it is the planned capacity, not current output.
- `CapacitySnapshot` vertices hold the capacity in each year from 2017 to 2025, including the ramp-up after a facility opens (0 before it opens). Each has a composite ID of `facility_id` + `year` and hangs off its facility through `HAS_CAPACITY`. Filter on `year` to get a point in time, or follow all of them for a trend.

## SQL-Only Table

`product` (real, CEPII BACI) decodes HS codes into descriptions and supply chain stages. It is not part of the graph because the columns that would link to it contain blanks; join it in SQL for readable product names.

## Type Mapping

| Iceberg | PuppyGraph |
|---|---|
| STRING | String |
| INT | Int |
| BIGINT | Long |
| DOUBLE | Double |
| DATE | Date |
