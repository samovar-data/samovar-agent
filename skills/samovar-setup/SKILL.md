---
name: samovar-setup
description: Set up or repair the Samovar Data analyst plugin - check uv, install the pinned DuckDB extensions, configure the S3 key and verify access. Use when the user installs the plugin, when samovar tools report a missing key or extension, or when the user asks to connect their Samovar Data.
---

# Samovar Data analyst: setup

Follow these steps in order and stop at the first one that fails, explaining the fix to the user.

1. **uv.** The MCP server runs with [uv](https://docs.astral.sh/uv/). Check it with `uv --version`. If it is
   missing, ask the user to install it and restart Claude Code.
2. **DuckDB extensions and the chart library.** Call the `status` tool and run the exact `setup_command` it returns (absolute paths of
   this installation). If the tool is not available yet, run:

   ```bash
   UV_PROJECT_ENVIRONMENT="${CLAUDE_PLUGIN_DATA}/venv" SAMOVAR_DATA_DIR="${CLAUDE_PLUGIN_DATA}" \
     uv run --frozen --quiet --no-dev --project "${CLAUDE_PLUGIN_ROOT}/server" samovar-agent setup
   ```

   It downloads the pinned DuckDB extensions from extensions.duckdb.org and the pinned chart library (samovar-chart)
   from the Samovar Data public storage, and refuses any file whose sha256 differs from the pinned manifests. Show
   the user the sha256 lines from the output.
3. **S3 key.** An admin of the organisation creates a read-only S3 key in the Samovar Data cabinet (S3 keys); the
   secret is shown once. The user enters its Access Key ID, Secret Access Key and bucket (and the endpoint and
   region, if they differ from the defaults) in the plugin settings (`/plugin`, the plugin's configuration). Claude
   Code stores the key and the secret in the system keychain. Never ask the user to paste the key or the secret into
   the chat, and never print them. If the storage refuses the key, it was mistyped, revoked or has expired (a key
   lives a year): a new one is created in the cabinet.
4. **Verify.** Call `describe_data` first: `data_access` must be `ok` and the tables of the connected sources `available` (if it reports that
   no data is published yet, there is nothing to fix on the user's side). Then call `status`: `problems` must be
   empty.
