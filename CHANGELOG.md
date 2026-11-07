# Changelog

## 0.1.0 (unreleased)

- Specification: JSON Schemas of the catalog fields the agent reads and of the MCP tools, generated from their
  sources; an example catalog (a copy of the platform's `/api/v1/catalog`).
- Local stdio MCP server `samovar-agent` (Python 3.12, uv): `describe_data`, `run_query`, `make_chart`, `export`,
  `status`; DuckDB 1.5.4 locked down (no autoinstall, file and network access limited to the tenant data,
  configuration locked); SQL guard on DuckDB's parser (one SELECT, known views only, bounded day windows on the
  detail layer with DATE literals); interactive charts as self-contained HTML; CSV, JSON and XLSX exports with the
  SQL; tool output, errors and logs redacted.
- Data access with the client's own read-only S3 key from the cabinet: the mapping of the views and the Iceberg
  tables of the bucket are read directly, without a platform call.
- Table descriptions from the platform's public catalog (Yandex Metrika and amoCRM), the same document the cabinet
  shows; no domain facts in the skills.
- `samovar-agent setup`: pinned DuckDB extensions (httpfs, avro, iceberg) and the pinned samovar-chart library, both
  verified by sha256.
- Charts come from the separate samovar-chart library (pinned published version 0.1.1, Apache ECharts inside); the
  plugin keeps no chart code and validates payloads against the library's schema. The site theme is bundled.
- Claude Code plugin: manifest, local marketplace, MCP configuration, `samovar-analyst` and `samovar-setup` skills.
- Evals: deterministic synthetic tenant (Metrika and amoCRM) and 46 questions (answers, honest refusals, guard
  rejections).
