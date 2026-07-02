"""Test fixtures.

The suite runs against the GSE-published sample packages, which are NOT
committed to this repository (see the README licensing note). Fetch them
once before running::

    uv run uad36 fetch-schemas
    uv run uad36 fetch-samples

Tests that need an artifact skip with an instructive message when it is
missing. Set ``UAD36_ARTIFACTS_DIR`` to use a non-default location.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from uad36.fetch import (
    find_sample_package,
    find_sample_xml,
    find_schema_xsd,
    iter_sample_packages,
    iter_sample_xml,
    samples_dir,
    schemas_dir,
)


@pytest.fixture(scope="session")
def schemas_root() -> Path:
    root = schemas_dir()
    if find_schema_xsd(root) is None:
        pytest.skip("GSE subschema not fetched — run `uv run uad36 fetch-schemas` first")
    return root


@pytest.fixture(scope="session")
def samples_root() -> Path:
    root = samples_dir()
    if not iter_sample_xml(root):
        pytest.skip("GSE samples not fetched — run `uv run uad36 fetch-samples` first")
    return root


def _sample_xml(samples_root: Path, prefix: str) -> Path:
    path = find_sample_xml(prefix, samples_root)
    if path is None:
        pytest.skip(f"sample {prefix} not present under {samples_root}")
    return path


def _sample_package(samples_root: Path, scenario: str) -> Path:
    path = find_sample_package(scenario, samples_root)
    if path is None:
        pytest.skip(f"sample package {scenario} not present under {samples_root}")
    return path


@pytest.fixture(scope="session")
def sf2_xml(samples_root: Path) -> Path:
    return _sample_xml(samples_root, "SF2")


@pytest.fixture(scope="session")
def condo1_xml(samples_root: Path) -> Path:
    return _sample_xml(samples_root, "Condo1")


@pytest.fixture(scope="session")
def sf2_package(samples_root: Path) -> Path:
    return _sample_package(samples_root, "SF2")


@pytest.fixture(scope="session")
def condo1_package(samples_root: Path) -> Path:
    return _sample_package(samples_root, "Condo1")


@pytest.fixture(scope="session")
def all_sample_xml(samples_root: Path) -> list[Path]:
    return iter_sample_xml(samples_root)


@pytest.fixture(scope="session")
def all_sample_packages(samples_root: Path) -> list[Path]:
    return iter_sample_packages(samples_root)
