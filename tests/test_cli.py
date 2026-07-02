"""CLI surface."""

from __future__ import annotations

from pathlib import Path

import pytest

from uad36.cli import main


def test_inspect_xml(sf2_xml: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["inspect", str(sf2_xml)]) == 0
    out = capsys.readouterr().out
    assert "rooms (15)" in out
    assert "GLA (standard above-grade finished): 3308 sqft" in out
    assert "comparables: 5" in out


def test_inspect_zip(sf2_package: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["inspect", str(sf2_package)]) == 0
    out = capsys.readouterr().out
    assert "UCDP package:" in out
    assert "floor-plan exhibit(s): Images/SF2_Sketch.png" in out


def test_inspect_shows_analyzed_not_used(
    condo1_package: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["inspect", str(condo1_package)]) == 0
    out = capsys.readouterr().out
    assert "analyzed-not-used: 5" in out
    assert "not used:" in out


def test_validate_ok(sf2_xml: Path, schemas_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(sf2_xml)]) == 0
    assert "valid against the GSE UAD 3.6 subschema" in capsys.readouterr().out


def test_validate_zip_and_json(sf2_package: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", str(sf2_package), "--json"]) == 0
    assert '"valid": true' in capsys.readouterr().out


def test_validate_failure_exit_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.xml"
    bad.write_bytes(b"<MESSAGE><unclosed>")
    assert main(["validate", str(bad)]) == 1
    assert "not well-formed" in capsys.readouterr().out


def test_redact_cli(sf2_xml: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out_file = tmp_path / "redacted.xml"
    assert main(["redact", str(sf2_xml), str(out_file)]) == 0
    assert b"Betty" not in out_file.read_bytes()


def test_exhibits_cli(sf2_package: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["exhibits", str(sf2_package), str(tmp_path), "--floor-plans-only"]) == 0
    assert (tmp_path / "SF2_Sketch.png").exists()


def test_package_error_is_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bogus = tmp_path / "bogus.zip"
    bogus.write_bytes(b"nope")
    assert main(["inspect", str(bogus)]) == 2
    assert "error:" in capsys.readouterr().err
