# Queries

Simple questions are answered with SQL directly on the Iceberg tables. Questions that follow the supply chain across several steps are answered with Cypher on the PuppyGraph graph defined in `schema.json`, which reads the same tables without copying them.

Figures from real tables (`country`, `product`, `trade_flow`) are real. Any figure that touches a `synthetic_` table is illustrative. See the Dataset section of the [README](README.md).

## SQL: Questions a Table Can Answer

Run in the Spark SQL shell (`docker exec -it spark-iceberg spark-sql`).

### Who exports chip-making equipment? (real data)

```sql
SELECT exporter,
       ROUND(100 * SUM(value_usd) / SUM(SUM(value_usd)) OVER (), 1) AS share_pct
FROM ai_chip_supply_chain.trade_flow
WHERE year = 2024 AND hs_code = '848620'
GROUP BY exporter
ORDER BY share_pct DESC
LIMIT 5;
```

### Where does the US buy servers? 2017 vs 2024 (real data)

```sql
SELECT exporter,
       ROUND(SUM(CASE WHEN year = 2017 THEN value_usd END) / 1e9, 1) AS usd_bn_2017,
       ROUND(SUM(CASE WHEN year = 2024 THEN value_usd END) / 1e9, 1) AS usd_bn_2024
FROM ai_chip_supply_chain.trade_flow
WHERE importer = 'USA' AND hs_code = '847150' AND year IN (2017, 2024)
GROUP BY exporter
ORDER BY usd_bn_2024 DESC NULLS LAST
LIMIT 5;
```

### How many AI accelerators come from a single fab? (illustrative)

```sql
SELECT ROUND(100 * AVG(CASE WHEN fabs = 1 THEN 1 ELSE 0 END), 1) AS single_fab_pct
FROM (
  SELECT p.part_id, COUNT(f.facility_id) AS fabs
  FROM ai_chip_supply_chain.synthetic_chip_part p
  JOIN ai_chip_supply_chain.synthetic_fabrication f ON f.part_id = p.part_id
  WHERE p.part_type = 'ai_accelerator'
  GROUP BY p.part_id
) t;
```

## Cypher: Questions That Need the Graph

