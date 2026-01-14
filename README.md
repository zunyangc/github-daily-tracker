# GitHub repo maintainer contributions daily tracker

This tool **automatically updates an Excel workbook** with your **daily GitHub contributions** (issues, PRs, commits) for a specific repository.

***

## What this tracker updates automatically

For the selected repo and user:

*   **Issues Triaged**  
    Unique issues you commented on that day

*   **Issues Resolved**  
    Issues you closed that day (from your GitHub events)

*   **PRs Created**  
    PRs you opened that day

*   **PRs Merged**  
    PRs you authored that were merged that day

*   **Commits**  
    Number of commits you pushed to the repo that day (via PushEvent + compare API)

*   **Open Issues / Open PRs**  
    Snapshot counts as of end‑of‑day

***

## What you fill manually in Excel

These columns are **never touched** by the script:

*   **ADO Tests**
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

### 1️⃣ Clone the repository

```bash
git clone <your-repo-url>
cd azcollection-daily-tracker
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
# Required scopes: read access to repos and events
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Output Excel filename (created by init_tracker.py, updated by update_tracker.py)
TRACKER_OUT="daily_contributions_tracker_auto.xlsx"

# Worksheet name inside the Excel file where daily rows are written
TRACKER_SHEET="worksheet_name"

# GitHub repository owner (organization or user)
GITHUB_OWNER="repo-owner"

# GitHub repository name
GITHUB_REPO="repo-name"

# Your GitHub username (used to filter events and search results)
GITHUB_USERNAME="zunyangc"

# Your local timezone (stored in Excel for reference)
# NOTE: GitHub APIs use UTC; this does not change query logic
TRACKER_TIMEZONE="Asia/Kuala_Lumpur"
```

⚠️ **Important rules**

*   `.env` **must exist**
*   Every variable above **must be present and non‑empty**
*   The scripts **will exit immediately** if anything is missing

***

### 4️⃣ Initialize the Excel tracker (run once)

This creates the Excel workbook, headers, and Config sheet.

```bash
python init_tracker.py
```

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

## Notes & limitations

*   GitHub **User Events API** only exposes **recent activity**
*   This tracker is designed for **daily / ongoing use**
*   It is **not suitable** for reconstructing years of historical data
*   All GitHub timestamps are evaluated in **UTC**

***

## Troubleshooting

*   **`.env file not found`** → create `.env` in the same directory
*   **Missing required config** → check for typos or empty values
*   **Worksheet not found** → run `init_tracker.py` first
*   **BadZipFile / invalid xlsx** → delete workbook and re‑run init

***
