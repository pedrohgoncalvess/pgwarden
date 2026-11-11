"""Release gates must reject manifest drift and tags for another version."""

from pathlib import Path
import runpy
import shutil

import pytest


ROOT = Path(__file__).resolve().parents[2]
check_versions = runpy.run_path(str(ROOT / "scripts/check_version.py"))["check_versions"]
release_version = runpy.run_path(str(ROOT / "scripts/check_version.py"))["release_version"]


@pytest.fixture
def release_tree(tmp_path):
    paths = [
        "pyproject.toml", "uv.lock", "api/uv.lock", "collector/uv.lock",
        "migrations/uv.lock", "frontend/package.json", "frontend/package-lock.json",
        *[f"{service}/pyproject.toml" for service in
          ("api", "analytics", "collector", "migrations", "notifier")],
    ]
    for path in paths:
        destination = tmp_path / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, destination)
    return tmp_path


def test_matching_release(release_tree):
    version = check_versions(root=release_tree)
    assert check_versions(f"v{version}", root=release_tree) == version


@pytest.mark.parametrize("python_version,tag_version", [
    ("0.2.0a1", "0.2.0-alpha.1"),
    ("0.2.0b2", "0.2.0-beta.2"),
    ("0.2.0rc3", "0.2.0-rc.3"),
])
def test_python_prereleases_match_semver_tags(python_version, tag_version):
    assert release_version(python_version) == release_version(tag_version)


@pytest.mark.parametrize("tag", ["v99.0.0", "0.1.0", "v0.1.0-rc.1", "v0.1.0-extra"])
def test_rejects_unmatched_tag(release_tree, tag):
    with pytest.raises(ValueError):
        check_versions(tag, root=release_tree)


@pytest.mark.parametrize("path", [
    "collector/pyproject.toml", "collector/uv.lock",
    "frontend/package.json", "frontend/package-lock.json",
])
def test_rejects_manifest_and_lockfile_drift(release_tree, path):
    manifest = release_tree / path
    version = check_versions(root=release_tree)
    manifest.write_text(manifest.read_text().replace(f'"{version}"', '"99.0.0"'))
    with pytest.raises(ValueError, match="mismatches"):
        check_versions(root=release_tree)
