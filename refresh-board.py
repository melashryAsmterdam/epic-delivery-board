#!/usr/bin/env python3
"""
refresh-board.py — rewrite the snapshot inside live-board.html from Jira.

Run it on a schedule (cron / Task Scheduler / CI). It rewrites only the block
between the SNAPSHOT-START and SNAPSHOT-END markers, so the layout, styling and
live-refresh logic are never touched.

    export JIRA_BASE=https://webookcom.atlassian.net
    export JIRA_EMAIL=you@webook.com
    export JIRA_TOKEN=...            # id.atlassian.com > Security > API tokens
    python3 refresh-board.py live-board.html

Daily at 06:00, via crontab -e:
    0 6 * * *  cd /srv/board && /usr/bin/python3 refresh-board.py live-board.html >> refresh.log 2>&1

Only needs the standard library.
"""

import base64, datetime as dt, json, os, sys, urllib.request, urllib.error

BASE  = os.environ.get("JIRA_BASE",  "").rstrip("/")
EMAIL = os.environ.get("JIRA_EMAIL", "")
TOKEN = os.environ.get("JIRA_TOKEN", "")

CORE   = ["CBPC", "CCS", "CHOL", "CR", "CSD"]
TRAVEL = "10749"
ECO    = ["Ecosystem: Subscriptions & Loyalty", "Ecosystem: Incentives",
          "Ecosystem: Reco & Personalization", "Ecosystem: TrueFan"]
CLOSED_SINCE = "2026-07-01"          # Done epics are kept from this date onward

DRI, RELEASE, TSHIRT = "customfield_10042", "customfield_10176", "customfield_10578"
FIELDS = ["summary", "status", "labels", "duedate", "reporter",
          "statuscategorychangedate", DRI, RELEASE, TSHIRT]

# Table tabs hide these; Discovery is deliberately kept (it shows on every tab).
TABLE_EXCLUDE = {"Backlog", "New"}


