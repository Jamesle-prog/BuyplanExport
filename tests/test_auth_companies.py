"""Tests for auth/companies.py file-corruption handling."""
from __future__ import annotations

import auth.companies as companies


def test_corrupted_companies_file_raises_clear_error(tmp_path, monkeypatch):
    """A corrupted companies.json must fail loudly with a message pointing at
    the file, not raise a bare JSONDecodeError."""
    companies_file = tmp_path / "companies.json"
    companies_file.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(companies, "_COMPANIES_FILE", str(companies_file))
    try:
        companies._load()
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "companies.json" in str(e)


def test_missing_companies_file_still_seeds_defaults(tmp_path, monkeypatch):
    companies_file = tmp_path / "companies.json"
    monkeypatch.setattr(companies, "_COMPANIES_FILE", str(companies_file))
    data = companies._load()
    assert companies.COMPANY_GIII in data
