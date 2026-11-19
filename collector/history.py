"""Append one row per project from su-watch.json to history.csv (for trends later)."""
import csv
import json
import os
import sys

src, dst = sys.argv[1], sys.argv[2]
d = json.load(open(src))
fields = ["generated", "project", "budget", "used", "su_per_hour", "charged_su_per_hour_7d",
          "servers", "idle", "quota_cores", "alloc_end"]
new = not os.path.exists(dst)
with open(dst, "a", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    if new:
        w.writeheader()
    for p in d["projects"]:
        if "error" in p:
            continue
        a = p.get("allocation") or {}
        w.writerow({"generated": d["generated"], "project": p["project"], "budget": a.get("budget"),
                    "used": p.get("used"), "su_per_hour": p.get("su_per_hour"),
                    "charged_su_per_hour_7d": p.get("charged_su_per_hour_7d"),
                    "servers": len(p.get("servers", [])), "idle": len(p.get("idle", [])),
                    "quota_cores": p.get("quota_cores"), "alloc_end": a.get("end")})