def jql(query, fields):
    """POST /rest/api/3/search/jql, following nextPageToken to the end."""
    if not (BASE and EMAIL and TOKEN):
        sys.exit("Set JIRA_BASE, JIRA_EMAIL and JIRA_TOKEN first.")
    auth = base64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
    issues, token = [], None
    while True:
        body = {"jql": query, "maxResults": 100, "fields": fields}
        if token:
            body["nextPageToken"] = token
        req = urllib.request.Request(
            f"{BASE}/rest/api/3/search/jql",
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Basic {auth}",
                     "Content-Type": "application/json",
                     "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                page = json.load(r)
        except urllib.error.HTTPError as e:
            sys.exit(f"Jira {e.code} on query: {query}\n{e.read().decode()[:400]}")
        issues += page.get("issues", [])
        token = page.get("nextPageToken")
        if not token:
            return issues


def row(issue, domain):
    f = issue["fields"]
    rel = f.get(RELEASE)
    size = (f.get(TSHIRT) or {}).get("value", "") if f.get(TSHIRT) else ""
    return {
        "key": issue["key"],
        "summary": (f.get("summary") or "").strip(),
        "project": issue["key"].split("-")[0],
        "status": (f.get("status") or {}).get("name", "Unknown"),
        "dri": (f.get(DRI) or {}).get("displayName", "") if f.get(DRI) else "",
        "release": "" if rel is None else str(rel),
        "eta": f.get("duedate") or "",
        "since": (f.get("statuscategorychangedate") or "")[:10],
        "labels": f.get("labels") or [],
        "reporter": (f.get("reporter") or {}).get("displayName", "") if f.get("reporter") else "",
        "size": size,
        "domain": domain,
    }


def defect_counts(keys):
    """total / open / rejected per epic, tallied from child Bugs in chunks of 40."""
    counts = {k: [0, 0, 0] for k in keys}
    for i in range(0, len(keys), 40):
        chunk = keys[i:i + 40]
        for b in jql(f"issuetype = Bug AND parent in ({','.join(chunk)})",
                     ["status", "parent"]):
            parent = (b["fields"].get("parent") or {}).get("key")
            if parent not in counts:
                continue
            st = b["fields"]["status"]
            counts[parent][0] += 1
            if st["name"] == "Defect Rejected":
                counts[parent][2] += 1          # Jira files this under Done
            elif st["statusCategory"]["key"] != "done":
                counts[parent][1] += 1
    return counts


def js_rows(name, rows, extra=""):
    """Emit one `let NAME = [...].map(...)` block matching the board's shape."""
    lines = []
    for r in rows:
        lines.append(json.dumps([r["key"], r["summary"], r["project"], r["status"],
                                 r["dri"], "", r["release"], r["eta"], r["since"],
                                 r["labels"]], ensure_ascii=False))
    body = ",\n".join(lines)
    return (f"let {name} = [\n{body}\n]"
            ".map(r=>({key:r[0],summary:r[1],project:r[2],status:r[3],dri:r[4],lead:r[5],"
            "release:r[6]||'',eta:r[7]||'',since:r[8],labels:r[9]||[],dor:dorState(r[9]),"
            f"{extra}"
            "size:SIZE[r[0]]||'',"
            "bugs:(DEFECTS[r[0]]||[0,0,0])[0],bugsOpen:(DEFECTS[r[0]]||[0,0,0])[1],"
            "bugsRej:(DEFECTS[r[0]]||[0,0,0])[2],"
            "age:Math.round((TODAY-new Date(r[8]+'T00:00:00'))/864e5)}));\n")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "live-board.html"
    core_list, eco_list = ",".join(CORE), ",".join(f'"{p}"' for p in ECO)
    recent = f'(statusCategory != Done OR resolved >= "{CLOSED_SINCE}")'

    print("querying Jira…")
    core   = [row(i, "Core")   for i in jql(f"project in ({core_list}) AND issuetype = Epic AND statusCategory != Done", FIELDS)]
    closed = [row(i, "Core")   for i in jql(f"project in ({core_list}) AND issuetype = Epic AND statusCategory = Done AND resolved >= \"{CLOSED_SINCE}\"", FIELDS)]
    travel = [row(i, "Travel") for i in jql(f"project = {TRAVEL} AND issuetype = Epic AND {recent}", FIELDS)]
    eco    = [row(i, "ECO")    for i in jql(f"project in ({eco_list}) AND issuetype = Epic AND {recent}", FIELDS)]

    travel = [r for r in travel if r["status"] not in TABLE_EXCLUDE]
    eco    = [r for r in eco    if r["status"] not in TABLE_EXCLUDE]

    everything = core + closed + travel + eco
    print(f"  {len(core)} core open, {len(closed)} core done, {len(travel)} travel, {len(eco)} eco")

    print("counting defects…")
    counts = defect_counts([r["key"] for r in everything])
    total = sum(v[0] for v in counts.values())
    print(f"  {total} defects, {sum(v[1] for v in counts.values())} open, "
          f"{sum(v[2] for v in counts.values())} rejected")

    reporter = {r["key"]: r["reporter"] for r in everything if r["reporter"]}
    sizes    = {r["key"]: r["size"]     for r in everything if r["size"]}

    block = (
        "/* SNAPSHOT-START — refresh-board.py rewrites everything between these markers */\n"
        f"const SNAPSHOT_DATE = '{dt.date.today().isoformat()}';\n"
        f"let REPORTER = {json.dumps(reporter, ensure_ascii=False)};\n"
        f"let SIZE = {json.dumps(sizes, ensure_ascii=False)};\n"
        f"let DEFECTS = {json.dumps(counts)};\n"
        + js_rows("EPICS", core, "domain:'Core',")
        + js_rows("CLOSED_EPICS", closed, "domain:'Core',closed:true,")
        + js_rows("TRAVEL_EPICS", travel, "domain:'Travel',")
        + js_rows("ECO_EPICS", eco, "domain:'ECO',")
        + "/* SNAPSHOT-END */"
    )

    html = open(path, encoding="utf-8").read()
    a = html.index("/* SNAPSHOT-START")
    b = html.index("/* SNAPSHOT-END */") + len("/* SNAPSHOT-END */")
    open(path, "w", encoding="utf-8").write(html[:a] + block + html[b:])
    print(f"updated {path} — snapshot dated {dt.date.today().isoformat()}")


if __name__ == "__main__":
    main()
