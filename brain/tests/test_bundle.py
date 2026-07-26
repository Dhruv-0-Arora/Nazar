import shutil

import pytest

from brain.ingest.bundle import BundleError, validate_bundle
from conftest import BUNDLE_A


def test_fixture_bundle_validates():
    manifest = validate_bundle(BUNDLE_A)
    assert manifest.machine_id == "laptop-a"
    assert manifest.services == ("backend",)


def test_bad_name_rejected(tmp_path):
    bad = tmp_path / "bundle-laptop-a-fake"
    shutil.copytree(BUNDLE_A, bad)
    with pytest.raises(BundleError, match="naming contract"):
        validate_bundle(bad)


def test_missing_manifest_rejected(tmp_path):
    broken = tmp_path / BUNDLE_A.name
    shutil.copytree(BUNDLE_A, broken)
    (broken / "manifest.json").unlink()
    with pytest.raises(BundleError, match="manifest.json missing"):
        validate_bundle(broken)


def test_unsupported_contract_rejected(tmp_path):
    broken = tmp_path / BUNDLE_A.name
    shutil.copytree(BUNDLE_A, broken)
    manifest = (broken / "manifest.json").read_text().replace('"1.0"', '"2.0"')
    (broken / "manifest.json").write_text(manifest)
    with pytest.raises(BundleError, match="contract_version"):
        validate_bundle(broken)
