# Security

## Reporting

Please report vulnerabilities privately to Samovar Data (samovardata.ru) rather than in public issues. Include the
version, the steps to reproduce and the impact. We acknowledge reports within a few working days.

## Design

- **The client's own S3 key.** The agent reads data with a read-only S3 key that an admin of the organisation
  creates in the Samovar Data cabinet (S3 keys). It is a permanent key (it lives a year and is not renewed) that
  reads only what the platform's bucket policy allows it in the organisation's bucket (the DuckDB map of the views
  and the tables it points to); the policy, not the plugin, is the limit inside the bucket.
  The Access Key ID and the Secret Access Key are sensitive plugin options: Claude Code keeps them in the system
  keychain and passes them to the local MCP server through its environment, never through command-line arguments.
  The server holds them in memory only, sends them only to the configured S3 endpoint (as a DuckDB secret that is
  never persisted), and never writes them to disk or logs. A key that leaks is revoked in the cabinet.
- **Locked query engine.** DuckDB runs with extension autoinstall/autoload off, community and unsigned extensions
  refused, persistent (user-stored) secrets ignored, file and network access limited to the key's own bucket
  (`allowed_directories`; the local fixture folder in fixture mode), so nothing outside it can be read even with a
  valid key, and the configuration locked before any user query.
  Extensions are installed only by `samovar-agent setup`, from a pinned manifest with sha256 checks; DuckDB also
  verifies their signatures.
- **SQL guard.** Only one SELECT, parsed by DuckDB itself (the LIMIT-wrapped text is parsed again before it runs);
  only views listed by the catalog or present in the mapping; no file readers, settings, secret, variable or
  environment functions; detail-layer queries must bound the table's day column with DATE literals, and the window
  is limited.
- **No secrets in output.** Tool results, errors and logs are redacted (the S3 key, credential fields, presigned
  URLs). Logs go to stderr.
- **Charts.** The chart library (samovar-chart, ECharts inside) is downloaded only by `samovar-agent setup`, from the
  pinned version in Object Storage; the sha256 of its manifest is pinned in the plugin and every file is checked
  against the manifest before anything is written, and again before every chart (no cached copy). One
  self-contained HTML file per chart: the library and the theme are inlined, the page has a Content-Security-Policy
  with script hashes (no CDN, no eval), the payload is validated against the library's schema, tooltips are drawn on
  the canvas.
- **No telemetry.** The MCP SDK's OpenTelemetry middleware is removed and the server refuses to start if a tracer
  provider or SDK is present.
- **Network.** Every place the plugin connects to:
  - `uv run --frozen` (Claude Code starting the server, `samovar-agent setup`): PyPI, to install the locked Python
    packages into the plugin's data folder on first start, and, when no Python 3.12 is installed, uv's managed
    Python build from GitHub (python-build-standalone);
  - `samovar-agent setup` only: `extensions.duckdb.org` (the pinned DuckDB extensions) and `global.s3.cloud.ru`
    (the pinned samovar-chart library in the `samovar-data-static` bucket);
  - while answering: the platform URL (`GET /api/v1/catalog`, public, no credentials sent) and the configured S3
    endpoint (`s3.cloud.ru` by default) with the S3 key.
  - demo mode only (`SAMOVAR_DATA_MODE=demo`): `samovar-demo.s3.cloud.ru`, one anonymous `GET /mapping/<sha256>.duckdb`
    (about 3 MB of synthetic data, public read on `mapping/*` only, no credentials sent). The file name and the sha256
    are pinned in the plugin (`demo-snapshot.json`); the body is hashed before anything is written, a mismatch is
    refused, the file is cached under its hash (atomic rename), re-checked on every start and attached read-only with
    file access limited to that folder, no extensions and no S3. The size is limited to 32 MB. A new snapshot is a
    new plugin version.
  The plugin's own HTTP client and the S3 endpoint accept HTTPS only (plain HTTP only to a loopback host, for local
  development); the HTTP client never follows redirects. Nothing else is sent anywhere.
- **Personal data.** The platform loads only an allowlist of source fields and leaves personal data out; the
  catalog lists what is excluded and why (`excluded`) and warns, in the notes of a table, about free-text fields
  that are loaded as entered (for example amoCRM tag and source names). The agent reads only the `dds` and `mart`
  views of the tenant's mapping, which the platform builds from that allowlist.
