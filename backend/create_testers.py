"""テスターに配る参加者をまとめて作り、配布用 URL の一覧（CSV）を書き出す。

    使い方（backend で）： uv run python create_testers.py --count 100 [--base-url https://example.com]

接続先は DATABASE_URL（無ければ手元の SQLite）。CSV にはトークンが入るので、git には入れない。
"""

import argparse
import csv
import secrets
from datetime import datetime
from pathlib import Path

from app.db import SessionLocal, init_db
from app.models import User


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default="", help="サービスの公開 URL（例 https://example.com）。省くと URL 列は空")
    p.add_argument("--count", type=int, default=100)
    p.add_argument("--out", type=Path, default=Path(__file__).resolve().parent.parent / "testers")
    args = p.parse_args()

    init_db()
    base = args.base_url.rstrip("/")
    with SessionLocal() as db:
        users = [User(token=secrets.token_urlsafe(32)) for _ in range(args.count)]
        db.add_all(users)
        db.commit()
        rows = [(i, u.id, u.token, f"{base}/?t={u.token}" if base else "") for i, u in enumerate(users, 1)]

    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"testers-{datetime.now():%Y%m%d-%H%M%S}.csv"
    # Excel で文字化けしないよう BOM 付き
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["番号", "ユーザーID", "トークン", "配布用URL"])
        w.writerows(rows)
    print(f"{len(rows)} 人作りました（ユーザーID {rows[0][1]}〜{rows[-1][1]}）: {path}")


if __name__ == "__main__":
    main()
