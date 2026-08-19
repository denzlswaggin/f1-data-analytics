#!/usr/bin/env python
"""Fail if any dbt model or source lacks a description.

A lightweight docs-coverage gate: run it after ``dbt docs generate`` so the
lineage catalog we publish is fully described. Seeds (including the CI fixtures)
are exempt — they are test data, not modelled assets.

Usage::

    python scripts/check_dbt_docs_coverage.py [path/to/manifest.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_MANIFEST = Path("warehouse/dbt/target/manifest.json")


def undocumented(manifest: dict[str, Any]) -> list[str]:
    """Return ``model:<name>`` / ``source:<src>.<name>`` for nodes missing a description."""
    missing: list[str] = []
    for node in manifest.get("nodes", {}).values():
        if node.get("resource_type") != "model":
            continue
        if not (node.get("description") or "").strip():
            missing.append(f"model:{node['name']}")
    for src in manifest.get("sources", {}).values():
        if not (src.get("description") or "").strip():
            missing.append(f"source:{src['source_name']}.{src['name']}")
    return sorted(missing)


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_MANIFEST
    manifest = json.loads(path.read_text())
    n_models = sum(
        1 for n in manifest.get("nodes", {}).values() if n.get("resource_type") == "model"
    )
    n_sources = len(manifest.get("sources", {}))
    missing = undocumented(manifest)
    if missing:
        print(f"Undocumented dbt nodes ({len(missing)}) — add a description: block:")
        for item in missing:
            print(f"  - {item}")
        return 1
    print(f"dbt docs coverage OK: {n_models} models + {n_sources} sources all described.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
