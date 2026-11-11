"""Check release versions without installing project dependencies."""

import argparse
import json
from pathlib import Path
import re
import tomllib


ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-(?:alpha|beta|rc)\.(0|[1-9][0-9]*))?")


def release_version(value: str) -> str:
    """Map Python's normalized prereleases to the existing release tag format."""
    match = re.fullmatch(r"(\d+\.\d+\.\d+)(a|b|rc)(\d+)", value)
    if match:
        base, phase, number = match.groups()
        phase = {"a": "alpha", "b": "beta", "rc": "rc"}[phase]
        value = f"{base}-{phase}.{number}"
    if not VERSION.fullmatch(value):
        raise ValueError(f"Invalid project version: {value}")
    return value


def check_versions(tag: str | None = None, root: Path = ROOT) -> str:
    expected = release_version(tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"])
    versions = {}
    for service in ("api", "analytics", "collector", "migrations", "notifier"):
        manifest = tomllib.loads((root / service / "pyproject.toml").read_text())
        versions[f"{service}/pyproject.toml"] = manifest["project"]["version"]
    for filename in ("uv.lock", "api/uv.lock", "collector/uv.lock", "migrations/uv.lock"):
        lock = tomllib.loads((root / filename).read_text())
        for package in lock["package"]:
            source = package.get("source", {})
            if "virtual" in source or "editable" in source:
                versions[f"{filename}:{package['name']}"] = package["version"]
    package = json.loads((root / "frontend/package.json").read_text())
    lock = json.loads((root / "frontend/package-lock.json").read_text())
    versions["frontend/package.json"] = package["version"]
    versions["frontend/package-lock.json"] = lock["version"]
    versions["frontend/package-lock.json:root"] = lock["packages"][""]["version"]
    if tag is not None:
        versions["release tag"] = tag.removeprefix("v") if tag.startswith("v") else tag
        if not tag.startswith("v"):
            raise ValueError("Release tag must start with v")
    mismatches = [f"{name}: {version}" for name, version in versions.items() if release_version(version) != expected]
    if mismatches:
        raise ValueError(f"Expected version {expected}; mismatches: " + ", ".join(mismatches))
    return expected


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Require a matching vMAJOR.MINOR.PATCH release tag")
    args = parser.parse_args()
    try:
        version = check_versions(args.tag)
    except (ValueError, KeyError) as error:
        parser.exit(1, f"{error}\n")
    print(f"Release versions match: {version}")
