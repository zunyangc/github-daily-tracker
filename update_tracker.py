"""
GitHub -> Excel daily tracker updater (with progress logging)

Purpose
-------
Updates (or creates) a single row in your Excel tracker for a given day, filling
in GitHub-derived metrics for *your personal contributions*.

What this script updates in Excel (auto-populated)
--------------------------------------------------
- Issues Triaged:
    Count of unique issues in the target repo where you commented on that day.
    (Uses IssueCommentEvent in your GitHub user events.)
- Issues Resolved:
    Count of issues you closed that day.
    (Uses IssuesEvent "closed" in your GitHub user events.)
- PRs Created:
    Count of PRs you opened that day.
    (Uses GitHub Search API query on PRs authored by you created on that date.)
- PRs Merged:
    Count of PRs authored by you that were merged that day.
    (Uses GitHub Search API query on PRs authored by you merged on that date.)
- Commits:
    Number of commits I pushed to this repository on that day (across all branches), regardless of merge strategy.
    (Uses PushEvent in your GitHub user events to count unique commit SHAs.)
- Open Issues / Open PRs (as-of that day):
    Snapshot count of open issues/PRs as-of end-of-day using advanced search:
      created<=day AND (open OR closed>day)

Manual columns (not overwritten)
-------------------------------
- ADO Tests, Release, Notes

Defaults
--------
- If no date argument is provided, defaults to *today* (local machine date).
- If TRACKER_XLSX env var is not set, uses "daily_contributions_tracker_auto.xlsx".

Important Limitations
---------------------
- GitHub User Events API only exposes recent history (not years back).
  This approach is perfect for daily/weekly logging, not deep historical rebuild.

Environment requirements
------------------------
- Set GITHUB_TOKEN (GitHub PAT) in env or in a .env file loaded by your runner.
"""

import os
import sys
import time
import datetime as dt
import zipfile
from typing import Tuple, Dict, Any, List, Set
from pathlib import Path

import requests
from openpyxl import load_workbook

API = "https://api.github.com"



def load_dotenv(dotenv_path: str = ".env") -> Dict[str, str]:
    """
    Minimal .env loader.
    Reads KEY=VALUE pairs, ignores blank lines and comments.
    Supports quoted values.
    """
    path = Path(dotenv_path)
    if not path.is_file():
        die(f"Workbook not found: {path}. Put the .xlsx in this folder or run init_tracker.py.")

    data: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()

        # remove optional quotes
        if (len(v) >= 2) and ((v[0] == v[-1]) and v[0] in ("'", '"')):
            v = v[1:-1]

        data[k] = v
    return data


def require_cfg(cfg: Dict[str, str], key: str) -> str:
    v = cfg.get(key)
    if not v:
        die(f"Missing required config in .env: {key}")
    return v


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    """
    Print a timestamped log line.

    Input:
        msg: message string

    Output:
        None (prints to stdout)
    """
    now = dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now}] {msg}")


def die(msg: str, code: int = 1) -> None:
    """
    Print an error message (timestamped) then exit.

    Input:
        msg: error description
        code: exit code (default: 1)

    Output:
        None (exits the process)
    """
    log(f"ERROR: {msg}")
    sys.exit(code)


def parse_args() -> dt.date:
    """
    Parse command-line date argument.

    Supported formats:
        - YYYY-MM-DD     e.g. 2026-01-13
        - DD/MM/YYYY     e.g. 13/01/2026
        - DD/MM/YY       e.g. 13/01/26

    If no argument is provided, defaults to *today* based on local machine date.

    Output:
        A dt.date object for the target day.
    """
    if len(sys.argv) >= 2 and sys.argv[1].strip():
        s = sys.argv[1].strip()
        fmts = ["%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y"]
        for f in fmts:
            try:
                return dt.datetime.strptime(s, f).date()
            except Exception:
                pass
        raise ValueError(f"Unsupported date format: {s}. Use YYYY-MM-DD or DD/MM/YYYY")
    return dt.datetime.now().date()


