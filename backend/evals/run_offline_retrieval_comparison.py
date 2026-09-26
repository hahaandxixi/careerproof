"""Offline production retrieval comparison on frozen, provisionally labeled cases."""

import argparse
import ast
import copy
import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from platform import python_version
from time import perf_counter
from uuid import NAMESPACE_URL, uuid5

from app.core.config import settings
from app.tools.code_analyzer import ProjectFileSnapshot
from app.tools.evidence_context import retrieve_context
from app.tools.hybrid_retrieval import VERSION as LEXICAL_VERSION
from app.tools.hybrid_retrieval import retrieve_requirement_candidates
from app.tools.matcher import FORMULA_VERSION, RequirementInput, match_candidate
from app.tools.semantic_retrieval import (
    MIN_SIMILARITY,
    MODEL_REVISION,
    MODEL_SHA256,
    VERSION,
    load_local_model,
    retrieve_semantic_candidates,
)


def load_corpus(path):
    raw = path.read_bytes()
    corpus = json.loads(raw)
    if not corpus.get("cases"):
        raise ValueError("Corpus must include at least one case")
    ids = set()
    for case in corpus["cases"]:
        if case["id"] in ids:
            raise ValueError("Duplicate case id")
        ids.add(case["id"])
        documents = {document["path"]: document["content"] for document in case["documents"]}
        if len(documents) != len(case["documents"]):
            raise ValueError("Duplicate document path")
        gold_keys = set()
        for gold in case["gold"]:
            key = (gold["path"], gold["lineStart"], gold["lineEnd"])
            if key in gold_keys:
                raise ValueError("Duplicate gold source")
            gold_keys.add(key)
            text = documents.get(gold["path"])
            if text is None or not 1 <= gold["lineStart"] <= gold["lineEnd"] <= len(
                text.splitlines()
            ):
                raise ValueError("Gold source is missing or outside source lines")
    return corpus, hashlib.sha256(raw).hexdigest()


def apply_annotations(corpus, digest, path):
    raw = path.read_bytes()
    review = json.loads(raw)
    if review.get("corpusHash") != digest:
        raise ValueError("Annotation corpus hash does not match")
    if not str(review.get("reviewer", "")).strip() or not review.get("reviewedAt"):
        raise ValueError("Reviewer and review date must be explicitly recorded")
    datetime.fromisoformat(review["reviewedAt"])
    reviewed = {item["id"]: item for item in review.get("cases", [])}
    if len(reviewed) != len(review.get("cases", [])) or set(reviewed) != {
        case["id"] for case in corpus["cases"]
    }:
        raise ValueError("Annotations must include every case exactly once")
    updated = copy.deepcopy(corpus)
    support_kinds = {
        "describes_behavior",
        "describes_partial_behavior",
        "self_claim_only",
        "dependency_only",
        "empty_implementation",
        "contradiction_to_check",
        "untrusted_instruction",
    }
    for case in updated["cases"]:
        label = reviewed[case["id"]]
        if (
            not isinstance(label.get("noRelevantSource"), bool)
            or not label.get("reason", "").strip()
        ):
            raise ValueError("Every case requires an explicit decision and reason")
        sources = label.get("relevantSources", [])
        if label["noRelevantSource"] != (not sources):
            raise ValueError("No-source decision contradicts selected sources")
        documents = {item["path"]: item["content"] for item in case["documents"]}
        source_keys = set()
        for source in sources:
            lines = documents.get(source.get("path"), "").splitlines()
            start, end = source.get("lineStart"), source.get("lineEnd")
            if (
                type(start) is not int
                or type(end) is not int
                or not 1 <= start <= end <= len(lines)
                or source.get("support") not in support_kinds
            ):
                raise ValueError("Invalid annotated source or support kind")
            key = (source["path"], start, end)
            if key in source_keys:
                raise ValueError("Duplicate annotated source")
            source_keys.add(key)
        case["gold"] = sources
        case["labelStatus"] = "review_provided_identity_not_verified"
    updated["annotationStatus"] = "review provided; format checked, reviewer identity not verified"
    return updated, {
        "hash": hashlib.sha256(raw).hexdigest(),
        "reviewer": review["reviewer"],
        "reviewedAt": review["reviewedAt"],
        "identityVerified": False,
    }


