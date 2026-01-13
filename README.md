
# azcollection daily tracker (GitHub -> Excel)

This folder updates **daily_contributions_tracker_auto.xlsx** with GitHub metrics.

## What it updates automatically
- Issues Triaged (unique issues you commented on that day)
- Issues Resolved (issues you closed that day; based on your events stream)
- PRs Created (PRs you opened that day; GitHub search)
- PRs Merged (PRs you authored merged that day; GitHub search)
- Commits (commits authored by you that day; repo commits endpoint)
- Open Issues (current open issues count in repo)
- Open PRs (current open PRs count in repo)

## What you fill manually
- ADO Tests
- Release
- Notes

## Setup
1) Put these files in one folder:
   - daily_contributions_tracker_auto.xlsx
   - update_tracker.py
   - run_update.sh
   - requirements.txt

2) Create a GitHub PAT and set it as `GITHUB_TOKEN`.
   - Recommended: create a `.env` file:
     GITHUB_TOKEN=ghp_xxx

3) Ensure the **Config** sheet has your values:
   - GitHub Owner (e.g., ansible-collections)
   - GitHub Repo (e.g., azure)
   - GitHub Username (e.g., zunyangc)

## Run
- Update today:
  `./run_update.sh`

- Update a specific day:
  - `./run_update.sh 2026-01-13`
  - `./run_update.sh 13/1/2026`  (DD/M/YYYY)

## Notes / limitations
GitHub user events API only exposes recent activity. This approach is ideal for daily use, not for reconstructing years of history.