# ---------------------------------------------------------------------------
# GitHub REST helpers
# ---------------------------------------------------------------------------

def gh_headers(token: str) -> Dict[str, str]:
    """
    Build GitHub request headers.

    Input:
        token: GitHub personal access token (PAT)

    Output:
        dict of HTTP headers used in all GitHub API calls.
    """
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "azcollection-daily-tracker"
    }


def request_get(url: str, headers: Dict[str, str], params=None, retries: int = 3, backoff: float = 2.0) -> requests.Response:
    """
    Perform a GET request with basic retry logic for transient GitHub errors.

    Retries on:
        - 429, 502, 503, 504

    Special handling:
        - If 403 contains "rate limit", exits with a helpful message.

    Input:
        url: endpoint
        headers: HTTP headers dict
        params: query params dict
        retries: max retries
        backoff: seconds multiplier for incremental backoff

    Output:
        requests.Response (already status-checked via raise_for_status)
    """
    for attempt in range(1, retries + 1):
        r = requests.get(url, headers=headers, params=params)
        if r.status_code in (429, 502, 503, 504):
            log(f"HTTP {r.status_code} from GitHub. Retry {attempt}/{retries}...")
            time.sleep(backoff * attempt)
            continue
        if r.status_code == 403 and 'rate limit' in r.text.lower():
            die("GitHub rate limit hit (403). Try later or use a token with higher limits.")
        r.raise_for_status()
        return r
    # If we exhausted retries
    r.raise_for_status()
    return r


def get_all_pages(url: str, headers: Dict[str, str], params=None, max_pages: int = 10) -> List[Dict[str, Any]]:
    """
    Fetch and concatenate paginated GitHub REST API results.

    This follows 'Link' headers for pagination.

    Input:
        url: initial URL
        headers: HTTP headers dict
        params: initial query params
        max_pages: safety cap on total pages to fetch

    Output:
        A list of JSON objects from all fetched pages.
    """
    out: List[Dict[str, Any]] = []
    page = 1
    while url and page <= max_pages:
        r = request_get(url, headers=headers, params=params)
        out.extend(r.json())
        if 'next' in r.links:
            url = r.links['next']['url']
            params = None  # because next page URL already includes params
        else:
            url = None
        page += 1
    return out


# ---------------------------------------------------------------------------
# GitHub metrics: Search API counts
# ---------------------------------------------------------------------------

def search_count(query: str, headers: Dict[str, str], advanced: bool = False) -> int:
    """
    Run a GitHub Search API query and return total_count.

    Input:
        query: search query string, e.g. "repo:org/repo is:pr author:me created:2026-01-13"
        headers: GitHub headers
        advanced: enable advanced search (AND/OR parentheses) via parameter

    Output:
        Integer total_count returned by GitHub.
    """
    url = f"{API}/search/issues"
    params = {"q": query, "per_page": 1}
    if advanced:
        # Enables AND/OR + parentheses in REST search (GitHub supports advanced_search=true)
        params["advanced_search"] = "true"
    r = request_get(url, headers=headers, params=params)
    return int(r.json().get("total_count", 0))


def count_open_counts_asof(owner: str, repo: str, day: dt.date, headers: Dict[str, str]) -> Tuple[int, int]:
    """
    Compute open issues and open PRs snapshot "as-of end of target day".

    Logic:
        created<=day AND (is:open OR closed>day)

    This is an approximation but is good for daily snapshots.

    Input:
        owner, repo: target repo
        day: date object
        headers: GitHub headers

    Output:
        (open_issues_count, open_prs_count) as integers
    """
    day_str = day.strftime("%Y-%m-%d")

    q_open_issues_asof = (
        f"repo:{owner}/{repo} is:issue created:<={day_str} AND (is:open OR closed:>{day_str})"
    )
    q_open_prs_asof = (
        f"repo:{owner}/{repo} is:pr created:<={day_str} AND (is:open OR closed:>{day_str})"
    )

    open_issues = search_count(q_open_issues_asof, headers, advanced=True)
    open_prs = search_count(q_open_prs_asof, headers, advanced=True)
    return open_issues, open_prs