def contextualize(hits, files):
    file_map = {file.path: file for file in files}
    results = []
    seen = set()
    for hit in hits:
        file = file_map[hit.file_path]
        try:
            tree = ast.parse(file.content) if file.path.endswith(".py") else None
        except SyntaxError:
            tree = None
        source = retrieve_context(hit, file, tree)
        key = (source.file_path, source.line_start, source.line_end)
        if key in seen:
            continue
        seen.add(key)
        exact = source.snippet == "\n".join(
            file.content.splitlines()[source.line_start - 1 : source.line_end]
        )
        digest = hashlib.sha256(file.content.encode("utf-8")).hexdigest()
        results.append({**asdict(source), "sourceExact": exact and source.content_hash == digest})
    return results


def overlaps(hit, gold):
    return (
        hit["file_path"] == gold["path"]
        and hit["line_start"] <= gold["lineEnd"]
        and hit["line_end"] >= gold["lineStart"]
    )


def measure(hits, gold):
    if not gold:
        return {"targetCount": 0, "noTargetReturnedCandidate": bool(hits)}
    ranks = [
        next((rank for rank, hit in enumerate(hits, 1) if overlaps(hit, target)), None)
        for target in gold
    ]
    first = min((rank for rank in ranks if rank is not None), default=None)
    precision = sum(any(overlaps(hit, target) for target in gold) for hit in hits[:2])
    return {
        "targetCount": len(gold),
        "recallAt1": sum(rank is not None and rank <= 1 for rank in ranks) / len(gold),
        "recallAt2": sum(rank is not None and rank <= 2 for rank in ranks) / len(gold),
        "fullCoverageAt2": all(rank is not None and rank <= 2 for rank in ranks),
        "reciprocalRank": 1 / first if first else 0,
        "precisionAt2": precision / min(2, len(hits)) if hits else 0,
    }


def aggregate(rows):
    positives = [row["metrics"] for row in rows if row["metrics"]["targetCount"]]
    negatives = [row["metrics"] for row in rows if not row["metrics"]["targetCount"]]
    average = lambda field: (  # noqa: E731
        sum(float(item[field]) for item in positives) / len(positives) if positives else None
    )
    return {
        "caseCount": len(rows),
        "returnedCandidates": sum(len(row["hits"]) for row in rows),
        "positiveCases": len(positives),
        "noTargetCases": len(negatives),
        "targetUnits": sum(item["targetCount"] for item in positives),
        "microRecallAt2": (
            sum(item["recallAt2"] * item["targetCount"] for item in positives)
            / sum(item["targetCount"] for item in positives)
            if positives
            else None
        ),
        **{
            name: average(name)
            for name in (
                "recallAt1",
                "recallAt2",
                "fullCoverageAt2",
                "reciprocalRank",
                "precisionAt2",
            )
        },
        "noTargetCandidateRate": sum(n["noTargetReturnedCandidate"] for n in negatives)
        / len(negatives)
        if negatives
        else None,
        "sourceExact": all(hit["sourceExact"] for row in rows for hit in row["hits"]),
    }


