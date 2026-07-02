"""Fetch-layer behavior that does not require network access."""

from __future__ import annotations

from pathlib import Path

import pytest

from uad36.errors import SchemaNotAvailableError
from uad36.fetch import (
    SAMPLES_URL,
    SCHEMA_URL,
    default_artifacts_dir,
    find_schema_xsd,
    iter_sample_xml,
    require_schema_xsd,
)


def test_official_urls_are_gse_hosted() -> None:
    assert SCHEMA_URL.startswith("https://sf.freddiemac.com/")
    assert SAMPLES_URL.startswith("https://sf.freddiemac.com/")


def test_artifacts_dir_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("UAD36_ARTIFACTS_DIR", str(tmp_path))
    assert default_artifacts_dir() == tmp_path


def test_find_schema_ignores_helper_xsds(tmp_path: Path) -> None:
    combined = tmp_path / "GSE_UAD_3.6.0_v1.3" / "Combined"
    combined.mkdir(parents=True)
    (combined / "GSE_UAD_3.6.0_xlink_v1.3.xsd").write_text("<xs/>")
    (combined / "xml.xsd").write_text("<xs/>")
    (combined / "GSE_UAD_3.6.0_v1.3.xsd").write_text("<xs/>")
    found = find_schema_xsd(tmp_path)
    assert found is not None and found.name == "GSE_UAD_3.6.0_v1.3.xsd"


def test_missing_schema_message_is_actionable(tmp_path: Path) -> None:
    with pytest.raises(SchemaNotAvailableError, match="fetch-schemas"):
        require_schema_xsd(tmp_path)


def test_iter_sample_xml_empty_when_absent(tmp_path: Path) -> None:
    assert iter_sample_xml(tmp_path) == []


def test_no_schema_files_in_repo() -> None:
    """The legal invariant: this repository must never contain schema files.

    MISMO's license forbids redistributing its schemas (and the GSE
    subschema is MISMO-derived); code-only is the deal. Guard against a
    future contributor 'helpfully' vendoring them.
    """
    repo_root = Path(__file__).resolve().parents[1]
    offenders = [
        p
        for p in repo_root.rglob("*.xsd")
        if ".venv" not in p.parts and not p.parts[len(repo_root.parts)] == ".git"
    ]
    offenders += [
        p
        for p in repo_root.rglob("*_Appraisal_*.xml")
        if ".venv" not in p.parts
    ]
    assert offenders == [], f"schema/sample files must not be committed: {offenders}"