# ---------------------------------------------------------------------------
# GitHub metrics: User Events API parsing (triage / closes / commits)
# ---------------------------------------------------------------------------

def fetch_user_events(username: str, headers: Dict[str, str], max_pages: int = 3) -> List[Dict[str, Any]]:
    """
    Fetch recent user events from GitHub.

    Input:
        username: GitHub username
        headers: GitHub headers
        max_pages: number of pages to fetch (events API is limited anyway)

    Output:
        List of event JSON dicts (recent activity).
    """
    events_url = f"{API}/users/{username}/events"
    return get_all_pages(events_url, headers, params={"per_page": 100}, max_pages=max_pages)



def count_commits_pushed_to_repo_that_day(
    events: List[Dict[str, Any]],
    owner: str,
    repo: str,
    day: dt.date,
    headers: Dict[str, str],
) -> int:
    """
    Count commits pushed to the target repo on the target day.

    - Events API PushEvent no longer includes payload.commits/counts (post Oct 2025 changes),
      so we must use payload.before + payload.head to query commit data via REST.
    - We count commits per push by calling:
        GET /repos/{owner}/{repo}/compare/{before}...{head}

    Notes:
    - Events timestamps are UTC; filtering uses UTC date.
    - Dedup by push_id to avoid double-counting if the same event appears twice.
    - Handles new-branch pushes where 'before' can be all zeros by deriving a base from default branch head.
    """

    target_repo = f"{owner}/{repo}"
    total = 0
    seen_push_ids: Set[int] = set()

    # helper: GET repo default branch head sha (used for new branch case)
    def get_default_branch_head_sha() -> str:
        repo_url = f"{API}/repos/{owner}/{repo}"
        r = request_get(repo_url, headers=headers)
        default_branch = r.json().get("default_branch", "main")

        # fetch latest commit SHA on default branch
        commits_url = f"{API}/repos/{owner}/{repo}/commits"
        r2 = request_get(commits_url, headers=headers, params={"sha": default_branch, "per_page": 1})
        arr = r2.json()
        if isinstance(arr, list) and arr:
            return arr[0].get("sha")
        return ""

    default_base_sha = None
    ZERO_SHA = "0" * 40

    for ev in events:
        if ev.get("type") != "PushEvent":
            continue

        created_at = dt.datetime.strptime(ev["created_at"], "%Y-%m-%dT%H:%M:%SZ").date()
        if created_at != day:
            continue

        if ev.get("repo", {}).get("name") != target_repo:
            continue

        payload = ev.get("payload", {}) or {}
        push_id = payload.get("push_id")
        if isinstance(push_id, int):
            if push_id in seen_push_ids:
                continue
            seen_push_ids.add(push_id)

        before = payload.get("before")
        head = payload.get("head")

        if not before or not head:
            continue  # nothing to compare

        # If this is a new ref/branch, GitHub sometimes uses before = 0000...0000
        if before == ZERO_SHA:
            if default_base_sha is None:
                default_base_sha = get_default_branch_head_sha()
            if default_base_sha:
                before = default_base_sha
            else:
                # fallback: if we can't resolve base, count at least 1 (head)
                total += 1
                continue

        compare_url = f"{API}/repos/{owner}/{repo}/compare/{before}...{head}"
        resp = request_get(compare_url, headers=headers)
        data = resp.json()

        # Compare API returns total_commits + commits[] (commits[] can be truncated)
        total += int(data.get("total_commits", 0))

    return total


