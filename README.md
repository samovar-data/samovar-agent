# samovar-agent

Plain-language analytics over your own data in [Samovar Data](https://samovardata.ru): ask "what happened with
traffic last week?" and get a checked SQL query, a table, a chart and an export (CSV, JSON, XLSX).

The agent is a local [MCP](https://modelcontextprotocol.io) server plus skills. MVP: a Claude Code plugin. Planned:
a Codex plugin over the same server and a chat in the Samovar Data cabinet.

> **Status: 0.2.0, pre-release.** The agent reads your data with your own read-only S3 key from the cabinet and the
> table descriptions from the platform's public catalog; the platform needs no change for it.

## Русский кратко

- **Установка:** `/plugin marketplace add samovar-data/samovar-agent`, затем `/plugin install samovar-agent@samovar-data`.
  Нужен [uv](https://docs.astral.sh/uv/).
- **Настройка:** администратор организации создаёт в кабинете Samovar Data S3-ключ только на чтение (раздел
  «S3-ключи»). При включении плагина введите Access Key ID, Secret Access Key и бакет этого ключа (ключ и секрет
  хранятся в системной связке ключей; endpoint и регион по умолчанию облачные). Затем попросите «настрой samovar» —
  скилл `samovar-setup` один раз скачает расширения DuckDB (httpfs, avro, iceberg) и библиотеку графиков со сверкой
  sha256.
- **Вопрос:** «Что у меня с трафиком за прошлую неделю? Разбей по источникам и нарисуй график» или «Сколько сделок
  выиграли в amoCRM за неделю?». Агент читает описания таблиц из каталога Samovar Data, пишет SQL, проверяет
  результат, показывает SQL и версию каталога и предлагает выгрузку.
- Описания таблиц и колонок в плагин не зашиты: они берутся из публичного каталога платформы
  (`/api/v1/catalog`, тот же документ, что показывает кабинет).

## Try it without a key (demo data)

Set the plugin option "Data: platform or demo" to `demo` (or `SAMOVAR_DATA_MODE=demo`) and ask a question. The plugin
downloads a public snapshot (about 3 MB) of **synthetic** Samovar Data, a made-up tea shop with Yandex Metrika and
amoCRM over 120 days, checks its sha256, keeps it in the plugin data folder (it then works offline) and moves its dates
so that the latest day is yesterday. Answers are marked `data_mode: "demo"`. Example: *"Which campaign earns the most
revenue per visit?"* Set the option back to `platform` and enter your S3 key to use your own data.

Демо без ключа: выставьте опцию плагина «Data: platform or demo» в `demo` (или `SAMOVAR_DATA_MODE=demo`) и задайте
вопрос. Плагин скачает открытый снимок (около 3 МБ) **синтетических** данных Samovar Data (вымышленный магазин чая:
Яндекс Метрика и amoCRM за 120 дней), сверит sha256, сохранит его в папке данных плагина (дальше работает офлайн) и
сдвинет даты так, чтобы последний день был вчерашним. Ответы помечены `data_mode: "demo"`. Для своих данных верните
`platform` и введите S3-ключ.

## Install (Claude Code)

Requirements: Claude Code, [uv](https://docs.astral.sh/uv/) on `PATH`.

```text
/plugin marketplace add samovar-data/samovar-agent
/plugin install samovar-agent@samovar-data
```

When the plugin is enabled, Claude Code asks for:

| Option | Meaning |
|---|---|
| S3 key: Access Key ID, Secret Access Key (sensitive) | A read-only S3 key an admin creates in the cabinet (S3 keys); kept in the system keychain |
| S3 key: bucket, endpoint, region | Shown with the key in the cabinet; endpoint `https://s3.cloud.ru` and region `ru-central-1` by default |
| Platform URL | `https://samovardata.ru` by default; the table descriptions come from its `/api/v1/catalog` |
| Output folder | Where charts and exports go, relative to the project (`samovar-output`) |

DuckDB in the agent may read only inside the bucket of the key; which folders of it the key may read is set by the
platform's bucket policy (the plugin attaches `mapping/samovar.duckdb` and follows its views). The key lives a year
and is not renewed: create a new one in the cabinet before it expires, and revoke the old one there.

Environment-only settings:

| Variable | Default | Meaning |
|---|---|---|
| `SAMOVAR_TIMEZONE` | `Europe/Moscow` | Zone of "today"; each source's day (`dt`) is in its own zone, see each table's day rule |
| `SAMOVAR_CATALOG_URL` | `<platform URL>/api/v1/catalog` | Another catalog, e.g. `file://…` for offline work |
| `SAMOVAR_S3_URL_STYLE` | `vhost` | `path` for a local MinIO |
| `SAMOVAR_DDS_WINDOW_DAYS` | 93 | Longest day window of a detail-layer query |
| `SAMOVAR_MAX_ROWS` | 500 | Rows a query returns to the model |
| `SAMOVAR_EXPORT_MAX_ROWS` | 100000 | Rows an export writes |
| `SAMOVAR_TIMEOUT_SECONDS` | 30 | Query time limit |
| `SAMOVAR_MEMORY_LIMIT` | `1GB` | DuckDB memory limit |
| `SAMOVAR_THREADS` | 2 | DuckDB threads |
| `SAMOVAR_DATA_MODE` | `platform` | `platform` (your S3 key) or `demo` (the public synthetic snapshot) |

Then ask Claude to "set up samovar" (skill `samovar-setup`), which runs once:

```bash
samovar-agent setup   # downloads the pinned DuckDB extensions and the chart library and checks their sha256
```

Example: *"How did visits change last week compared to the week before? Show a chart and export it to Excel."*

## How it works

- `describe_data` reads the platform's catalog (sources, tables, grain, keys, day rule, notes, columns) and marks
  which views the tenant's mapping has (whether the key may read them is the bucket policy's). Yandex Metrika and
  amoCRM are described; the day of each source is in its own timezone (the counter's, the account's).
- `run_query` accepts one SELECT over `dds.*` (detail) and `mart.*` (daily marts) views, checked by DuckDB's own
  parser; detail queries need a bounded day filter. DuckDB 1.5.4 runs locked (see [SECURITY.md](SECURITY.md)).
- `make_chart` turns a ChartSpec into one self-contained, interactive HTML page drawn by the samovar-chart library
  (published bundle: [samovar-chart 0.1.1](https://global.s3.cloud.ru/samovar-data-static/samovar-chart/0.1.1/manifest.json),
  Apache ECharts inside), inlined from the locally installed, sha256-checked copy under a strict CSP (no CDN): the
  site theme (bundled) in light and dark, labels from the agent, the data and the SQL, a "save as PNG" button.
  The payload is checked against the library's own JSON Schema first. `export` writes CSV, JSON or XLSX with the SQL
  next to it. Output names are short ASCII (`<slug>-<id>.<ext>`).
- `status` reports versions, today's date in the data's timezone, key and extension readiness and the exact setup
  command.

Contracts live in [`spec/`](spec): `catalog.schema.json` (the catalog fields the agent reads) and `tools.schema.json`,
generated from the code, and `examples/catalog.demo.json`, a copy of the platform's `/api/v1/catalog`. The chart
contract (ChartSpec, payload, theme schemas) belongs to samovar-chart and is published with each of its versions.
The chart theme is bundled with the plugin; nothing is fetched for it.

The plugin keeps no chart code. `server/src/samovar_agent/charts/chart-dist.json` pins one published version of
samovar-chart: its version, URL (`https://global.s3.cloud.ru/samovar-data-static/samovar-chart/<version>/`) and the
sha256 of its `manifest.json`, which lists the sha256 of every file. `samovar-agent setup` downloads that version
into the plugin data folder (like the DuckDB extensions) and installs nothing that does not match; every chart
re-checks the installed copy. For development, `SAMOVAR_CHART_DIST_DIR=../samovar-chart/dist` installs from a local
build instead (still checked against the pin).

## Development

```bash
scripts/check            # the gate: SQL scan, empty __init__.py, black, isort, flake8, strict mypy, schemas, pytest,
                         # and the chart contract against ../samovar-chart/dist when that build exists
scripts/check --fix      # format
cd server
uv run python -m samovar_dev.tenant_fixture ../evals/.fixture        # synthetic tenant (deterministic, no personal data)
uv run python -m samovar_dev.evals ../evals ../evals/.fixture       # 46 eval questions through the guard and engine
uv run python -m samovar_dev.schemas ../spec                        # regenerate spec/*.schema.json
uv run python -m samovar_dev.chart_contract ../../samovar-chart/dist  # pin, schemas and payloads vs a local library build
curl -fsS https://samovardata.ru/api/v1/catalog -o ../spec/examples/catalog.demo.json   # refresh the example catalog
SAMOVAR_DATA_MODE=fixture SAMOVAR_FIXTURE_DIR=../evals/.fixture \
  SAMOVAR_CATALOG_URL=file://$PWD/../spec/examples/catalog.demo.json uv run samovar-agent status
```

The Iceberg read test (`tests/integration/test_iceberg.py`) needs the pinned extensions: run `samovar-agent setup`
once (it installs them into `~/.samovar-agent/ext`) or point `SAMOVAR_TEST_EXTENSION_DIR` at a folder with them;
without them the test is skipped.

Code rules: one composition root (`samovar_agent/composition.py`) reads the environment and wires everything;
ports (`Protocol`) only at external boundaries (HTTP, data access, catalog source, clock) or where several
implementations exist; SQL only in `.sql` files (`server/src/*/sql/`, `server/tests/sql/`), rendered from typed parts;
`__init__.py` files are empty; domain errors do not subclass built-in exceptions; tests fake the ports and state what
they prove. Third-party phone-home is disabled and asserted at start-up.

## License

[Business Source License 1.1](LICENSE): production use only in connection with the Samovar Data service; each
version converts to Apache-2.0 four years after its publication.
