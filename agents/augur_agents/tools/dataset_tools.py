"""Dataset inspection and curation for the Data Agent (stub).

Stands in for a ``dataset-mcp``. The catalogue is a small allow-list of real,
public text datasets with plausible metadata; the point is not the numbers but
the *shape* of the flow:

    inspect -> validate -> (approval) -> materialize -> manifest

``materialize_dataset`` is the only mutating tool here. It writes data somewhere
durable and costs bandwidth and storage, so it goes through
``governance_tools.check_policy`` with an approval token bound to the exact
source and revision. Everything else is read-only and needs no approval.

The manifest a run trains against is immutable and checksummed, because
"which data was this model trained on" must have an answer that survives the
session that produced it.
"""

from __future__ import annotations

import hashlib
from typing import Any

from augur_agents.contracts import DatasetManifest, DatasetSplit
from augur_agents.tools import governance_tools

## =============================================================================
# Allow-listed catalogue
#
# Only public datasets with a clear licence. An unknown source is refused rather
# than guessed at: inventing a row count would silently corrupt every downstream
# estimate.
## =============================================================================

_CATALOGUE: dict[str, dict[str, Any]] = {
    "wikitext-2-raw-v1": {
        "source": "wikitext",
        "revision": "wikitext-2-raw-v1",
        "license": "cc-by-sa-3.0",
        "description": "Verified Good and Featured Wikipedia articles, raw text.",
        "text_column": "text",
        "splits": [
            {"name": "train", "num_rows": 36_718, "num_tokens": 2_391_884},
            {"name": "validation", "num_rows": 3_760, "num_tokens": 247_289},
            {"name": "test", "num_rows": 4_358, "num_tokens": 283_287},
        ],
    },
    "wikitext-103-raw-v1": {
        "source": "wikitext",
        "revision": "wikitext-103-raw-v1",
        "license": "cc-by-sa-3.0",
        "description": "The larger WikiText corpus, ~103M tokens of raw text.",
        "text_column": "text",
        "splits": [
            {"name": "train", "num_rows": 1_801_350, "num_tokens": 103_227_021},
            {"name": "validation", "num_rows": 3_760, "num_tokens": 217_646},
            {"name": "test", "num_rows": 4_358, "num_tokens": 245_569},
        ],
    },
    "tiny_shakespeare": {
        "source": "tiny_shakespeare",
        "revision": "default",
        "license": "public-domain",
        "description": "The complete works of Shakespeare as one character stream. "
                       "Small enough for a smoke test.",
        "text_column": "text",
        "splits": [
            {"name": "train", "num_rows": 1, "num_tokens": 301_966},
            {"name": "validation", "num_rows": 1, "num_tokens": 16_998},
        ],
    },
    "ag_news": {
        "source": "ag_news",
        "revision": "default",
        "license": "custom-non-commercial",
        "description": "News headlines and bodies in four topic classes.",
        "text_column": "text",
        "splits": [
            {"name": "train", "num_rows": 120_000, "num_tokens": 5_400_000},
            {"name": "test", "num_rows": 7_600, "num_tokens": 342_000},
        ],
    },
}

# Datasets whose licence forbids commercial use or redistribution. Surfaced as a
# validation finding rather than a hard block - it is a decision for a human.
_RESTRICTED_LICENSES = {"custom-non-commercial"}

# Benchmark corpora that must never end up in a training set. A model trained on
# its own evaluation data produces meaningless numbers, and by the time that is
# discovered the compute is already spent.
_BENCHMARK_SOURCES = {"hellaswag", "mmlu", "truthfulqa", "gsm8k", "humaneval", "arc"}

_STUB_NOTE = "Stub catalogue - metadata is representative, nothing is downloaded."


