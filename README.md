# GitHub repo maintainer contributions daily tracker

This tool **automatically updates an Excel workbook** with your **daily GitHub contributions** (issues, PRs, commits) for a specific repository.

***

## What this tracker updates automatically

For the selected repo and user:

*   **Issues Triaged**  
    Unique issues you commented on that day (via Issue Comments API, scoped to repo)

*   **Issues Resolved**  
    Issues you personally closed that day (via Search API + Issue Events verification)

*   **PRs Created**  
    PRs you opened that day

*   **PRs Merged**  
    PRs you authored that were merged that day

*   **Commits**  
    Commits you authored in the repo that day (via Commits API)

*   **Open Issues / Open PRs**  
    Snapshot counts as of end‑of‑day (via two Search API queries)

***

## What you fill manually in Excel

These columns are **never touched** by the script:

*   **Release**
*   **Notes**

***

## Folder layout

All files must live in the **same directory**:

    .
    ├── .env
    ├── init_tracker.py
    ├── update_tracker.py
    ├── run_update.sh
    ├── requirements.txt
    └── daily_contributions_tracker_auto.xlsx   # created by init_tracker.py

***

## Setup (step by step)

> **Requires Python 3.10+.**

### (Pre-requisites) Generate GitHub Personal Access Token
```
1. Go to GitHub
2. Click on Profile -> Settings
3. Click on Developer Settings
4. Click on Personal access tokens -> Tokens (Classic)
5. Click on Generate new token -> Generate new token (Classic)
6. Give an unique name, select expiration durations
7. Make sure the "repo" scope is checked
8. Click on Generate token
```

### 1️⃣ Clone the repository

```bash
git clone <your-repo-url>
cd github-daily-tracker
```

***

### 2️⃣ Create and activate a Python virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

***

### 3️⃣ Create a `.env` file (REQUIRED)

Create a file named **`.env`** in the same folder as the scripts.

### ✅ Sample `.env` (token truncated)

```env
# GitHub Personal Access Token (PAT)
# Required scopes: read access to repos
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Output Excel filename (created by init_tracker.py, updated by update_tracker.py)
TRACKER_OUT="daily_contributions_tracker_auto.xlsx"

# Worksheet name inside the Excel file where daily rows are written
TRACKER_SHEET="worksheet_name"

# GitHub repository owner (organization or user)
GITHUB_OWNER="repo-owner"

# GitHub repository name
GITHUB_REPO="repo-name"

# Your GitHub username (used to filter search results and commits)
GITHUB_USERNAME="zunyangc"

# Your local timezone (IANA name). The "day" window for all metrics is
# interpreted in this timezone, then translated to UTC for API queries.
# Default: UTC.
TRACKER_TIMEZONE="Asia/Kuala_Lumpur"

# ---------- Optional (sensible defaults applied if omitted) ----------

# GitHub API base URL. Set this to use GitHub Enterprise Server.
# Default: https://api.github.com
# GHES example: https://github.example.com/api/v3
# GITHUB_API_BASE_URL="https://api.github.com"

# Excel display format for the Date column. Default: DD/MM/YYYY
# Examples: "YYYY-MM-DD", "MM/DD/YYYY", "DD-MMM-YYYY"
# TRACKER_DATE_FORMAT="DD/MM/YYYY"

# Whether to compute the "Open Issues / Open PRs" snapshot (4 extra Search
# API calls per run). Set "false" to skip and save quota. Default: true
# TRACKER_INCLUDE_OPEN_SNAPSHOT="true"

# Maximum pages to walk for paginated endpoints (commits, issue comments,
# search, issue events). Default: 10. Increase for very busy repos.
# TRACKER_MAX_PAGES="10"
```

⚠️ **Important rules**

*   `.env` **must exist**
*   Every variable above **must be present and non‑empty**
*   The scripts **will exit immediately** if anything is missing

***

### 4️⃣ Initialize the Excel tracker (run once)

This creates the Excel workbook, headers, and Config sheet.

```bash
python3 init_tracker.py
```

