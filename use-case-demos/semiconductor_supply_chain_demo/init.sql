-- AI chip supply chain demo: Iceberg tables.
-- Real tables (no prefix) come from CEPII BACI; tables prefixed synthetic_ are fictional.
-- See the Dataset section of README.md for details.
--
-- Run by init.sh. Safe to re-run: tables are created if missing and their contents replaced.

CREATE DATABASE IF NOT EXISTS ai_chip_supply_chain;

-- REAL (CEPII BACI). Countries.
CREATE TABLE IF NOT EXISTS ai_chip_supply_chain.country (
  iso3  STRING,
  iso2  STRING,
  name  STRING
) USING iceberg;

INSERT OVERWRITE ai_chip_supply_chain.country
SELECT
  CAST(iso3 AS STRING),
  CAST(iso2 AS STRING),
  CAST(name AS STRING)
FROM parquet.`/parquet_data/country.parquet`;

-- REAL (CEPII BACI). Traded products (HS codes) in the chip and AI server supply chain.
CREATE TABLE IF NOT EXISTS ai_chip_supply_chain.product (
  hs_code      STRING,
  description  STRING,
  stage        STRING
) USING iceberg;

INSERT OVERWRITE ai_chip_supply_chain.product
SELECT
  CAST(hs_code AS STRING),
  CAST(description AS STRING),
  CAST(stage AS STRING)
FROM parquet.`/parquet_data/product.parquet`;

-- REAL (CEPII BACI). Annual exporter -> importer trade, 2017-2024, flows >= $10M.
CREATE TABLE IF NOT EXISTS ai_chip_supply_chain.trade_flow (
  year             INT,
  exporter         STRING,
  importer         STRING,
  hs_code          STRING,
  value_usd        BIGINT,
  quantity_tonnes  DOUBLE
) USING iceberg;

INSERT OVERWRITE ai_chip_supply_chain.trade_flow
SELECT
  CAST(year AS INT),
  CAST(exporter AS STRING),
  CAST(importer AS STRING),
  CAST(hs_code AS STRING),
  CAST(value_usd AS BIGINT),
  CAST(quantity_tonnes AS DOUBLE)
FROM parquet.`/parquet_data/trade_flow.parquet`;

-- SYNTHETIC. Fictional companies and their supply chain role.
CREATE TABLE IF NOT EXISTS ai_chip_supply_chain.synthetic_company (
  company_id    STRING,
  name          STRING,
  role          STRING,
  subtype       STRING,
  hq_country    STRING,
  ownership     STRING,
  founded_year  INT,
  employees     INT
) USING iceberg;

INSERT OVERWRITE ai_chip_supply_chain.synthetic_company
SELECT
  CAST(company_id AS STRING),
  CAST(name AS STRING),
  CAST(role AS STRING),
  CAST(subtype AS STRING),
  CAST(hq_country AS STRING),
  CAST(ownership AS STRING),
  CAST(founded_year AS INT),
  CAST(employees AS INT)
FROM parquet.`/parquet_data/synthetic_company.parquet`;

-- SYNTHETIC. Fictional fabs, packaging, equipment, materials and assembly plants in real cities.
CREATE TABLE IF NOT EXISTS ai_chip_supply_chain.synthetic_facility (
  facility_id            STRING,
  company_id             STRING,
  name                   STRING,
  facility_type          STRING,
  city                   STRING,
  country                STRING,
  latitude               DOUBLE,
  longitude              DOUBLE,
  status                 STRING,
  hvm_start_year         INT,
  domain                 STRING,
  process_node           STRING,
  process_node_nm        DOUBLE,
  wafer_size_mm          INT,
  capacity               BIGINT,
  capacity_unit          STRING,
  time_to_recover_weeks  INT
) USING iceberg;

INSERT OVERWRITE ai_chip_supply_chain.synthetic_facility
SELECT
  CAST(facility_id AS STRING),
  CAST(company_id AS STRING),
  CAST(name AS STRING),
  CAST(facility_type AS STRING),
  CAST(city AS STRING),
  CAST(country AS STRING),
  CAST(latitude AS DOUBLE),
  CAST(longitude AS DOUBLE),
  CAST(status AS STRING),
  CAST(hvm_start_year AS INT),
  CAST(domain AS STRING),
  CAST(process_node AS STRING),
  CAST(process_node_nm AS DOUBLE),
  CAST(wafer_size_mm AS INT),
  CAST(capacity AS BIGINT),
  CAST(capacity_unit AS STRING),
  CAST(time_to_recover_weeks AS INT)
FROM parquet.`/parquet_data/synthetic_facility.parquet`;