def _checksum(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


def _resolve(source: str, revision: str | None) -> tuple[str, dict[str, Any]] | None:
    """Find a catalogue entry by revision key or by source name."""
    key = (revision or source or "").strip()
    if key in _CATALOGUE:
        return key, _CATALOGUE[key]
    for cat_key, entry in _CATALOGUE.items():
        if entry["source"] == source and (not revision or entry["revision"] == revision):
            return cat_key, entry
    return None


def inspect_dataset(source: str, revision: str | None = None) -> dict[str, Any]:
    """Read-only metadata for an allow-listed dataset.

    Returns splits, row and token counts, licence, and a checksum. An unknown
    source fails rather than guessing.
    """
    hit = _resolve(source, revision)
    if hit is None:
        return {
            "success": False,
            "error": (
                f"{source!r} is not in the allow-list. Available: "
                f"{', '.join(sorted(_CATALOGUE))}."
            ),
        }
    key, entry = hit
    total_tokens = sum(s["num_tokens"] for s in entry["splits"])
    return {
        "success": True,
        "source": entry["source"],
        "revision": entry["revision"],
        "license": entry["license"],
        "description": entry["description"],
        "text_column": entry["text_column"],
        "splits": entry["splits"],
        "total_rows": sum(s["num_rows"] for s in entry["splits"]),
        "total_tokens": total_tokens,
        "checksum": _checksum(key, entry["revision"]),
        "note": _STUB_NOTE,
    }


def validate_dataset(
    source: str, revision: str | None = None, task_type: str = "llm"
) -> dict[str, Any]:
    """Check a dataset is usable and safe for the intended task.

    Covers the three things that actually go wrong: the schema does not match
    the task, the licence does not permit the use, or the data is a benchmark
    that would contaminate evaluation.
    """
    meta = inspect_dataset(source, revision)
    if not meta["success"]:
        return {"success": True, "passed": False, "findings": [meta["error"]]}

    findings: list[str] = []
    passed = True

    if task_type not in {"llm", "seq2seq", "encoder"}:
        findings.append(f"Unknown task_type {task_type!r}; expected llm/seq2seq/encoder.")
        passed = False

    if meta["text_column"] != "text":
        findings.append(
            f"Text lives in {meta['text_column']!r}, not 'text' - the loader "
            f"needs an explicit column mapping."
        )

    if meta["license"] in _RESTRICTED_LICENSES:
        findings.append(
            f"Licence {meta['license']!r} restricts commercial use or "
            f"redistribution. A human should confirm this use is permitted."
        )
        passed = False

    if meta["source"].lower() in _BENCHMARK_SOURCES:
        findings.append(
            f"{meta['source']!r} is an evaluation benchmark. Training on it "
            f"contaminates evaluation and invalidates the resulting scores."
        )
        passed = False

    if not any(s["name"] == "validation" for s in meta["splits"]):
        findings.append(
            "No validation split; one will have to be held out from train."
        )

    small = meta["total_tokens"] < 1_000_000
    if small:
        findings.append(
            f"Only {meta['total_tokens']:,} tokens - fine for a smoke test, far "
            f"below compute-optimal for real training (~20 tokens/parameter)."
        )

    return {
        "success": True,
        "passed": passed,
        "source": meta["source"],
        "revision": meta["revision"],
        "findings": findings or ["No problems found."],
        "note": _STUB_NOTE,
    }


def materialize_dataset(
    source: str,
    revision: str | None = None,
    approval_token: str | None = None,
) -> dict[str, Any]:
    """Download and store a dataset. **Mutating - requires approval.**

    Costs bandwidth, storage and time, so it is gated on an approval token bound
    to this exact source and revision.
    """
    meta = inspect_dataset(source, revision)
    if not meta["success"]:
        return meta

    params = {"source": meta["source"], "revision": meta["revision"]}
    decision = governance_tools.check_policy(
        "materialize_dataset", params, approval_token
    )
    if not decision["allowed"]:
        return {
            "success": False,
            "error": decision["reason"],
            "needs_approval": True,
            "action": "materialize_dataset",
            "params": params,
        }

    digest = _checksum(meta["source"], meta["revision"], "materialized")
    uri = f"s3://augur-dev/datasets/{meta['source']}/{meta['revision']}/{digest[:12]}/"
    governance_tools.record_audit(
        "dataset_materialized", source=meta["source"],
        revision=meta["revision"], uri=uri,
    )
    return {
        "success": True,
        "storage_uri": uri,
        "source": meta["source"],
        "revision": meta["revision"],
        "checksum": digest,
        "bytes": meta["total_tokens"] * 4,
        "note": "Stub - no bytes were transferred. " + _STUB_NOTE,
    }


def build_manifest(
    source: str,
    revision: str | None = None,
    storage_uri: str | None = None,
    transforms: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble the immutable ``DatasetManifest`` a training run references."""
    meta = inspect_dataset(source, revision)
    if not meta["success"]:
        return meta

    manifest = DatasetManifest(
        source=meta["source"],
        revision=meta["revision"],
        license=meta["license"],
        splits=[
            DatasetSplit(
                name=s["name"], num_rows=s["num_rows"], num_tokens=s["num_tokens"]
            )
            for s in meta["splits"]
        ],
        checksum=meta["checksum"],
        storage_uri=storage_uri
        or f"s3://augur-dev/datasets/{meta['source']}/{meta['revision']}/",
        transforms=transforms or [],
        text_column=meta["text_column"],
        provenance={"produced_by": "data_agent", "tool": "build_manifest"},
    )
    return {
        "success": True,
        "manifest": manifest.model_dump(mode="json"),
        "dataset_ref": manifest.id,
        "total_tokens": meta["total_tokens"],
        "note": _STUB_NOTE,
    }


def list_datasets() -> dict[str, Any]:
    """Everything in the allow-list."""
    return {
        "success": True,
        "datasets": [
            {
                "key": key,
                "source": e["source"],
                "revision": e["revision"],
                "license": e["license"],
                "description": e["description"],
                "total_tokens": sum(s["num_tokens"] for s in e["splits"]),
            }
            for key, e in _CATALOGUE.items()
        ],
    }


DATASET_TOOLS = [
    list_datasets,
    inspect_dataset,
    validate_dataset,
    materialize_dataset,
    build_manifest,
]

__all__ = [
    "list_datasets",
    "inspect_dataset",
    "validate_dataset",
    "materialize_dataset",
    "build_manifest",
    "DATASET_TOOLS",
]

