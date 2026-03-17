"""Unit tests for reparatio_mcp.server helper functions.

These tests cover all pure / side-effect-free functions and the error-handling
helpers using mock httpx responses.  The MCP tool handlers themselves require
a live server and are covered by integration tests.
"""
from __future__ import annotations

import json
import pytest
import httpx
from pathlib import Path
from unittest.mock import patch

from reparatio_mcp.server import (
    _fmt_size,
    _default_output,
    _raise_api_error,
    _truncation_warning,
    _read_file,
    _write_file,
    _headers,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _resp(status: int, *, json_data: dict | None = None, headers: dict | None = None) -> httpx.Response:
    h = dict(headers or {})
    content = json.dumps(json_data).encode() if json_data is not None else b""
    if json_data is not None:
        h.setdefault("content-type", "application/json")
    return httpx.Response(status, content=content, headers=h)


# ── _fmt_size ─────────────────────────────────────────────────────────────────

class TestFmtSize:
    def test_bytes(self):
        assert _fmt_size(512) == "512.0 B"

    def test_kilobytes(self):
        assert _fmt_size(2048) == "2.0 KB"

    def test_megabytes(self):
        assert _fmt_size(3 * 1024 * 1024) == "3.0 MB"

    def test_gigabytes(self):
        assert _fmt_size(2 * 1024 ** 3) == "2.0 GB"

    def test_boundary_exactly_1kb(self):
        assert _fmt_size(1024) == "1.0 KB"

    def test_zero(self):
        assert _fmt_size(0) == "0.0 B"


# ── _default_output ───────────────────────────────────────────────────────────

class TestDefaultOutput:
    def test_basic_extension_change(self):
        result = _default_output("/data/sales.csv", "parquet")
        assert result == "/data/sales.parquet"

    def test_strips_gz_suffix(self):
        result = _default_output("/data/sales.csv.gz", "parquet")
        assert result == "/data/sales.parquet"

    def test_adds_suffix(self):
        result = _default_output("/data/events.csv", "csv", "_query")
        assert result == "/data/events_query.csv"

    def test_preserves_directory(self):
        result = _default_output("/some/deep/path/file.xlsx", "json")
        assert result.startswith("/some/deep/path/")

    def test_non_gz_extension_kept(self):
        # .bz2 is not stripped (only .gz is)
        result = _default_output("/data/file.csv.bz2", "parquet")
        assert result == "/data/file.csv.parquet"


# ── _raise_api_error ──────────────────────────────────────────────────────────

class TestRaiseApiError:
    def test_401_no_key_message(self):
        with pytest.raises(RuntimeError, match="No API key"):
            _raise_api_error(_resp(401))

    def test_403_insufficient_plan(self):
        with pytest.raises(RuntimeError, match="Professional plan"):
            _raise_api_error(_resp(403))

    def test_413_file_too_large(self):
        with pytest.raises(RuntimeError, match="too large"):
            _raise_api_error(_resp(413))

    def test_422_uses_detail_field(self):
        with pytest.raises(RuntimeError, match="Parse failure: bad delimiter"):
            _raise_api_error(_resp(422, json_data={"detail": "bad delimiter"}))

    def test_500_generic_message(self):
        with pytest.raises(RuntimeError, match="API error 500"):
            _raise_api_error(_resp(500, json_data={"detail": "internal error"}))

    def test_non_json_body_falls_back(self):
        r = httpx.Response(500, content=b"plain text error")
        with pytest.raises(RuntimeError, match="API error 500"):
            _raise_api_error(r)


# ── _truncation_warning ───────────────────────────────────────────────────────

class TestTruncationWarning:
    def test_returns_none_when_header_absent(self):
        assert _truncation_warning(_resp(200)) is None

    def test_returns_none_when_header_false(self):
        r = _resp(200, headers={"x-reparatio-truncated": "false"})
        assert _truncation_warning(r) is None

    def test_returns_warning_when_truncated(self):
        r = _resp(200, headers={"x-reparatio-truncated": "true", "x-reparatio-row-limit": "50"})
        warning = _truncation_warning(r)
        assert warning is not None
        assert "50" in warning
        assert "truncated" in warning.lower() or "⚠" in warning

    def test_uses_default_limit_when_header_missing(self):
        r = _resp(200, headers={"x-reparatio-truncated": "true"})
        warning = _truncation_warning(r)
        assert warning is not None
        assert "50" in warning


# ── _read_file / _write_file ──────────────────────────────────────────────────

class TestReadWriteFile:
    def test_read_returns_bytes_and_name(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_bytes(b"id,name\n1,Alice\n")
        content, name = _read_file(str(f))
        assert content == b"id,name\n1,Alice\n"
        assert name == "data.csv"

    def test_read_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            _read_file(str(tmp_path / "nonexistent.csv"))

    def test_write_creates_file(self, tmp_path):
        out = tmp_path / "out.parquet"
        _write_file(str(out), b"PAR1")
        assert out.read_bytes() == b"PAR1"

    def test_read_expands_tilde(self, tmp_path, monkeypatch):
        # Verify ~ expansion doesn't crash (even if path doesn't exist)
        with pytest.raises(FileNotFoundError):
            _read_file("~/definitely_not_a_real_file_xyz_12345.csv")


# ── _headers ──────────────────────────────────────────────────────────────────

class TestHeaders:
    def test_includes_key_when_set(self, monkeypatch):
        import reparatio_mcp.server as srv
        monkeypatch.setattr(srv, "API_KEY", "rp_test123")
        assert srv._headers() == {"X-API-Key": "rp_test123"}

    def test_empty_dict_when_no_key(self, monkeypatch):
        import reparatio_mcp.server as srv
        monkeypatch.setattr(srv, "API_KEY", "")
        assert srv._headers() == {}
