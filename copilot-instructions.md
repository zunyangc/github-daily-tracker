# Daily GH Tracker — Copilot Instructions

## Command Alias

When user types `runghtracker` or `/runghtracker`, execute the full daily gh tracker workflow.

## Tracker Script
```bash
cd ~/github-daily-tracker && source venv/bin/activate && python update_tracker.py
```

If a specific date is provided, pass it as an argument in DD/MM/YYYY format:
```
python update_tracker.py 10/4/2026
```

## Full Workflow
1. Run tracker script → display metrics table (Issues Triaged, Issues Resolved, PRs Created, PRs Merged, Commits, Open Issues, Open PRs).
2. Fetch GitHub activity for the target day via gh CLI (repo: <repository name>, user: <github username>): 
- PRs created
- PRs merged
- Issues closed
- Issues triaged (commented on)
- PRs currently working on
- Display as a details table.
3. Ask user permission before writing to the Notes column. Never auto-write.
4. User reviews and may add/modify information.
5. Write to Notes column (column J) in the Excel workbook.

Excel Details
- Workbook path: <path-to-excel-workbook)
- Sheet: <sheetname>
- Notes column: J (index 10)
- Library: openpyxl

Notes Format

Completed #<PRID>, Closed #<PR/IssueID>, Working on #<PRID>

Examples:

- Completed #2216, Closed #1234, Working on #2215
- Working on #2216, Working on #2215, Working on #2210
