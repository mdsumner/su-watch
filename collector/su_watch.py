"""SU watch: Service Unit budget, use and burn for every Nectar project you belong to.

Reads only. Run from su-watch.sh, which loads OpenStack credentials (one user password
works for all your projects; each call is scoped to one project with OS_PROJECT_ID).

Output (JSON, safe to publish): per project, the current allocation's SU budget, SU used
since it started (Rating service), current burn from the servers that exist (flavour
`nectar:rate`, SU/hour), and when the budget runs out at that rate. No IPs, IDs, emails
or people's names.
"""
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone

OS = os.path.expanduser("~/venvs/openstack/bin/openstack")
ALLOC = "https://allocations.rc.nectar.org.au/rest_api/allocations/"
NOW = datetime.now(timezone.utc)

# VM id -> name, remembered across runs so deleted VMs keep their names in "what used it".
# Local only: ids are never published.
NAMES_FILE = os.path.expanduser("~/.cache/su-watch/names.json")
try:
    NAMES = json.load(open(NAMES_FILE))
except (OSError, ValueError):
    NAMES = {}


def osc(args, project_id, fmt=True):
    env = dict(os.environ, OS_PROJECT_ID=project_id)
    env.pop("OS_PROJECT_NAME", None)
    cmd = [OS] + args + (["-f", "json"] if fmt else [])
    out = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.strip().splitlines()[-1] if out.stderr.strip() else "failed")
    return json.loads(out.stdout) if fmt else out.stdout.strip()


def allocation(project_id, token):
    req = urllib.request.Request(ALLOC + "?project_id=" + project_id,
                                 headers={"X-Auth-Token": token, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        recs = json.load(r).get("results", [])
    today = NOW.date().isoformat()
    approved = [a for a in recs if a.get("status") == "A"]
    if not approved:
        return None
    # the approved record covering today, else the one that ended most recently
    current = [a for a in approved if a["start_date"] <= today <= a["end_date"]]
    cur = max(current or approved, key=lambda a: (a["end_date"], a["id"]))
    latest = max(recs, key=lambda a: a.get("modified_time") or "")
    budget = next((q["quota"] for q in cur.get("quotas") or [] if q.get("resource") == "rating.budget"), None)
    return {"start": cur["start_date"], "end": cur["end_date"], "ended": cur["end_date"] < today,
            "bundle": cur.get("bundle"), "home": cur.get("allocation_home_display"),
            "budget": budget, "request_status": latest.get("status_display"),
            "request_date": str(latest.get("modified_time") or "")[:10]}


def rated(pid, begin, end):
    """SU charged by the Rating service between two datetimes."""
    summ = osc(["rating", "summary", "get", "-b", begin.strftime("%Y-%m-%dT%H:%M:%S"),
                "-e", end.strftime("%Y-%m-%dT%H:%M:%S")], pid)
    return sum(float(r.get("Rate") or 0) for r in summ)


def project(name, pid):
    p = {"project": name}
    token = osc(["token", "issue", "-c", "id"], pid)["id"]
    a = allocation(pid, token)
    p["allocation"] = a
    rates = {f["Name"]: float((f.get("Properties") or {}).get("nectar:rate", "nan"))
             for f in osc(["flavor", "list", "--all", "--long"], pid)}
    servers = []
    for s in osc(["server", "list", "--long"], pid):
        fl = s.get("Flavor Name") or s.get("Flavor")
        servers.append({"name": s["Name"], "status": s["Status"], "flavor": fl,
                        "su_per_hour": rates.get(fl)})
    p["servers"] = sorted(servers, key=lambda s: -(s["su_per_hour"] or 0))
    p["idle"] = [s["name"] for s in servers if s["status"] in ("SHUTOFF", "SUSPENDED", "PAUSED")]
    p["unrated_flavours"] = sorted({s["flavor"] for s in servers if s["su_per_hour"] is None})
    # list rate: what the servers that exist now cost per hour (shelved ones cost nothing)
    list_burn = sum(s["su_per_hour"] or 0 for s in servers if s["status"] != "SHELVED_OFFLOADED")
    p["list_su_per_hour"] = round(list_burn, 3)
    # charged rate: what Rating actually billed over the last 7 days
    week = rated(pid, NOW - timedelta(days=7), NOW) / 168
    p["charged_su_per_hour_7d"] = round(week, 3)
    # project forward from the list rate (reflects today's changes), unless flavours lack a rate
    burn = list_burn if not p["unrated_flavours"] else max(list_burn, week)
    p["su_per_hour"] = round(burn, 3)
    p["su_per_year"] = round(burn * 8760)
    cores = osc(["limits", "show", "--absolute"], pid)
    p["quota_cores"] = next((r["Value"] for r in cores if r["Name"] == "maxTotalCores"
                             or r["Name"] == "max_total_cores"), None)
    p["expired"] = p["quota_cores"] == 0
    if a:
        start = datetime.fromisoformat(a["start"]).replace(tzinfo=timezone.utc)
        used = rated(pid, start, NOW)
        p["used"] = round(used)
        # what used it: SU per resource since the allocation started, by VM name where it
        # still exists (Rating keeps charges for deleted VMs, but not their names)
        NAMES.update({s["ID"]: s["Name"] for s in osc(["server", "list", "-c", "ID", "-c", "Name"], pid)})
        names = {i: (n if any(s["name"] == n for s in servers) else n + " (deleted)") for i, n in NAMES.items()}
        by = osc(["rating", "summary", "get", "-g", "id", "--limit", "1000",
                  "-b", start.strftime("%Y-%m-%dT%H:%M:%S"), "-e", NOW.strftime("%Y-%m-%dT%H:%M:%S")], pid)
        p["used_by"] = [{"name": names.get(r["Id"], "deleted VM"), "su": round(float(r["Rate"] or 0)),
                         "hours": round(float(r["Qty"] or 0))}
                        for r in sorted(by, key=lambda r: -float(r["Rate"] or 0)) if float(r["Rate"] or 0) >= 1]
        if a["budget"] and not a["ended"]:
            left = a["budget"] - used
            p["pct_used"] = round(100 * used / a["budget"], 1)
            if left <= 0:
                p["runs_out"] = "over budget"
            elif burn > 0:
                p["runs_out"] = (NOW + timedelta(hours=left / burn)).date().isoformat()
            else:
                p["runs_out"] = "not at current burn"
        elif a["ended"]:
            p["runs_out"] = "allocation ended " + a["end"]
    return p


def main():
    projects = osc(["project", "list", "--my-projects", "-c", "ID", "-c", "Name"], os.environ["OS_PROJECT_ID"])
    out = {"generated": NOW.strftime("%Y-%m-%dT%H:%MZ"), "projects": []}
    for pr in sorted(projects, key=lambda x: x["Name"].lower()):
        try:
            out["projects"].append(project(pr["Name"], pr["ID"]))
        except Exception as e:  # one project failing shouldn't stop the rest
            msg = re.sub(r"\s*\(Request-ID:[^)]*\)", "", str(e))
            msg = "no access (HTTP 401)" if "401" in msg else msg[:120]
            out["projects"].append({"project": pr["Name"], "error": msg})
    os.makedirs(os.path.dirname(NAMES_FILE), exist_ok=True)
    with open(NAMES_FILE, "w") as f:
        json.dump(NAMES, f, indent=1, sort_keys=True)
    json.dump(out, sys.stdout, indent=1)


if __name__ == "__main__":
    main()