Run in the PuppyGraph web UI (http://localhost:8081) or any Cypher client on port 7687.

A part reaches a server either directly (`USED_IN`) or as a component of another part first (`COMPONENT_OF`, e.g. HBM inside an AI accelerator). The pattern `[:COMPONENT_OF|USED_IN*1..3]` follows both routes.

### 1. Export control: which servers and markets are exposed?

Hypothetical scenario V006: the US restricts wafer fab equipment exports to China. Starting from the imposing country, find Chinese facilities whose only source for a tool category is a US supplier, then follow what they make all the way to servers and end markets.
*Path: Event → Country ← Company → Facility → Part → (Part) → Server → Market, up to 9 hops.*

```cypher
MATCH (e:Event {event_id: 'V006'})-[imp:INVOLVES {relation: 'imposing'}]->(src:Country),
      (e)-[:INVOLVES {relation: 'target'}]->(dst:Country),
      (src)<-[:HQ_IN]-(:Company)-[s:SUPPLIES]->(f:Facility)-[:LOCATED_IN]->(dst)
WHERE s.hs_code = e.hs_code AND s.share_of_need_pct = 100
MATCH (f)-[:FABRICATES|PACKAGES]->(:Part)-[:COMPONENT_OF|USED_IN*1..3]->(srv:Server)
WITH DISTINCT srv
MATCH (srv)-[sale:SOLD_INTO]->(m:Market)
RETURN m.name AS market, count(srv) AS servers_exposed, sum(sale.revenue_usd) AS revenue_exposed_usd
ORDER BY revenue_exposed_usd DESC;
```

### 2. Earthquake: what breaks, and is there a backup?

Hypothetical scenario V001: an earthquake near Hsinchu. For each affected part, check whether a qualified backup facility exists outside the impact zone.
*Path: Event → Facility → Part → (Part) → Server, plus Part ← backup Facility.*

```cypher
MATCH (e:Event {event_id: 'V001'})-[:IMPACTS]->(f:Facility)-[:FABRICATES|PACKAGES]->(p:Part)
      -[:COMPONENT_OF|USED_IN*1..3]->(srv:Server)
OPTIONAL MATCH (b:Facility)-[:ALT_FOR]->(p)
WHERE NOT (e)-[:IMPACTS]->(b)
WITH p, collect(DISTINCT srv.name) AS servers, count(DISTINCT b) AS backups
RETURN p.part_number, p.part_type, size(servers) AS servers_affected, backups > 0 AS has_backup
ORDER BY servers_affected DESC
LIMIT 20;
```

### 3. Time to survive vs time to recover

Which parts run out of inventory before the affected facility recovers, and how much server revenue depends on them?
*Path: Event → Facility → Part → (Part) → Server → Market, comparing values along the path.*

```cypher
MATCH (e:Event {event_id: 'V001'})-[i:IMPACTS]->(f:Facility)-[m:FABRICATES|PACKAGES]->(p:Part)
WHERE i.recovery_weeks > m.inventory_weeks_on_hand
MATCH (p)-[:COMPONENT_OF|USED_IN*1..3]->(srv:Server)
WITH p, max(i.recovery_weeks - m.inventory_weeks_on_hand) AS gap_weeks, collect(DISTINCT srv) AS servers
UNWIND servers AS srv
MATCH (srv)-[sale:SOLD_INTO]->(:Market)
RETURN p.part_number, p.part_type, gap_weeks, sum(sale.revenue_usd) AS revenue_exposed_usd
ORDER BY revenue_exposed_usd DESC
LIMIT 20;
```

### 4. Hidden single points of failure

Servers whose bill of materials looks diversified, but which depend on a component made at only one facility, two or more tiers down.
*Path: Facility → component Part → Part → Server.*

```cypher
MATCH (f:Facility)-[:FABRICATES]->(c:Part)
WITH c, count(f) AS sites
WHERE sites = 1
MATCH (c)-[:COMPONENT_OF]->(parent:Part)-[:USED_IN]->(srv:Server)<-[:MAKES]-(maker:Company)
RETURN c.part_type AS sole_source_component, count(DISTINCT parent) AS parts_affected,
       count(DISTINCT srv) AS servers_affected, count(DISTINCT maker) AS server_makers_affected;
```

### 5. Sanctions exposure

Restricted companies and the servers that depend on what they design or make, directly or through other companies' facilities.
*Path: Country → Company → Part / Facility → Part → (Part) → Server ← Company.*

```cypher
MATCH (:Country)-[r:RESTRICTS]->(x:Company)
MATCH (x)-[:DESIGNS]->(p:Part)
MATCH (p)-[:COMPONENT_OF|USED_IN*1..3]->(srv:Server)<-[:MAKES]-(maker:Company)
RETURN x.name AS restricted_company, r.program, count(DISTINCT p) AS parts,
       count(DISTINCT srv) AS servers, collect(DISTINCT maker.name)[0..5] AS example_server_makers
ORDER BY servers DESC;
```

### 6. Servers behind a single lithography supplier

Facilities that buy lithography from only one Dutch supplier, and the servers that depend on them.
*Path: Country → Company → Facility → Part → (Part) → Server.*

```cypher
MATCH (:Country {iso3: 'NLD'})<-[:HQ_IN]-(s:Company)-[sup:SUPPLIES]->(f:Facility)
WHERE sup.supply_category = 'lithography' AND sup.share_of_need_pct = 100
MATCH (f)-[:FABRICATES]->(:Part)-[:COMPONENT_OF|USED_IN*1..3]->(srv:Server)
RETURN s.name AS lithography_supplier, count(DISTINCT f) AS sole_sourced_facilities,
       count(DISTINCT srv) AS servers_depending
ORDER BY servers_depending DESC;
```

## Side by Side: The Same Question in SQL

Query 1 in SQL. Spark SQL has no recursive queries, so each route from part to server (direct, through one component, through two) is written out by hand. Every new route means another branch.

```sql
WITH sole_sourced AS (
  SELECT s.facility_id
  FROM ai_chip_supply_chain.synthetic_disruption_event e
  JOIN ai_chip_supply_chain.synthetic_event_country src ON src.event_id = e.event_id AND src.relation = 'imposing'
  JOIN ai_chip_supply_chain.synthetic_event_country dst ON dst.event_id = e.event_id AND dst.relation = 'target'
  JOIN ai_chip_supply_chain.synthetic_company c ON c.hq_country = src.country
  JOIN ai_chip_supply_chain.synthetic_supply s ON s.supplier_company_id = c.company_id
       AND s.hs_code = e.hs_code AND s.share_of_need_pct = 100
  JOIN ai_chip_supply_chain.synthetic_facility f ON f.facility_id = s.facility_id AND f.country = dst.country
  WHERE e.event_id = 'V006'
),
made AS (
  SELECT facility_id, part_id FROM ai_chip_supply_chain.synthetic_fabrication
  UNION
  SELECT facility_id, part_id FROM ai_chip_supply_chain.synthetic_packaging
),
exposed_parts AS (
  SELECT DISTINCT m.part_id FROM made m JOIN sole_sourced ss ON ss.facility_id = m.facility_id
),
reachable_parts AS (
  SELECT part_id FROM exposed_parts                                                 -- the part itself
  UNION
  SELECT pc.parent_part_id FROM ai_chip_supply_chain.synthetic_part_component pc    -- one level up
  JOIN exposed_parts ep ON ep.part_id = pc.component_part_id
  UNION
  SELECT pc2.parent_part_id FROM ai_chip_supply_chain.synthetic_part_component pc1  -- two levels up
  JOIN exposed_parts ep ON ep.part_id = pc1.component_part_id
  JOIN ai_chip_supply_chain.synthetic_part_component pc2 ON pc2.component_part_id = pc1.parent_part_id
),
exposed_servers AS (
  SELECT DISTINCT b.product_id
  FROM ai_chip_supply_chain.synthetic_bom_line b JOIN reachable_parts rp ON rp.part_id = b.part_id
)
SELECT m.name AS market, COUNT(*) AS servers_exposed, SUM(s.revenue_usd) AS revenue_exposed_usd
FROM exposed_servers es
JOIN ai_chip_supply_chain.synthetic_sales s ON s.product_id = es.product_id
JOIN ai_chip_supply_chain.synthetic_end_market m ON m.market_id = s.market_id
GROUP BY m.name
ORDER BY revenue_exposed_usd DESC;
```
