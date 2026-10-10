"""Apply the frozen protocol's declared tolerances to the two probe outputs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

# Must match tolerance-predeclared.md, which was written before any probe run.
CROSS_VERSION_ABSOLUTE_TOLERANCE = 1e-5
MIN_COSINE = 1.0 - 1e-9


def main() -> None:
    baseline = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    candidate = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    left = np.asarray(baseline["vectors"], dtype=np.float64)
    right = np.asarray(candidate["vectors"], dtype=np.float64)
    assert left.shape == right.shape == (6, 384)
    assert baseline["weightHashes"] == candidate["weightHashes"]
    max_abs = float(np.max(np.abs(left - right)))
    cosines = np.sum(left * right, axis=1) / (
        np.linalg.norm(left, axis=1) * np.linalg.norm(right, axis=1)
    )
    ranking_equal = baseline["queryRanking"] == candidate["queryRanking"]
    result = {
        "toleranceSource": "tolerance-predeclared.md (written before probe runs)",
        "crossVersionAbsoluteTolerance": CROSS_VERSION_ABSOLUTE_TOLERANCE,
        "minimumCosineThreshold": MIN_COSINE,
        "versions": {
            "baseline": {k: baseline[k] for k in ("fastembed", "onnxruntime", "pillow")},
            "candidate": {k: candidate[k] for k in ("fastembed", "onnxruntime", "pillow")},
        },
        "weightHashesIdentical": True,
        "maxAbsoluteDifference": max_abs,
        "maxAbsoluteDifferenceWithinTolerance": max_abs <= CROSS_VERSION_ABSOLUTE_TOLERANCE,
        "observedMinimumCosine": float(np.min(cosines)),
        "minCosineWithinTolerance": bool(np.min(cosines) >= MIN_COSINE),
        "queryRankingIdentical": ranking_equal,
        "normsIdentical": baseline["norms"] == candidate["norms"],
    }
    result["passed"] = (
        result["maxAbsoluteDifferenceWithinTolerance"]
        and result["minCosineWithinTolerance"]
        and result["queryRankingIdentical"]
        and result["normsIdentical"]
    )
    Path(sys.argv[3]).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
