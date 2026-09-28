"""合成静态脚本，不提供执行结果、显著性或因果证据。"""

import csv


def summarize(path):
    metrics, seen, missing = {}, set(), []
    with open(path, encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            if row["campaign"] in seen:
                continue
            seen.add(row["campaign"])
            if not row["views"]:
                missing.append(row["campaign"])
                continue
            views, clicks = int(row["views"]), int(row["clicks"])
            metrics[row["campaign"]] = clicks / views if views > 0 else None
    return {"observed_ctr": metrics, "missing_views": missing}