-- SYNTHETIC. Capacity per facility per year.
CREATE TABLE IF NOT EXISTS ai_chip_supply_chain.synthetic_facility_capacity (
  facility_id    STRING,
  year           INT,
  capacity       BIGINT,
  capacity_unit  STRING
) USING iceberg;

INSERT OVERWRITE ai_chip_supply_chain.synthetic_facility_capacity
SELECT
  CAST(facility_id AS STRING),
  CAST(year AS INT),
  CAST(capacity AS BIGINT),
  CAST(capacity_unit AS STRING)
FROM parquet.`/parquet_data/synthetic_facility_capacity.parquet`;

-- SYNTHETIC. Chip parts: AI accelerators, HBM, CPUs, network chips, power chips, substrates.
CREATE TABLE IF NOT EXISTS ai_chip_supply_chain.synthetic_chip_part (
  part_id              STRING,
  part_number          STRING,
  part_type            STRING,
  designer_company_id  STRING,
  hs_code              STRING,
  process_node_nm      DOUBLE,
  unit_price_usd       DOUBLE
) USING iceberg;

INSERT OVERWRITE ai_chip_supply_chain.synthetic_chip_part
SELECT
  CAST(part_id AS STRING),
  CAST(part_number AS STRING),
  CAST(part_type AS STRING),
  CAST(designer_company_id AS STRING),
  CAST(hs_code AS STRING),
  CAST(process_node_nm AS DOUBLE),
  CAST(unit_price_usd AS DOUBLE)
FROM parquet.`/parquet_data/synthetic_chip_part.parquet`;

-- SYNTHETIC. AI servers and racks.
CREATE TABLE IF NOT EXISTS ai_chip_supply_chain.synthetic_end_product (
  product_id          STRING,
  maker_company_id    STRING,
  name                STRING,
  product_type        STRING,
  hs_code             STRING,
  unit_price_usd      DOUBLE,
  annual_units        INT,
  annual_revenue_usd  BIGINT
) USING iceberg;

INSERT OVERWRITE ai_chip_supply_chain.synthetic_end_product
SELECT
  CAST(product_id AS STRING),
  CAST(maker_company_id AS STRING),
  CAST(name AS STRING),
  CAST(product_type AS STRING),
  CAST(hs_code AS STRING),
  CAST(unit_price_usd AS DOUBLE),
  CAST(annual_units AS INT),
  CAST(annual_revenue_usd AS BIGINT)
FROM parquet.`/parquet_data/synthetic_end_product.parquet`;

-- SYNTHETIC. End markets for AI servers.
CREATE TABLE IF NOT EXISTS ai_chip_supply_chain.synthetic_end_market (
  market_id    STRING,
  name         STRING,
  description  STRING
) USING iceberg;

INSERT OVERWRITE ai_chip_supply_chain.synthetic_end_market
SELECT
  CAST(market_id AS STRING),
  CAST(name AS STRING),
  CAST(description AS STRING)
FROM parquet.`/parquet_data/synthetic_end_market.parquet`;

-- SYNTHETIC. Hypothetical disruption scenarios (not forecasts).
CREATE TABLE IF NOT EXISTS ai_chip_supply_chain.synthetic_disruption_event (
  event_id       STRING,
  name           STRING,
  event_type     STRING,
  scenario_note  STRING,
  start_date     DATE,
  severity       INT,
  latitude       DOUBLE,
  longitude      DOUBLE,
  radius_km      DOUBLE,
  hs_code        STRING
) USING iceberg;

INSERT OVERWRITE ai_chip_supply_chain.synthetic_disruption_event
SELECT
  CAST(event_id AS STRING),
  CAST(name AS STRING),
  CAST(event_type AS STRING),
  CAST(scenario_note AS STRING),
  CAST(start_date AS DATE),
  CAST(severity AS INT),
  CAST(latitude AS DOUBLE),
  CAST(longitude AS DOUBLE),
  CAST(radius_km AS DOUBLE),
  CAST(hs_code AS STRING)
FROM parquet.`/parquet_data/synthetic_disruption_event.parquet`;

-- SYNTHETIC edge: equipment / materials company -> facility.
CREATE TABLE IF NOT EXISTS ai_chip_supply_chain.synthetic_supply (
  supply_id                STRING,
  supplier_company_id      STRING,
  facility_id              STRING,
  supply_category          STRING,
  hs_code                  STRING,
  annual_value_usd         BIGINT,
  share_of_need_pct        DOUBLE,
  lead_time_weeks          INT,
  inventory_weeks_on_hand  INT,
  contract_start           DATE,
  contract_end             DATE
) USING iceberg;

