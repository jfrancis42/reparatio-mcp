# reparatio-mcp

MCP server for [Reparatio](https://reparatio.app) — inspect, convert, merge, append, and query local data files directly from your AI assistant.

Supports CSV, TSV, Excel (.xlsx / .xls), ODS, JSON, JSONL, GeoJSON, Parquet, Feather, Arrow, ORC, Avro, SQLite, and gzip-compressed variants.

---

## How it works

The MCP server runs locally on your machine. When your AI assistant calls a tool, the server reads the file from your disk, sends it to the Reparatio API for processing, and writes the result back to disk — returning the output path to the assistant. Binary data never passes through the MCP protocol layer; only file paths and options travel as JSON.

---

## Prerequisites

- **Python 3.11 or later** — check with `python3 --version`
- **A Reparatio API key** — required for convert, merge, append, and query. `inspect_file` works without a key.
  - Get a key at [reparatio.app](https://reparatio.app) (Monthly plan)
  - Keys are prefixed with `rp_`

`uvx` (from [uv](https://github.com/astral-sh/uv)) is the recommended way to run the server — no install step required. Install uv with:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Installation

**Option A — run without installing (recommended):**

```bash
uvx reparatio-mcp
```

**Option B — install permanently:**

```bash
pip install reparatio-mcp
```

---

## Client configuration

MCP is a client-side protocol. Your AI assistant application needs to support MCP tool calls. The sections below cover every major client. The LLM backend (Claude, GPT-4o, Grok, DeepSeek, Gemini, a local Ollama model, etc.) is configured separately inside each client — the MCP server works with any of them.

---

### Claude Desktop

Edit `claude_desktop_config.json`:

| Platform | Path |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

```json
{
  "mcpServers": {
    "reparatio": {
      "command": "uvx",
      "args": ["reparatio-mcp"],
      "env": {
        "REPARATIO_API_KEY": "rp_YOUR_KEY"
      }
    }
  }
}
```

Restart Claude Desktop after saving. You should see "reparatio" listed under MCP servers in the app.

---

### Cursor

Cursor supports MCP servers globally or per-project.

**Global** (`~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "reparatio": {
      "command": "uvx",
      "args": ["reparatio-mcp"],
      "env": {
        "REPARATIO_API_KEY": "rp_YOUR_KEY"
      }
    }
  }
}
```

**Per-project** (`.cursor/mcp.json` in your project root) — same format.

Reload the MCP server list in **Cursor Settings → MCP** after saving.

---

### Windsurf

Edit `~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "reparatio": {
      "command": "uvx",
      "args": ["reparatio-mcp"],
      "env": {
        "REPARATIO_API_KEY": "rp_YOUR_KEY"
      }
    }
  }
}
```

---

### VS Code — GitHub Copilot

VS Code 1.99+ supports MCP natively. Add to your `settings.json` (`Ctrl+Shift+P` → "Open User Settings (JSON)"):

```json
{
  "mcp": {
    "servers": {
      "reparatio": {
        "type": "stdio",
        "command": "uvx",
        "args": ["reparatio-mcp"],
        "env": {
          "REPARATIO_API_KEY": "rp_YOUR_KEY"
        }
      }
    }
  }
}
```

---

### VS Code — Continue

[Continue](https://www.continue.dev/) is a VS Code / JetBrains extension that supports many LLM backends (OpenAI, Anthropic, DeepSeek, Grok, Gemini, Ollama, and more) alongside MCP tool servers.

Edit `~/.continue/config.json`:

```json
{
  "mcpServers": [
    {
      "name": "reparatio",
      "command": "uvx",
      "args": ["reparatio-mcp"],
      "env": {
        "REPARATIO_API_KEY": "rp_YOUR_KEY"
      }
    }
  ]
}
```

Continue handles the LLM connection separately. Reparatio tools are available regardless of which model you point Continue at.

---

### Zed

Edit `~/.config/zed/settings.json`:

```json
{
  "context_servers": {
    "reparatio": {
      "command": {
        "path": "uvx",
        "args": ["reparatio-mcp"],
        "env": {
          "REPARATIO_API_KEY": "rp_YOUR_KEY"
        }
      }
    }
  }
}
```

---

### Open WebUI (Ollama and others)

[Open WebUI](https://github.com/open-webui/open-webui) is a self-hosted chat interface that works with Ollama, OpenAI-compatible APIs, and others, and supports MCP tool servers.

1. Go to **Settings → Tools → MCP Servers**
2. Add a new server:
   - **Command:** `uvx reparatio-mcp`
   - **Environment:** `REPARATIO_API_KEY=rp_YOUR_KEY`
3. Save and reload.

The tools will be available to whichever model you have selected — Llama 3, Mistral, Qwen, DeepSeek-R1, or any other Ollama model.

---

### Claude Code (CLI)

Add to your project's `.mcp.json` or run inline:

```json
{
  "mcpServers": {
    "reparatio": {
      "command": "uvx",
      "args": ["reparatio-mcp"],
      "env": {
        "REPARATIO_API_KEY": "rp_YOUR_KEY"
      }
    }
  }
}
```

---

## Available tools

### `inspect_file`

Detect encoding, count rows, list column types and statistics, and return a data preview.
**No API key required.**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `path` | string | required | Local file path |
| `no_header` | bool | `false` | Treat first row as data (CSV/TSV) |
| `fix_encoding` | bool | `true` | Auto-detect and repair encoding |
| `delimiter` | string | `""` | Custom delimiter (auto-detected if blank) |
| `sheet` | string | `""` | Sheet or table name for Excel, ODS, SQLite |
| `preview_rows` | int | `8` | Preview rows to return (1–100) |

---

### `convert_file`

Convert a file from any supported input format to any supported output format.
**Monthly plan required.**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `input_path` | string | required | Source file path |
| `target_format` | string | required | Output format: `csv`, `tsv`, `csv.gz`, `csv.bz2`, `csv.zst`, `csv.zip`, `tsv.gz`, `tsv.bz2`, `tsv.zst`, `tsv.zip`, `xlsx`, `ods`, `json`, `json.bz2`, `json.zst`, `json.zip`, `jsonl`, `jsonl.gz`, `jsonl.bz2`, `jsonl.zst`, `jsonl.zip`, `geojson`, `geojson.gz`, `geojson.bz2`, `geojson.zst`, `parquet`, `feather`, `arrow`, `orc`, `avro`, `sqlite` |
| `output_path` | string | auto | Where to save the result |
| `no_header` | bool | `false` | Treat first row as data |
| `fix_encoding` | bool | `true` | Repair encoding |
| `delimiter` | string | `""` | Custom delimiter for CSV-like input |
| `sheet` | string | `""` | Sheet or table to read |
| `columns` | array | `[]` | Rename columns — new names in order |
| `select_columns` | array | `[]` | Columns to include (all if omitted) |
| `deduplicate` | bool | `false` | Remove duplicate rows |
| `sample_n` | int | — | Random sample of N rows |
| `sample_frac` | float | — | Random sample fraction (e.g. `0.1` for 10%) |
| `geometry_column` | string | `"geometry"` | WKT geometry column for GeoJSON output |

---

### `merge_files`

Merge two files using a SQL-style join or append (row-stacking).
**Monthly plan required.**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `file1_path` | string | required | First file path |
| `file2_path` | string | required | Second file path |
| `operation` | string | required | `append`, `left`, `right`, `outer`, or `inner` |
| `target_format` | string | required | Output format |
| `output_path` | string | auto | Where to save the result |
| `join_on` | string | `""` | Comma-separated column name(s) to join on |
| `no_header` | bool | `false` | Treat first row as data |
| `fix_encoding` | bool | `true` | Repair encoding |

**Operations:**

| Value | Behaviour |
|---|---|
| `append` | Stack all rows from both files; missing columns filled with null |
| `left` | All rows from file 1; matching columns from file 2 |
| `right` | All rows from file 2; matching columns from file 1 |
| `outer` | All rows from both files; nulls where no match |
| `inner` | Only rows matching in both files |

---

### `append_files`

Stack rows from two or more files vertically. Handles column mismatches gracefully.
**Monthly plan required.**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `paths` | array | required | List of file paths (minimum 2) |
| `target_format` | string | required | Output format |
| `output_path` | string | auto | Where to save the result |
| `no_header` | bool | `false` | Treat first row as data |
| `fix_encoding` | bool | `true` | Repair encoding |

---

### `query_file`

Run a SQL query against a file. The file is loaded as a table named `data`.
**Monthly plan required.**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `path` | string | required | Source file path |
| `sql` | string | required | SQL query (table name: `data`) |
| `target_format` | string | `"csv"` | Output format |
| `output_path` | string | auto | Where to save the result |
| `no_header` | bool | `false` | Treat first row as data |
| `fix_encoding` | bool | `true` | Repair encoding |
| `delimiter` | string | `""` | Custom delimiter for CSV-like input |
| `sheet` | string | `""` | Sheet or table to read |

Supports `SELECT`, `WHERE`, `GROUP BY`, `ORDER BY`, `LIMIT`, aggregations, and most scalar functions.

---

## Supported formats

| Format | Input | Output |
|---|---|---|
| CSV | ✓ | ✓ |
| TSV | ✓ | ✓ |
| CSV.GZ (gzip) | ✓ | ✓ |
| CSV.BZ2 (bzip2) | ✓ | ✓ |
| CSV.ZST (zstd) | ✓ | ✓ |
| CSV.ZIP | — | ✓ |
| TSV.GZ (gzip) | ✓ | ✓ |
| TSV.BZ2 (bzip2) | ✓ | ✓ |
| TSV.ZST (zstd) | ✓ | ✓ |
| TSV.ZIP | — | ✓ |
| ZIP (any supported format inside) | ✓ | — |
| BZ2 (any supported format inside) | ✓ | — |
| ZST (any supported format inside) | ✓ | — |
| Excel (.xlsx) | ✓ | ✓ |
| Excel (.xls, legacy) | ✓ | — |
| ODS | ✓ | ✓ |
| JSON | ✓ | ✓ |
| JSON.BZ2 (bzip2) | — | ✓ |
| JSON.ZST (zstd) | — | ✓ |
| JSON.ZIP | — | ✓ |
| JSON Lines | ✓ | ✓ |
| JSON Lines GZ (gzip) | — | ✓ |
| JSON Lines BZ2 (bzip2) | — | ✓ |
| JSON Lines ZST (zstd) | — | ✓ |
| JSON Lines ZIP | — | ✓ |
| GeoJSON | ✓ | ✓ |
| GeoJSON.GZ (gzip) | — | ✓ |
| GeoJSON.BZ2 (bzip2) | — | ✓ |
| GeoJSON.ZST (zstd) | — | ✓ |
| Parquet | ✓ | ✓ |
| Feather | ✓ | ✓ |
| Arrow | ✓ | ✓ |
| ORC | ✓ | ✓ |
| Avro | ✓ | ✓ |
| SQLite | ✓ | ✓ |

---

## Example prompts

Once the server is connected, you can use natural language:

```
Inspect ~/data/sales.csv and tell me about the schema.

Convert ~/data/sales.csv to Parquet.

Convert ~/data/report.xlsx, sheet "Q3", to CSV, selecting only the
"date", "region", and "revenue" columns.

Merge orders.csv and customers.csv on customer_id using a left join,
output as Parquet.

Append all the CSV files in ~/data/monthly/ into one file and save it
as ~/data/all_months.parquet.

Query ~/data/events.parquet: give me total revenue by region for 2025,
sorted descending, as a JSON file.

I have ~/data/legacy.csv from an old Windows system — fix the encoding
and convert it to Excel.
```

---

## Output paths

If you don't specify `output_path`, the server picks a sensible default in the same directory as the input:

| Tool | Default output |
|---|---|
| `convert_file` | `{input_stem}.{target_format}` |
| `merge_files` | `{file1_stem}_{operation}_{file2_stem}.{target_format}` |
| `append_files` | `appended.{target_format}` |
| `query_file` | `{input_stem}_query.{target_format}` |

---

## Free tier

`inspect_file` requires no API key. All other tools work without a key but output is truncated to 50 rows. The tool will tell you when truncation occurs. A Monthly plan at [reparatio.app](https://reparatio.app) removes all row limits.

---

## Privacy

Your files are sent to the Reparatio API at `reparatio.app` for processing. Files are handled in memory and never stored — see the [Privacy Policy](https://reparatio.app). If you need to keep data fully local, this tool is not the right fit.

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `REPARATIO_API_KEY` | — | Your `rp_...` API key |

---

## Troubleshooting

**"REPARATIO_API_KEY is not set"**
The key is missing from the `env` block in your client config. Check spelling — it must be exactly `REPARATIO_API_KEY`.

**"uvx: command not found"**
Install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`, then restart your terminal and your AI client.

**"Insufficient plan"**
The tool you called requires a Monthly plan key. `inspect_file` is always free.

**"File not found"**
Use an absolute path (starting with `/` or `~`). Relative paths are resolved from the server process's working directory, which may not be what you expect.

**"Parse failure"**
The file could not be read in the detected format. Try setting `fix_encoding: true`, specifying a `delimiter`, or confirming the file extension matches the actual format.

**Tools not appearing in the client**
Restart the client after editing the config. Check that `uvx` is on the PATH visible to the client process — on macOS/Linux, confirm with `which uvx`.
