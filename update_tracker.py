"""
GitHub -> Excel daily tracker updater (with progress logging)

Purpose
-------
Updates (or creates) a single row in your Excel tracker for a given day, filling
in GitHub-derived metrics for *your personal contributions*.

What this script updates in Excel (auto-populated)
--------------------------------------------------
- Issues Triaged:
    Unique issues in the target repo where you commented on that day.
    (Uses Issue Comments API: GET /repos/.../issues/comments, filtered by user + date)
- Issues Resolved:
    Issues you closed on that day in the target repo.
    (Uses Search API + Issue Events API to verify you were the closer)
- PRs Created:
    PRs you opened that day.
    (Uses Search API: author:USER created:DAY)
- PRs Merged:
    PRs you authored that were merged that day.
    (Uses Search API: author:USER merged:DAY)
- Commits:
    Commits you authored in the target repo that day.
    (Uses Commits API: GET /repos/.../commits?author=USER&since=&until=)
- Open Issues / Open PRs (as-of that day):
    Snapshot count approximated by summing two queries:
      (1) created<=day AND still open  (2) created<=day AND closed after day

Manual columns (not overwritten)
-------------------------------
- ADO Tests, Release, Notes

Defaults
--------
- If no date argument is provided, defaults to *today* (local machine date).

Environment requirements
------------------------
- Set GITHUB_TOKEN (GitHub PAT) in env or in a .env file loaded by your runner.
"""

import os
import sys
import time
import datetime as dt
import zipfile
from typing import Tuple, Dict, Any, List
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
        die(f".env file not found: {path}. Create a .env file in this folder (see README).")

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
        "User-Agent": "github-daily-tracker"
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

def search_count(query: str, headers: Dict[str, str]) -> int:
    """
    Run a GitHub Search API query and return total_count.

    Input:
        query: search query string, e.g. "repo:org/repo is:pr author:me created:2026-01-13"
        headers: GitHub headers

    Output:
        Integer total_count returned by GitHub.
    """
    url = f"{API}/search/issues"
    params = {"q": query, "per_page": 1}
    r = request_get(url, headers=headers, params=params)
    return int(r.json().get("total_count", 0))


def count_open_counts_asof(owner: str, repo: str, day: dt.date, headers: Dict[str, str]) -> Tuple[int, int]:
    """
    Compute open issues and open PRs snapshot "as-of end of target day".

    Logic (split into two queries to avoid undocumented boolean grouping):
        Query A: created<=day AND still open now  (lower bound — may undercount if closed later)
        Query B: created<=day AND closed AFTER day (were open on that day but closed since)
        Total = A + B

    Input:
        owner, repo: target repo
        day: date object
        headers: GitHub headers

    Output:
        (open_issues_count, open_prs_count) as integers
    """
    day_str = day.strftime("%Y-%m-%d")

    # Issues: still open + created on or before that day
    open_issues_now = search_count(
        f"repo:{owner}/{repo} is:issue is:open created:<={day_str}", headers
    )
    # Issues: closed after that day (were open on that day) + created on or before
    closed_issues_after = search_count(
        f"repo:{owner}/{repo} is:issue is:closed closed:>{day_str} created:<={day_str}", headers
    )

    # PRs: still open + created on or before that day
    open_prs_now = search_count(
        f"repo:{owner}/{repo} is:pr is:open created:<={day_str}", headers
    )
    # PRs: closed after that day + created on or before
    closed_prs_after = search_count(
        f"repo:{owner}/{repo} is:pr is:closed closed:>{day_str} created:<={day_str}", headers
    )

    return open_issues_now + closed_issues_after, open_prs_now + closed_prs_after


# ---------------------------------------------------------------------------
# GitHub metrics: Search API for triage/resolved, Commits API for commits
# ---------------------------------------------------------------------------

def count_issues_triaged(owner: str, repo: str, username: str, day: dt.date, headers: Dict[str, str]) -> int:
    """
    Count unique issues (not PRs) in the target repo where the user commented on that day.

    Uses the Issue Comments API (GET /repos/.../issues/comments?since=DAY) and
    filters by created_at within the day + user login. This is more accurate than
    Search API's commenter:USER updated:DAY which only checks the issue's last
    updated_at timestamp — that overcounts when someone else updates an issue the
    user previously commented on, and undercounts for historical dates when
    updated_at has moved past the target day.

    Input:
        owner, repo: target repository
        username: GitHub username
        day: target date
        headers: GitHub headers

    Output:
        Integer count of unique issues commented on.
    """
    day_start = dt.datetime.combine(day, dt.time.min)
    day_end = dt.datetime.combine(day + dt.timedelta(days=1), dt.time.min)
    since_str = day_start.strftime("%Y-%m-%dT%H:%M:%SZ")

    url = f"{API}/repos/{owner}/{repo}/issues/comments"
    params: Dict[str, Any] = {"since": since_str, "sort": "created", "direction": "desc", "per_page": 100}

    issue_numbers: set = set()
    page_url: str | None = url
    page_params = params

    for _ in range(10):  # max pages safety
        r = request_get(page_url, headers, params=page_params)
        comments = r.json()
        if not comments:
            break

        done = False
        for c in comments:
            created = dt.datetime.strptime(c["created_at"], "%Y-%m-%dT%H:%M:%SZ")
            if created >= day_end:
                continue  # newer than target day, skip
            if created < day_start:
                done = True  # older than target day — all subsequent are older too
                break

            if c.get("user", {}).get("login") != username:
                continue
            # Skip PR comments (html_url contains /pull/ for PRs, /issues/ for issues)
            if "/pull/" in c.get("html_url", ""):
                continue

            issue_url = c.get("issue_url", "")
            try:
                issue_numbers.add(int(issue_url.rsplit("/", 1)[-1]))
            except (ValueError, IndexError):
                pass

        if done:
            break
        if "next" in r.links:
            page_url = r.links["next"]["url"]
            page_params = None
        else:
            break

    return len(issue_numbers)


