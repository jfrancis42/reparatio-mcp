#!/usr/bin/env python3
"""
reparatio-mcp — MCP server wrapping the Reparatio REST API.

Configuration (environment variables):
    REPARATIO_API_KEY   rp_... key from your Reparatio account (required for
                        convert / merge / append / query)
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# ── Configuration ─────────────────────────────────────────────────────────────

BASE_URL = "https://reparatio.app"
API_KEY  = os.getenv("REPARATIO_API_KEY", "")

server = Server("reparatio")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _headers() -> dict:
    return {"X-API-Key": API_KEY} if API_KEY else {}


def _read_file(path: str) -> tuple[bytes, str]:
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return p.read_bytes(), p.name


def _write_file(path: str, data: bytes) -> None:
    Path(path).expanduser().resolve().write_bytes(data)


def _default_output(input_path: str, fmt: str, suffix: str = "") -> str:
    """Derive an output path from the input path, stripping .gz if present."""
    p    = Path(input_path)
    stem = p.stem
    if p.suffix.lower() == ".gz":
        stem = Path(stem).stem
    return str(p.parent / f"{stem}{suffix}.{fmt}")


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _raise_api_error(resp: httpx.Response) -> None:
    try:
        detail = resp.json().get("detail", resp.text)
    except Exception:
        detail = resp.text or resp.reason_phrase
    messages = {
        401: "No API key set. Add REPARATIO_API_KEY to your environment.",
        403: "Insufficient plan. A Monthly plan is required for this operation.",
        413: "File too large (max 1 GB).",
        422: f"Parse failure: {detail}",
    }
    raise RuntimeError(messages.get(resp.status_code, f"API error {resp.status_code}: {detail}"))


def _truncation_warning(resp: httpx.Response) -> str | None:
    if resp.headers.get("x-reparatio-truncated") == "true":
        limit = resp.headers.get("x-reparatio-row-limit", "50")
        return (
            f"⚠ Output truncated to {limit} rows (free tier). "
            "A paid plan at reparatio.app is required for full-file output."
        )
    return None


# ── Tool definitions ──────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="inspect_file",
            description=(
                "Inspect a local file: detect encoding, count rows, list columns with "
                "data types, null counts, and unique counts, and return a preview. "
                "Supports CSV, TSV, Excel (.xlsx/.xls), ODS, JSON, JSONL, GeoJSON, "
                "Parquet, Feather, Arrow, ORC, Avro, SQLite, and gzip-compressed variants. "
                "No API key required."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path":         {"type": "string",  "description": "Local file path"},
                    "no_header":    {"type": "boolean", "default": False, "description": "Treat first row as data (CSV/TSV)"},
                    "fix_encoding": {"type": "boolean", "default": True,  "description": "Auto-detect and repair encoding"},
                    "delimiter":    {"type": "string",  "default": "",    "description": "Custom delimiter for CSV-like files (auto-detected if blank)"},
                    "sheet":        {"type": "string",  "default": "",    "description": "Sheet or table name for Excel, ODS, SQLite (first used if blank)"},
                    "preview_rows": {"type": "integer", "default": 8,     "description": "Preview rows to return (1–100)"},
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="convert_file",
            description=(
                "Convert a local file from any supported input format to any supported "
                "output format. Optionally select or rename columns, deduplicate rows, "
                "or sample a subset. Saves the result to disk and returns the output path. "
                "Requires a Monthly plan API key."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "input_path":     {"type": "string", "description": "Local path to the source file"},
                    "target_format":  {"type": "string", "description": "Output format: csv, tsv, csv.gz, csv.bz2, csv.zst, csv.zip, tsv.gz, tsv.bz2, tsv.zst, tsv.zip, xlsx, ods, json, json.bz2, json.zst, json.zip, jsonl, jsonl.gz, jsonl.bz2, jsonl.zst, jsonl.zip, geojson, geojson.gz, geojson.bz2, geojson.zst, parquet, feather, arrow, orc, avro, sqlite"},
                    "output_path":    {"type": "string", "description": "Output file path (default: same directory as input, extension changed)"},
                    "no_header":      {"type": "boolean", "default": False},
                    "fix_encoding":   {"type": "boolean", "default": True},
                    "delimiter":      {"type": "string",  "default": "", "description": "Custom delimiter for CSV-like input"},
                    "sheet":          {"type": "string",  "default": "", "description": "Sheet or table to read"},
                    "columns":        {"type": "array",   "items": {"type": "string"}, "description": "Rename columns — new names in order (must match column count)"},
                    "select_columns": {"type": "array",   "items": {"type": "string"}, "description": "Columns to include in output (all if omitted)"},
                    "deduplicate":    {"type": "boolean", "default": False, "description": "Remove duplicate rows"},
                    "sample_n":       {"type": "integer", "description": "Output a random sample of N rows"},
                    "sample_frac":    {"type": "number",  "description": "Output a random fraction, e.g. 0.1 for 10%"},
                    "geometry_column":{"type": "string",  "default": "geometry", "description": "WKT geometry column for GeoJSON output"},
                },
                "required": ["input_path", "target_format"],
            },
        ),
        Tool(
            name="merge_files",
            description=(
                "Merge two local files using a join operation or append (row-stacking). "
                "Saves the result to disk and returns the output path. "
                "Requires a Monthly plan API key."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file1_path":     {"type": "string", "description": "Local path to the first file"},
                    "file2_path":     {"type": "string", "description": "Local path to the second file"},
                    "operation":      {"type": "string", "enum": ["append", "left", "right", "outer", "inner"],
                                       "description": "append=stack rows; left/right/outer/inner=SQL-style join"},
                    "target_format":  {"type": "string", "description": "Output format"},
                    "output_path":    {"type": "string", "description": "Output file path (default: derived from input filenames)"},
                    "join_on":        {"type": "string", "description": "Comma-separated column name(s) to join on (required for all operations except append)"},
                    "no_header":      {"type": "boolean", "default": False},
                    "fix_encoding":   {"type": "boolean", "default": True},
                    "geometry_column":{"type": "string",  "default": "geometry"},
                },
                "required": ["file1_path", "file2_path", "operation", "target_format"],
            },
        ),
        Tool(
            name="append_files",
            description=(
                "Stack rows from two or more local files vertically. Columns missing from "
                "some files are filled with null. Saves the result to disk and returns the "
                "output path. Requires a Monthly plan API key."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "paths":         {"type": "array", "items": {"type": "string"}, "description": "List of local file paths to append (minimum 2)"},
                    "target_format": {"type": "string", "description": "Output format"},
                    "output_path":   {"type": "string", "description": "Output file path (default: appended.{format} in directory of first file)"},
                    "no_header":     {"type": "boolean", "default": False},
                    "fix_encoding":  {"type": "boolean", "default": True},
                },
                "required": ["paths", "target_format"],
            },
        ),
        Tool(
            name="query_file",
            description=(
                "Run a SQL query against a local file. The file is loaded as a table named "
                "'data'. Supports SELECT, WHERE, GROUP BY, ORDER BY, LIMIT, aggregations, "
                "and most scalar functions. Saves the result to disk and returns the output path. "
                "Requires a Monthly plan API key."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path":          {"type": "string", "description": "Local path to the source file"},
                    "sql":           {"type": "string", "description": "SQL query (table name: data)"},
                    "target_format": {"type": "string", "default": "csv", "description": "Output format"},
                    "output_path":   {"type": "string", "description": "Output file path (default: {stem}_query.{format})"},
                    "no_header":     {"type": "boolean", "default": False},
                    "fix_encoding":  {"type": "boolean", "default": True},
                    "delimiter":     {"type": "string",  "default": ""},
                    "sheet":         {"type": "string",  "default": ""},
                },
                "required": ["path", "sql"],
            },
        ),
    ]


# ── Tool implementations ──────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    handlers = {
        "inspect_file": _inspect,
        "convert_file": _convert,
        "merge_files":  _merge,
        "append_files": _append,
        "query_file":   _query,
    }
    handler = handlers.get(name)
    if handler is None:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    try:
        return await handler(arguments)
    except FileNotFoundError as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]
    except RuntimeError as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]
    except Exception as exc:
        return [TextContent(type="text", text=f"Unexpected error: {exc}")]


async def _inspect(args: dict) -> list[TextContent]:
    content, filename = _read_file(args["path"])
    data = {
        "no_header":    str(args.get("no_header",    False)).lower(),
        "fix_encoding": str(args.get("fix_encoding", True)).lower(),
        "delimiter":    args.get("delimiter", ""),
        "sheet":        args.get("sheet", ""),
        "preview_rows": str(args.get("preview_rows", 8)),
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{BASE_URL}/api/v1/inspect",
            files={"file": (filename, content, "application/octet-stream")},
            data=data,
            headers=_headers(),
        )
    if not resp.is_success:
        _raise_api_error(resp)

    d = resp.json()
    lines = [
        f"File:     {d['filename']}",
        f"Encoding: {d.get('detected_encoding', 'unknown')}",
        f"Rows:     {d['rows_total']:,}",
    ]
    if d.get("sheets"):
        lines.append(f"Sheets/tables: {', '.join(d['sheets'])}")

    lines += ["", "Columns:"]
    name_w = max((len(c["name"]) for c in d["columns"]), default=4)
    type_w = max((len(c["dtype"]) for c in d["columns"]), default=5)
    for col in d["columns"]:
        lines.append(
            f"  {col['name']:<{name_w}}  {col['dtype']:<{type_w}}"
            f"  nulls={col['null_count']}  unique={col['unique_count']}"
        )

    if d.get("preview"):
        lines += ["", f"Preview ({len(d['preview'])} rows):"]
        hdrs = list(d["preview"][0].keys())
        lines.append("  " + " | ".join(hdrs))
        lines.append("  " + "-" * (sum(len(h) for h in hdrs) + 3 * (len(hdrs) - 1)))
        for row in d["preview"]:
            lines.append("  " + " | ".join(str(row.get(h, "")) for h in hdrs))

    return [TextContent(type="text", text="\n".join(lines))]


async def _convert(args: dict) -> list[TextContent]:
    content, filename = _read_file(args["input_path"])
    fmt      = args["target_format"]
    out_path = args.get("output_path") or _default_output(args["input_path"], fmt)

    data = {
        "target_format":   fmt,
        "no_header":       str(args.get("no_header",    False)).lower(),
        "fix_encoding":    str(args.get("fix_encoding", True)).lower(),
        "delimiter":       args.get("delimiter", ""),
        "sheet":           args.get("sheet", ""),
        "columns":         json.dumps(args.get("columns", [])),
        "select_columns":  json.dumps(args.get("select_columns", [])),
        "deduplicate":     str(args.get("deduplicate", False)).lower(),
        "deduplicate_on":  "[]",
        "geometry_column": args.get("geometry_column", "geometry"),
    }
    if args.get("sample_n"):    data["sample_n"]    = str(args["sample_n"])
    if args.get("sample_frac"): data["sample_frac"] = str(args["sample_frac"])

    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{BASE_URL}/api/v1/convert",
            files={"file": (filename, content, "application/octet-stream")},
            data=data,
            headers=_headers(),
        )
    if not resp.is_success:
        _raise_api_error(resp)

    _write_file(out_path, resp.content)
    lines = [
        "Converted successfully.",
        f"Output: {out_path}  ({_fmt_size(len(resp.content))})",
    ]
    warn = _truncation_warning(resp)
    if warn:
        lines.append(warn)
    return [TextContent(type="text", text="\n".join(lines))]


async def _merge(args: dict) -> list[TextContent]:
    content1, filename1 = _read_file(args["file1_path"])
    content2, filename2 = _read_file(args["file2_path"])
    fmt       = args["target_format"]
    operation = args["operation"]
    stem1     = Path(args["file1_path"]).stem
    stem2     = Path(args["file2_path"]).stem
    out_path  = args.get("output_path") or str(
        Path(args["file1_path"]).parent / f"{stem1}_{operation}_{stem2}.{fmt}"
    )

    data = {
        "operation":       operation,
        "join_on":         args.get("join_on", ""),
        "target_format":   fmt,
        "no_header":       str(args.get("no_header",    False)).lower(),
        "fix_encoding":    str(args.get("fix_encoding", True)).lower(),
        "geometry_column": args.get("geometry_column", "geometry"),
    }
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{BASE_URL}/api/v1/merge",
            files={
                "file1": (filename1, content1, "application/octet-stream"),
                "file2": (filename2, content2, "application/octet-stream"),
            },
            data=data,
            headers=_headers(),
        )
    if not resp.is_success:
        _raise_api_error(resp)

    _write_file(out_path, resp.content)
    lines = [
        "Merged successfully.",
        f"Output: {out_path}  ({_fmt_size(len(resp.content))})",
    ]
    if col_warn := resp.headers.get("x-reparatio-warning"):
        lines.append(f"⚠ {col_warn}")
    if trunc := _truncation_warning(resp):
        lines.append(trunc)
    return [TextContent(type="text", text="\n".join(lines))]


async def _append(args: dict) -> list[TextContent]:
    paths = args["paths"]
    if len(paths) < 2:
        return [TextContent(type="text", text="Error: at least 2 files are required for append.")]

    fmt      = args["target_format"]
    out_path = args.get("output_path") or str(
        Path(paths[0]).parent / f"appended.{fmt}"
    )

    files = []
    for p in paths:
        content, filename = _read_file(p)
        files.append(("files", (filename, content, "application/octet-stream")))

    data = {
        "target_format": fmt,
        "no_header":     str(args.get("no_header",    False)).lower(),
        "fix_encoding":  str(args.get("fix_encoding", True)).lower(),
    }
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{BASE_URL}/api/v1/append",
            files=files,
            data=data,
            headers=_headers(),
        )
    if not resp.is_success:
        _raise_api_error(resp)

    _write_file(out_path, resp.content)
    lines = [
        f"Appended {len(paths)} files successfully.",
        f"Output: {out_path}  ({_fmt_size(len(resp.content))})",
    ]
    if col_warn := resp.headers.get("x-reparatio-warning"):
        lines.append(f"⚠ {col_warn}")
    if trunc := _truncation_warning(resp):
        lines.append(trunc)
    return [TextContent(type="text", text="\n".join(lines))]


async def _query(args: dict) -> list[TextContent]:
    content, filename = _read_file(args["path"])
    fmt      = args.get("target_format", "csv")
    out_path = args.get("output_path") or _default_output(args["path"], fmt, "_query")

    data = {
        "sql":           args["sql"],
        "target_format": fmt,
        "no_header":     str(args.get("no_header",    False)).lower(),
        "fix_encoding":  str(args.get("fix_encoding", True)).lower(),
        "delimiter":     args.get("delimiter", ""),
        "sheet":         args.get("sheet", ""),
    }
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{BASE_URL}/api/v1/query",
            files={"file": (filename, content, "application/octet-stream")},
            data=data,
            headers=_headers(),
        )
    if not resp.is_success:
        _raise_api_error(resp)

    _write_file(out_path, resp.content)
    lines = [
        "Query executed successfully.",
        f"Output: {out_path}  ({_fmt_size(len(resp.content))})",
    ]
    if trunc := _truncation_warning(resp):
        lines.append(trunc)
    return [TextContent(type="text", text="\n".join(lines))]


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    if not API_KEY:
        print(
            "reparatio-mcp: REPARATIO_API_KEY is not set. "
            "inspect_file works without a key; all other tools require a Monthly plan key.",
            file=sys.stderr,
        )
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def cli() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    cli()