INSERT OVERWRITE ai_chip_supply_chain.synthetic_supply
SELECT
  CAST(supply_id AS STRING),
  CAST(supplier_company_id AS STRING),
  CAST(facility_id AS STRING),
  CAST(supply_category AS STRING),
  CAST(hs_code AS STRING),
  CAST(annual_value_usd AS BIGINT),
  CAST(share_of_need_pct AS DOUBLE),
  CAST(lead_time_weeks AS INT),
  CAST(inventory_weeks_on_hand AS INT),
  CAST(contract_start AS DATE),
  CAST(contract_end AS DATE)
FROM parquet.`/parquet_data/synthetic_supply.parquet`;

-- SYNTHETIC edge: qualified backup supplier -> facility.
CREATE TABLE IF NOT EXISTS ai_chip_supply_chain.synthetic_alt_supplier (
  supplier_company_id   STRING,
  facility_id           STRING,
  supply_category       STRING,
  qualification_months  INT,
  spare_capacity_pct    DOUBLE
) USING iceberg;

INSERT OVERWRITE ai_chip_supply_chain.synthetic_alt_supplier
SELECT
  CAST(supplier_company_id AS STRING),
  CAST(facility_id AS STRING),
  CAST(supply_category AS STRING),
  CAST(qualification_months AS INT),
  CAST(spare_capacity_pct AS DOUBLE)
FROM parquet.`/parquet_data/synthetic_alt_supplier.parquet`;

-- SYNTHETIC edge: facility -> chip part it fabricates.
CREATE TABLE IF NOT EXISTS ai_chip_supply_chain.synthetic_fabrication (
  facility_id               STRING,
  part_id                   STRING,
  share_of_part_volume_pct  DOUBLE,
  lead_time_weeks           INT,
  inventory_weeks_on_hand   INT,
  wafers_per_month          INT
) USING iceberg;

INSERT OVERWRITE ai_chip_supply_chain.synthetic_fabrication
SELECT
  CAST(facility_id AS STRING),
  CAST(part_id AS STRING),
  CAST(share_of_part_volume_pct AS DOUBLE),
  CAST(lead_time_weeks AS INT),
  CAST(inventory_weeks_on_hand AS INT),
  CAST(wafers_per_month AS INT)
FROM parquet.`/parquet_data/synthetic_fabrication.parquet`;

-- SYNTHETIC edge: packaging plant -> chip part it packages.
CREATE TABLE IF NOT EXISTS ai_chip_supply_chain.synthetic_packaging (
  facility_id               STRING,
  part_id                   STRING,
  share_of_part_volume_pct  DOUBLE,
  lead_time_weeks           INT,
  inventory_weeks_on_hand   INT
) USING iceberg;

INSERT OVERWRITE ai_chip_supply_chain.synthetic_packaging
SELECT
  CAST(facility_id AS STRING),
  CAST(part_id AS STRING),
  CAST(share_of_part_volume_pct AS DOUBLE),
  CAST(lead_time_weeks AS INT),
  CAST(inventory_weeks_on_hand AS INT)
FROM parquet.`/parquet_data/synthetic_packaging.parquet`;

-- SYNTHETIC edge: qualified backup facility -> chip part.
CREATE TABLE IF NOT EXISTS ai_chip_supply_chain.synthetic_alt_facility (
  facility_id           STRING,
  part_id               STRING,
  step                  STRING,
  qualification_months  INT,
  spare_capacity_pct    DOUBLE
) USING iceberg;

INSERT OVERWRITE ai_chip_supply_chain.synthetic_alt_facility
SELECT
  CAST(facility_id AS STRING),
  CAST(part_id AS STRING),
  CAST(step AS STRING),
  CAST(qualification_months AS INT),
  CAST(spare_capacity_pct AS DOUBLE)
FROM parquet.`/parquet_data/synthetic_alt_facility.parquet`;

-- SYNTHETIC edge: component part -> parent part (e.g. HBM -> AI accelerator).
CREATE TABLE IF NOT EXISTS ai_chip_supply_chain.synthetic_part_component (
  component_part_id  STRING,
  parent_part_id     STRING,
  quantity           INT
) USING iceberg;

INSERT OVERWRITE ai_chip_supply_chain.synthetic_part_component
SELECT
  CAST(component_part_id AS STRING),
  CAST(parent_part_id AS STRING),
  CAST(quantity AS INT)
FROM parquet.`/parquet_data/synthetic_part_component.parquet`;