def count_issues_resolved(owner: str, repo: str, username: str, day: dt.date, headers: Dict[str, str]) -> int:
    """
    Count issues the user closed on that day in the target repo.

    Strategy:
        1. Search API finds all issues closed on that day in the repo.
        2. For each, fetch issue events to verify the user was the closer.

    This is more accurate than involves:USER which matches anyone who
    authored, commented, was assigned, or was mentioned — not just the closer.

    Input:
        owner, repo: target repository
        username: GitHub username
        day: target date
        headers: GitHub headers

    Output:
        Integer count of issues the user closed.
    """
    day_str = day.strftime("%Y-%m-%d")
    day_start = dt.datetime.combine(day, dt.time.min)
    day_end = dt.datetime.combine(day + dt.timedelta(days=1), dt.time.min)

    # Step 1: Find all issues closed on that day
    query = f"repo:{owner}/{repo} is:issue is:closed closed:{day_str}"
    url = f"{API}/search/issues"
    params: Dict[str, Any] = {"q": query, "per_page": 100}
    r = request_get(url, headers, params=params)
    items = r.json().get("items", [])

    # Step 2: For each closed issue, check who closed it
    count = 0
    for issue in items:
        number = issue["number"]
        events_url = f"{API}/repos/{owner}/{repo}/issues/{number}/events"
        ev_r = request_get(events_url, headers, params={"per_page": 100})
        events = ev_r.json()

        # Walk events in reverse to find the most recent "closed" event on that day
        for ev in reversed(events):
            if ev.get("event") != "closed":
                continue
            ev_time = dt.datetime.strptime(ev["created_at"], "%Y-%m-%dT%H:%M:%SZ")
            if day_start <= ev_time < day_end:
                if ev.get("actor", {}).get("login") == username:
                    count += 1
            break  # only check the most recent close event

    return count


def count_commits(owner: str, repo: str, username: str, day: dt.date, headers: Dict[str, str]) -> int:
    """
    Count commits authored by the user in the target repo on the given day.

    Uses the Commits API: GET /repos/{owner}/{repo}/commits?author={user}&since=&until=
    This avoids all PushEvent/compare issues (force pushes, new branches, 90-day limit).

    Input:
        owner, repo: target repository
        username: GitHub username
        day: target date
        headers: GitHub headers

    Output:
        Integer count of commits.
    """
    since = dt.datetime.combine(day, dt.time.min).strftime("%Y-%m-%dT%H:%M:%SZ")
    until = dt.datetime.combine(day + dt.timedelta(days=1), dt.time.min).strftime("%Y-%m-%dT%H:%M:%SZ")

    commits_url = f"{API}/repos/{owner}/{repo}/commits"
    params = {
        "author": username,
        "since": since,
        "until": until,
        "per_page": 100,
    }
    commits = get_all_pages(commits_url, headers, params=params, max_pages=10)
    return len(commits)


# ---------------------------------------------------------------------------
# Aggregate daily metrics
# ---------------------------------------------------------------------------

def count_metrics(owner: str, repo: str, username: str, day: dt.date, headers: Dict[str, str]) -> Dict[str, int]:
    """
    Gather all metrics needed for one date row.

    All queries are scoped to the target repo via Search API or Commits API.

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

    # 2) Issues triaged (commented on) via Search API
    log("Fetching issues triaged (commented on) via search...")
    issues_triaged = count_issues_triaged(owner, repo, username, day, headers)

    # 3) Issues resolved (closed) via Search API
    log("Fetching issues resolved (closed) via search...")
    issues_resolved = count_issues_resolved(owner, repo, username, day, headers)

    # 4) Commits via Commits API
    log("Fetching commits count via Commits API...")
    commits = count_commits(owner, repo, username, day, headers)

    # 5) Open snapshot as-of that day (two-query approach)
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
    last_data_row = 1  # header
    for r in range(2, ws.max_row + 1):
        v = ws.cell(r, 1).value
        if isinstance(v, dt.datetime):
            v = v.date()
        if isinstance(v, dt.date):
            if v == day:
                return r
            last_data_row = r

    r = last_data_row + 1
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
        die(f"Workbook not found: {path}. Put the .xlsx in this folder or set TRACKER_OUT in .env.")
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
