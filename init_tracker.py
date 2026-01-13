
#!/usr/bin/env python3
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

OUT = "daily_contributions_tracker_auto.xlsx"

HEADERS = [
    "Date",
    "Issues Triaged",
    "Issues Resolved",
    "PRs Created",
    "PRs Merged",
    "Commits",
    "Open Issues",
    "Open PRs",
    "ADO Tests",
    "Release",
    "Notes",
]

def style_header(ws, row=1):
    fill = PatternFill("solid", fgColor="305496")
    font = Font(bold=True, color="FFFFFF")
    align = Alignment(horizontal="center", vertical="center")
    for col, name in enumerate(HEADERS, start=1):
        c = ws.cell(row=row, column=col, value=name)
        c.fill = fill
        c.font = font
        c.alignment = align
    ws.freeze_panes = "A2"
    widths = [12, 14, 15, 12, 12, 10, 12, 10, 14, 12, 60]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

def main():
    wb = Workbook()

    ws = wb.active
    ws.title = "Ansible.Azcollection"
    style_header(ws)

    cfg = wb.create_sheet("Config")
    cfg["A1"] = "GitHub Owner"
    cfg["A2"] = "GitHub Repo"
    cfg["A3"] = "GitHub Username"
    cfg["A4"] = "Timezone"
    cfg["A5"] = "Last Updated (UTC)"
    for cell in ["A1","A2","A3","A4","A5"]:
        cfg[cell].font = Font(bold=True)
    cfg["B1"] = "ansible-collections"
    cfg["B2"] = "azure"
    cfg["B3"] = "zunyangc"
    cfg["B4"] = "Asia/Kuala_Lumpur"
    cfg.column_dimensions["A"].width = 22
    cfg.column_dimensions["B"].width = 28

    wb.save(OUT)
    print(f"Created valid workbook: {OUT}")

if __name__ == "__main__":
    main()