def count_triage_and_resolved_from_events(events: List[Dict[str, Any]], day: dt.date) -> Tuple[int, int]:
    """
    Compute:
      - Issues Triaged: unique issue numbers you commented on that day (non-PR issues)
      - Issues Resolved: number of issues closed by you that day

    Based on:
      - IssueCommentEvent (exclude PRs by checking 'pull_request' key)
      - IssuesEvent action=closed

    Input:
        events: list of GitHub events
        day: target date

    Output:
        (issues_triaged_count, issues_resolved_count)
    """
    issues_triaged_set: Set[int] = set()
    issues_resolved = 0

    for ev in events:
        # Commit counting is done by GitHub event UTC date, not local timezone
        created_at = dt.datetime.strptime(ev["created_at"], "%Y-%m-%dT%H:%M:%SZ").date()
        if created_at != day:
            continue

        etype = ev.get("type")
        payload = ev.get("payload", {}) or {}

        if etype == "IssueCommentEvent":
            issue = payload.get("issue", {}) or {}
            # Filter out PRs (PRs include "pull_request" key)
            if issue and "pull_request" not in issue:
                num = issue.get("number")
                if num is not None:
                    issues_triaged_set.add(num)

        if etype == "IssuesEvent" and payload.get("action") == "closed":
            issues_resolved += 1

    return len(issues_triaged_set), issues_resolved


# ---------------------------------------------------------------------------
# Aggregate daily metrics
# ---------------------------------------------------------------------------

def count_metrics(owner: str, repo: str, username: str, day: dt.date, headers: Dict[str, str]) -> Dict[str, int]:
    """
    Gather all metrics needed for one date row.

    Input:
        owner, repo: repository identifier
        username: GitHub username
        day: target date
        headers: GitHub headers

    Output:
        dict:
            issues_triaged, issues_resolved, prs_created, prs_merged,
            commits, open_issues, open_prs
    """
    day_str = day.strftime("%Y-%m-%d")

    # 1) PR counts via Search API
    log("Fetching PR counts (created / merged) via search...")
    prs_created = search_count(f"repo:{owner}/{repo} is:pr author:{username} created:{day_str}", headers)
    prs_merged = search_count(f"repo:{owner}/{repo} is:pr author:{username} merged:{day_str}", headers)

    # 2) User events used for triage/resolved + commits via PushEvent
    log("Fetching recent user events (triage / issue closes / push commits)...")
    events = fetch_user_events(username, headers, max_pages=3)

    issues_triaged, issues_resolved = count_triage_and_resolved_from_events(events, day)

    # 3) Commits count (FIXED) using PushEvent commits for that repo/day
    log("Fetching commits count via PushEvent (counts commits pushed by you to the repo that day)...")
    commits = count_commits_pushed_to_repo_that_day(events, owner, repo, day, headers)

    # 4) Open snapshot as-of that day
    log("Fetching open issues/PRs counts as-of target day...")
    open_issues, open_prs = count_open_counts_asof(owner, repo, day, headers)

    return {
        "issues_triaged": issues_triaged,
        "issues_resolved": issues_resolved,
        "prs_created": prs_created,
        "prs_merged": prs_merged,
        "commits": commits,
        "open_issues": open_issues,
        "open_prs": open_prs,
    }


# ---------------------------------------------------------------------------
# Excel helpers
# ---------------------------------------------------------------------------

def find_or_create_row(ws, day: dt.date) -> int:
    """
    Find an existing row whose Date column equals 'day', otherwise append a new row.

    Assumes:
        Column A is Date
        Row 1 is header
        Data starts from row 2

    Input:
        ws: openpyxl worksheet
        day: target date

    Output:
        row index (int) where data should be written.
    """
    for r in range(2, ws.max_row + 1):
        v = ws.cell(r, 1).value
        if isinstance(v, dt.datetime):
            v = v.date()
        if isinstance(v, dt.date) and v == day:
            return r

    r = ws.max_row + 1
    ws.cell(r, 1).value = day
    ws.cell(r, 1).number_format = "DD/MM/YYYY"
    return r