def evaluate(corpus, model=None):
    records = []
    for case in corpus["cases"]:
        files = [ProjectFileSnapshot(d["path"], d["content"]) for d in case["documents"]]
        requirement = RequirementInput(
            uuid5(NAMESPACE_URL, case["id"]), case["query"], case["skill"], 5
        )
        semantic, elapsed = {}, {}
        engines = {}
        start = perf_counter()
        engines["lexical"] = retrieve_requirement_candidates(case["query"], case["skill"], files)
        elapsed["lexical"] = (perf_counter() - start) * 1000
        start = perf_counter()
        engines["detector_lexical"] = (
            match_candidate([requirement], [], files).items[0].evidence_list
        )
        elapsed["detector_lexical"] = (perf_counter() - start) * 1000
        if model is not None:
            start = perf_counter()
            semantic, _ = retrieve_semantic_candidates([requirement], files, model)
            semantic_time = (perf_counter() - start) * 1000
            engines["semantic_documents"] = semantic.get(requirement.id, [])
            elapsed["semantic_documents"] = semantic_time
            start = perf_counter()
            engines["detector_lexical_semantic"] = (
                match_candidate([requirement], [], files, semantic_candidates=semantic)
                .items[0]
                .evidence_list
            )
            elapsed["detector_lexical_semantic"] = semantic_time + (perf_counter() - start) * 1000
        for engine, hits in engines.items():
            contextual = contextualize(hits, files)
            records.append(
                {
                    "caseId": case["id"],
                    "family": case["family"],
                    "category": case["category"],
                    "engine": engine,
                    "semanticScope": case["semanticScope"],
                    "metrics": measure(contextual, case["gold"]),
                    "latencyMs": round(elapsed[engine], 3),
                    "hits": contextual,
                }
            )
    summaries = {}
    for engine in sorted({row["engine"] for row in records}):
        rows = [row for row in records if row["engine"] == engine]
        scoped = [row for row in rows if row["semanticScope"]]
        summaries[engine] = {
            "allCases": aggregate(rows),
            "documentScope": aggregate(scoped),
            "byCategory": {
                category: aggregate([row for row in rows if row["category"] == category])
                for category in sorted({row["category"] for row in rows})
            },
        }
    return records, summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus", type=Path, default=Path(__file__).with_name("retrieval-corpus-v1.json")
    )
    parser.add_argument(
        "--semantic", action="store_true", help="Use installed local model; never download"
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--review-output", type=Path)
    parser.add_argument(
        "--annotations", type=Path, help="Explicit completed review; no automatic labels"
    )
    args = parser.parse_args()
    corpus, digest = load_corpus(args.corpus)
    annotation = None
    if args.annotations:
        corpus, annotation = apply_annotations(corpus, digest, args.annotations)
    model, error = None, None
    if args.semantic:
        try:
            model = load_local_model(settings.semantic_model_cache_dir)
        except Exception as exc:
            error = type(exc).__name__
    records, summaries = evaluate(corpus, model)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = args.output or Path(__file__).with_name(f"retrieval-comparison-{timestamp}.json")
    output = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "corpusHash": digest,
        "corpusVersion": corpus["version"],
        "annotationStatus": corpus["annotationStatus"],
        "annotation": annotation,
        "runtime": {"python": python_version()},
        "externalModelCalls": 0,
        "semanticStatus": "active" if model else "not_run",
        "semanticLoadError": error,
        "engines": {
            "lexical": LEXICAL_VERSION,
            "detectors": FORMULA_VERSION,
            "semantic": VERSION,
            "semanticRevision": MODEL_REVISION,
            "semanticModelSha256": MODEL_SHA256,
            "semanticThreshold": MIN_SIMILARITY,
        },
        "boundaries": [
            "Synthetic provisional labels; not independent or held-out",
            "Candidate relevance does not prove implementation or capability",
            "Semantic engine retrieves documents only; compare documentScope",
            "Ranks follow production insertion order, not unified learned scoring",
        ],
        "summary": summaries,
        "cases": records,
    }
    for package in ("fastembed", "onnxruntime", "numpy"):
        try:
            output["runtime"][package] = version(package)
        except PackageNotFoundError:
            output["runtime"][package] = None
    with target.open("x", encoding="utf-8") as result:
        json.dump(output, result, ensure_ascii=False, indent=2)
    if args.review_output:
        review = {
            "corpusHash": digest,
            "reviewer": "",
            "reviewedAt": "",
            "instructions": "Mark sources and support kind independently; no model output.",
            "cases": [
                {
                    "id": case["id"],
                    "skill": case["skill"],
                    "query": case["query"],
                    "documents": case["documents"],
                    "relevantSources": [],
                    "noRelevantSource": None,
                    "reason": "",
                }
                for case in corpus["cases"]
            ],
        }
        with args.review_output.open("x", encoding="utf-8") as review_file:
            json.dump(review, review_file, ensure_ascii=False, indent=2)
    print(
        json.dumps(
            {
                "output": str(target),
                "semanticStatus": output["semanticStatus"],
                "summary": {engine: data["documentScope"] for engine, data in summaries.items()},
            },
            ensure_ascii=False,
        )
    )
    return (
        0
        if (not error and all(data["allCases"]["sourceExact"] for data in summaries.values()))
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