-- SYNTHETIC edge: chip part -> AI server (bill of materials).
CREATE TABLE IF NOT EXISTS ai_chip_supply_chain.synthetic_bom_line (
  part_id            STRING,
  product_id         STRING,
  units_per_product  INT
) USING iceberg;

INSERT OVERWRITE ai_chip_supply_chain.synthetic_bom_line
SELECT
  CAST(part_id AS STRING),
  CAST(product_id AS STRING),
  CAST(units_per_product AS INT)
FROM parquet.`/parquet_data/synthetic_bom_line.parquet`;

-- SYNTHETIC edge: assembly plant -> AI server.
CREATE TABLE IF NOT EXISTS ai_chip_supply_chain.synthetic_assembly (
  facility_id                  STRING,
  product_id                   STRING,
  share_of_product_volume_pct  DOUBLE,
  lead_time_weeks              INT,
  inventory_weeks_on_hand      INT
) USING iceberg;

INSERT OVERWRITE ai_chip_supply_chain.synthetic_assembly
SELECT
  CAST(facility_id AS STRING),
  CAST(product_id AS STRING),
  CAST(share_of_product_volume_pct AS DOUBLE),
  CAST(lead_time_weeks AS INT),
  CAST(inventory_weeks_on_hand AS INT)
FROM parquet.`/parquet_data/synthetic_assembly.parquet`;

-- SYNTHETIC edge: AI server -> end market.
CREATE TABLE IF NOT EXISTS ai_chip_supply_chain.synthetic_sales (
  product_id   STRING,
  market_id    STRING,
  revenue_usd  BIGINT
) USING iceberg;

INSERT OVERWRITE ai_chip_supply_chain.synthetic_sales
SELECT
  CAST(product_id AS STRING),
  CAST(market_id AS STRING),
  CAST(revenue_usd AS BIGINT)
FROM parquet.`/parquet_data/synthetic_sales.parquet`;

-- SYNTHETIC edge: EDA / IP vendor -> chip designer.
CREATE TABLE IF NOT EXISTS ai_chip_supply_chain.synthetic_license (
  vendor_company_id    STRING,
  licensee_company_id  STRING,
  license_type         STRING,
  annual_fee_usd       BIGINT
) USING iceberg;

INSERT OVERWRITE ai_chip_supply_chain.synthetic_license
SELECT
  CAST(vendor_company_id AS STRING),
  CAST(licensee_company_id AS STRING),
  CAST(license_type AS STRING),
  CAST(annual_fee_usd AS BIGINT)
FROM parquet.`/parquet_data/synthetic_license.parquet`;

-- SYNTHETIC edge: country -> restricted company (fictional restrictions).
CREATE TABLE IF NOT EXISTS ai_chip_supply_chain.synthetic_restriction (
  restriction_id    STRING,
  imposing_country  STRING,
  company_id        STRING,
  list_type         STRING,
  program           STRING,
  start_date        DATE,
  license_policy    STRING
) USING iceberg;

INSERT OVERWRITE ai_chip_supply_chain.synthetic_restriction
SELECT
  CAST(restriction_id AS STRING),
  CAST(imposing_country AS STRING),
  CAST(company_id AS STRING),
  CAST(list_type AS STRING),
  CAST(program AS STRING),
  CAST(start_date AS DATE),
  CAST(license_policy AS STRING)
FROM parquet.`/parquet_data/synthetic_restriction.parquet`;

-- SYNTHETIC edge: disruption event -> affected facility.
CREATE TABLE IF NOT EXISTS ai_chip_supply_chain.synthetic_event_impact (
  event_id           STRING,
  facility_id        STRING,
  distance_km        DOUBLE,
  capacity_loss_pct  DOUBLE,
  recovery_weeks     INT
) USING iceberg;

INSERT OVERWRITE ai_chip_supply_chain.synthetic_event_impact
SELECT
  CAST(event_id AS STRING),
  CAST(facility_id AS STRING),
  CAST(distance_km AS DOUBLE),
  CAST(capacity_loss_pct AS DOUBLE),
  CAST(recovery_weeks AS INT)
FROM parquet.`/parquet_data/synthetic_event_impact.parquet`;

-- SYNTHETIC edge: disruption event -> country (location, target or imposing).
CREATE TABLE IF NOT EXISTS ai_chip_supply_chain.synthetic_event_country (
  event_id  STRING,
  country   STRING,
  relation  STRING
) USING iceberg;

INSERT OVERWRITE ai_chip_supply_chain.synthetic_event_country
SELECT
  CAST(event_id AS STRING),
  CAST(country AS STRING),
  CAST(relation AS STRING)
FROM parquet.`/parquet_data/synthetic_event_country.parquet`;
