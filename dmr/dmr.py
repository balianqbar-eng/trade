#!/usr/bin/env python3
"""DMR - Daily Mission Record CLI

子指令：
    init                  建立 Google Sheet（首次執行）
    log                   寫入一筆 DMR（CSV + Sheet 雙寫）
    list-pending          列出待確認項目
    mark-done <row_id>    標記某筆已完成驗證
"""

import argparse
import csv
import json
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

BASE_DIR = Path("/Users/balianwang/Downloads/balian/dmr")
CSV_PATH = Path("/Users/balianwang/Downloads/balian/工作記錄.csv")
CONFIG_PATH = BASE_DIR / ".dmr_config.json"
TOKEN_PATH = BASE_DIR / "token_dmr.json"
CLIENT_SECRETS = Path(
    "/Users/balianwang/Downloads/balian/video2slides/credentials/google_oauth.json"
)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

COLUMNS = [
    "row_id",
    "start_time",
    "end_time",
    "duration_min",
    "project",
    "summary",
    "progress",
    "status",
    "needs_confirm",
    "notes",
]


def get_credentials():
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRETS), SCOPES
            )
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json())
    return creds


def load_config():
    if not CONFIG_PATH.exists():
        return {}
    return json.loads(CONFIG_PATH.read_text())


def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2))


def sheets_client():
    return build("sheets", "v4", credentials=get_credentials())


def cmd_init(args):
    cfg = load_config()
    if cfg.get("spreadsheet_id"):
        print(f"已存在 Sheet：{cfg.get('spreadsheet_url')}")
        return
    svc = sheets_client()
    body = {
        "properties": {"title": "工作記錄 DMR"},
        "sheets": [{"properties": {"title": "records"}}],
    }
    result = svc.spreadsheets().create(body=body).execute()
    sheet_id = result["spreadsheetId"]
    url = result["spreadsheetUrl"]
    svc.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range="records!A1",
        valueInputOption="RAW",
        body={"values": [COLUMNS]},
    ).execute()
    cfg["spreadsheet_id"] = sheet_id
    cfg["spreadsheet_url"] = url
    save_config(cfg)
    print(f"Sheet 建立完成：{url}")


def next_row_id():
    if not CSV_PATH.exists():
        return 1
    with CSV_PATH.open(encoding="utf-8") as f:
        return sum(1 for _ in csv.DictReader(f)) + 1


def append_csv(row):
    new_file = not CSV_PATH.exists()
    with CSV_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        if new_file:
            writer.writeheader()
        writer.writerow(row)


def append_sheet(row, sheet_id):
    svc = sheets_client()
    values = [[str(row[c]) for c in COLUMNS]]
    svc.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range="records!A:J",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": values},
    ).execute()


def cmd_log(args):
    cfg = load_config()
    sheet_id = cfg.get("spreadsheet_id")
    if not sheet_id:
        print("錯誤：尚未 init，請先 `python dmr.py init`", file=sys.stderr)
        sys.exit(1)
    row = {
        "row_id": next_row_id(),
        "start_time": args.start,
        "end_time": args.end,
        "duration_min": args.duration,
        "project": args.project,
        "summary": args.summary,
        "progress": args.progress,
        "status": args.status,
        "needs_confirm": args.needs_confirm,
        "notes": args.notes,
    }
    append_csv(row)
    append_sheet(row, sheet_id)
    print(f"已寫入 row_id={row['row_id']}（CSV + Sheet）")


def read_csv_rows():
    if not CSV_PATH.exists():
        return []
    with CSV_PATH.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def cmd_list_pending(args):
    rows = [r for r in read_csv_rows() if r["needs_confirm"] == "Y"]
    if not rows:
        print("無待確認項目")
        return
    for r in rows:
        print(
            f"#{r['row_id']} [{r['end_time']}] {r['project']} - {r['summary']} "
            f"({r['progress']})"
        )


def cmd_mark_done(args):
    rows = read_csv_rows()
    target = None
    for r in rows:
        if r["row_id"] == str(args.row_id):
            r["status"] = "completed"
            r["needs_confirm"] = "N"
            if args.notes:
                r["notes"] = (r["notes"] + " | " if r["notes"] else "") + args.notes
            target = r
            break
    if not target:
        print(f"找不到 row_id={args.row_id}", file=sys.stderr)
        sys.exit(1)
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    cfg = load_config()
    sheet_id = cfg.get("spreadsheet_id")
    if sheet_id:
        svc = sheets_client()
        result = (
            svc.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range="records!A:J")
            .execute()
        )
        for i, sr in enumerate(result.get("values", [])):
            if sr and sr[0] == str(args.row_id):
                svc.spreadsheets().values().update(
                    spreadsheetId=sheet_id,
                    range=f"records!A{i+1}:J{i+1}",
                    valueInputOption="RAW",
                    body={"values": [[str(target.get(c, "")) for c in COLUMNS]]},
                ).execute()
                break
    print(f"#{args.row_id} 已標記完成")


def main():
    p = argparse.ArgumentParser(prog="dmr")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="建立 Google Sheet")

    log_p = sub.add_parser("log", help="新增一筆 DMR")
    log_p.add_argument("--start", required=True, help="YYYY-MM-DD HH:MM")
    log_p.add_argument("--end", required=True, help="YYYY-MM-DD HH:MM")
    log_p.add_argument("--duration", type=int, required=True)
    log_p.add_argument("--project", required=True)
    log_p.add_argument("--summary", required=True)
    log_p.add_argument("--progress", default="")
    log_p.add_argument(
        "--status",
        choices=["completed", "pending_confirm", "blocked"],
        required=True,
    )
    log_p.add_argument(
        "--needs-confirm",
        choices=["Y", "N"],
        required=True,
        dest="needs_confirm",
    )
    log_p.add_argument("--notes", default="")

    sub.add_parser("list-pending", help="列出待確認項目")

    done_p = sub.add_parser("mark-done", help="標記某筆已完成")
    done_p.add_argument("row_id", type=int)
    done_p.add_argument("--notes", default="")

    args = p.parse_args()
    {
        "init": cmd_init,
        "log": cmd_log,
        "list-pending": cmd_list_pending,
        "mark-done": cmd_mark_done,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