> If a workbook with the same name already exists the script will refuse to
> overwrite it. Pass `--force` to replace it (this discards existing data):
>
> ```bash
> python3 init_tracker.py --force
> ```

✅ Result:

*   `daily_contributions_tracker_auto.xlsx` is created
*   Worksheet and column structure are initialized
*   Config sheet is populated from `.env`

***

### 5️⃣ Update the tracker (daily usage)

#### Update **today**

```bash
./run_update.sh
```

#### Update a **specific date**

```bash
./run_update.sh 2026-01-13
./run_update.sh 13/01/2026
```

✅ The script will:

*   Validate `.env`
*   Validate the workbook & worksheet
*   Fetch GitHub metrics
*   Insert or update the row for that date
*   Update “Last Updated (UTC)” in the Config sheet

***

## Optional: One-shot run via GitHub Copilot CLI

If you use [GitHub Copilot CLI](https://docs.github.com/en/copilot/github-copilot-in-the-cli),
this repo ships a `copilot-instructions.md` template that lets you trigger the
full daily workflow with a single command (e.g. `runghtracker`) inside `copilot`.

### What it does

When invoked, Copilot will:

1. Run `./run_update.sh` (optionally with a date) and show the metrics table.
2. Use `gh` CLI to fetch the day's PRs created/merged, issues closed, issues
   commented on, and PRs in progress.
3. Ask before writing anything, then write a summary to the **Notes** column.

### Setup

1. **Install GitHub CLI** and authenticate (used by Copilot to fetch activity):

   ```bash
   gh auth login
   ```

2. **Install the instructions** so Copilot CLI auto-loads them.
   Pick one of the supported locations
   (see `copilot /instructions` for the full list):

   ```bash
   # Personal (recommended) — applies anywhere you run `copilot`
   mkdir -p ~/.copilot
   cp copilot-instructions.md ~/.copilot/copilot-instructions.md

   # OR repo-scoped — only loads when you run `copilot` inside this repo
   mkdir -p .github
   cp copilot-instructions.md .github/copilot-instructions.md
   ```

3. **Edit the copy** and replace the placeholders with your own values:

   | Placeholder                | Replace with                                 |
   |----------------------------|----------------------------------------------|
   | `<owner>/<repo>`           | `GITHUB_OWNER/GITHUB_REPO` from `.env`       |
   | `<github-username>`        | `GITHUB_USERNAME` from `.env`                |
   | `<path-to-excel-workbook>` | absolute path to your `TRACKER_OUT` file     |
   | `<sheet-name>`             | `TRACKER_SHEET` from `.env`                  |

   If you cloned this repo somewhere other than `~/github-daily-tracker`,
   update the `cd` path in the **Tracker Script** section too.

4. **Reload Copilot CLI** and try it:

   ```bash
   copilot
   > runghtracker
   # or with a specific date
   > runghtracker 10/4/2026
   ```

> **Note**: Make sure the Notes column index in `copilot-instructions.md`
> matches your actual workbook layout.

***

## Notes & limitations

*   All metrics use the **Search API**, **Issue Comments API**, **Issue Events API**, and **Commits API** (no Events firehose dependency)
*   Works for **any date** — not limited by the 90‑day Events API window
*   The "day" window is interpreted in your **`TRACKER_TIMEZONE`** (defaults to `UTC`). All API queries are translated to the corresponding UTC range, so contributions made near local midnight land on the expected tracker date. The default `parse_args` "today" also uses this timezone.
*   `Open Issues` / `Open PRs` are an **approximation**: items that were closed on/before the target day, later reopened, and currently open will be miscounted.
*   Search API has a **30 requests/minute** rate limit for authenticated users and a hard **1000-result** cap per query. The script logs a warning when a query exceeds this cap.
*   `run_update.sh` automatically activates `./venv` if present, and uses `python3` (override with `PYTHON=...`).

***

## Troubleshooting

*   **`.env file not found`** → create `.env` in the same directory
*   **Missing required config** → check for typos or empty values
*   **Worksheet not found** → run `init_tracker.py` first
*   **BadZipFile / invalid xlsx** → delete workbook and re‑run init

***
