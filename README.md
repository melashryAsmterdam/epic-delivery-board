# Epic Delivery Board

A single-file delivery board across three domains, refreshed from Jira daily.

| File | What it is |
|---|---|
| `live-board.html` | The board. Ships with a snapshot so it renders instantly, tries a live Jira pull on load, and has a **Refresh** button. |
| `epic-delivery-board.html` | Frozen snapshot. No network calls — works anywhere, including from disk. |
| `refresh-board.py` | Rewrites the snapshot block inside `live-board.html` from Jira. Standard library only. |
| `.github/workflows/refresh-board.yml` | Runs the script daily at 06:00 Riyadh and commits the result. |

## Tabs

- **Core** — CBPC, CCS, CHOL, CR, CSD
- **Travel** — LTRF (project 10749)
- **ECO** — Ecosystem: Subscriptions & Loyalty, Incentives, Reco & Personalization, TrueFan
- **Defects analysis** — defect counts per epic with refinement, size, DRI and reporter

Backlog and New are excluded everywhere. Discovery is shown. Done epics appear from `CLOSED_SINCE` onward.

## Setup

Add three repository secrets under **Settings → Secrets and variables → Actions**:

| Secret | Value |
|---|---|
| `JIRA_BASE` | `https://webookcom.atlassian.net` |
| `JIRA_EMAIL` | your Atlassian account email |
| `JIRA_TOKEN` | from id.atlassian.com → Security → API tokens |

Then set **Settings → Actions → General → Workflow permissions** to **Read and write**, or the job cannot commit the refreshed file back.

Trigger a first run from the Actions tab with **Run workflow** rather than waiting for the schedule.

## Running it locally

```bash
export JIRA_BASE=https://webookcom.atlassian.net
export JIRA_EMAIL=you@webook.com
export JIRA_TOKEN=...
python3 refresh-board.py live-board.html
```

## Definitions

- **Refinement** — from Jira labels. `DOR`/`Refined` = refined; `DoR_NotMet`/`No_DOR`/`NotRefined`/`No_Refinement` = not met; `To-Be-Refined`/`Refine_2`/`rc-refinement-gap` = to refine; no DoR-family label = not refined. `Refinement` is excluded deliberately — it appears alongside both `DOR` and `No_DOR`, so it is a process tag, not a verdict.
- **Defects** — child issues of type Bug.
- **Open** — statusCategory is not Done.
- **Rejected** — status `Defect Rejected`. Jira files this under the Done category, so it is excluded from Fixed; counting it as fixed inflates throughput.
- **Days in progress** — from `statuscategorychangedate`. Time in the In Progress category, Discovery included. Not time in the current status.

## Field mapping

| Column | Jira field |
|---|---|
| DRI | `customfield_10042` |
| Release | `customfield_10176` |
| Size | `customfield_10578` (T Shirt Size) |
| Tech Lead | No such field exists — hardcoded via `TECH_LEAD` |

## Known limits

- The in-page **Refresh** button only works when the page is served from an origin Jira accepts (Forge app or a proxy forwarding `/rest/api/3/*`). From disk or a plain static host it fails on CORS and falls back to the snapshot. The scheduled job is the mechanism that actually keeps data current.
- Release and due date are sparse outside ECO.
- An epic showing zero defects may mean defects were not linked as children, not that it is clean.