def validate_xlsx(path: str) -> None:
    """
    Validate workbook path before openpyxl loads it.

    Checks:
        - exists
        - is file (not directory)
        - reasonable size (> 1000 bytes)
        - is a ZIP container (xlsx is a zip)

    Input:
        path: file path

    Output:
        None (dies on failure)
    """
    if not os.path.exists(path):
        die(f"Workbook not found: {path}. Put the .xlsx in this folder or set TRACKER_XLSX.")
    if os.path.isdir(path):
        die(f"Workbook path is a directory, not a file: {path}")
    size = os.path.getsize(path)
    if size < 1000:
        die(f"Workbook file looks too small ({size} bytes): {path}. Re-download the .xlsx.")
    if not zipfile.is_zipfile(path):
        die("Workbook is not a valid .xlsx (zip) file.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Script entry point.

    Steps:
        1) parse date
        2) validate token + workbook
        3) read Config sheet (owner/repo/username)
        4) compute metrics from GitHub
        5) write to the correct date row
        6) save workbook

    Output:
        None (prints logs, writes Excel)
    """
    try:
        day = parse_args()
    except Exception as e:
        die(str(e))

    script_dir = Path(__file__).resolve().parent
    env_cfg = load_dotenv(str(script_dir / ".env"))

    token = require_cfg(env_cfg, "GITHUB_TOKEN")
    xlsx = require_cfg(env_cfg, "TRACKER_OUT")
    owner = require_cfg(env_cfg, "GITHUB_OWNER")
    repo = require_cfg(env_cfg, "GITHUB_REPO")
    username = require_cfg(env_cfg, "GITHUB_USERNAME")
    sheet_name = require_cfg(env_cfg, "TRACKER_SHEET")

    log(f"Using workbook: {os.path.abspath(xlsx)}")
    validate_xlsx(xlsx)

    log("Opening workbook...")
    try:
        wb = load_workbook(xlsx)
    except zipfile.BadZipFile:
        die(f"BadZipFile: {xlsx} is not a real .xlsx. Re-download the workbook and try again.")

    if sheet_name not in wb.sheetnames:
        die(f"Worksheet '{sheet_name}' not found in workbook. Did you run init_tracker.py?")

    # Optional: enforce init_tracker-created Config sheet exists
    if "Config" not in wb.sheetnames:
        die("Sheet 'Config' not found in workbook. Did you run init_tracker.py?")

    log(f"Target date: {day:%Y-%m-%d} | Repo: {owner}/{repo} | User: {username} | Sheet: {sheet_name}")

    headers = gh_headers(token)
    metrics = count_metrics(owner, repo, username, day, headers)

    ws = wb[sheet_name]
    row = find_or_create_row(ws, day)

    log(f"Writing metrics into row {row}...")
    # A Date
    # B Issues Triaged
    # C Issues Resolved
    # D PRs Created
    # E PRs Merged
    # F Commits
    # G Open Issues
    # H Open PRs
    ws.cell(row, 2).value = metrics["issues_triaged"]
    ws.cell(row, 3).value = metrics["issues_resolved"]
    ws.cell(row, 4).value = metrics["prs_created"]
    ws.cell(row, 5).value = metrics["prs_merged"]
    ws.cell(row, 6).value = metrics["commits"]
    ws.cell(row, 7).value = metrics["open_issues"]
    ws.cell(row, 8).value = metrics["open_prs"]

    # Update "Last Updated (UTC)" in Config
    cfg_ws = wb["Config"]
    cfg_ws["B5"].value = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M:%SZ")

    log("Saving workbook...")
    wb.save(xlsx)

    log(f"DONE. Updated {os.path.basename(xlsx)} for {day.strftime('%Y-%m-%d')}: {metrics}")


if __name__ == "__main__":
    main()
