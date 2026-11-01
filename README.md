# 成果型SNS

社会の議題に賛成・反対で答えると、自分が多数派か少数派か、反対側の人の理由と体験談が分かる。
3つの議題に答えると、4つの軸の「価値観マップ」が完成する。行動はすべて計測し、管理画面で漏斗として見る。

依頼書（何を確かめるためのものか）は [brief.md](brief.md)。

## 画面
| パス | 内容 |
|---|---|
| `/` | 議題一覧と価値観マップの進み具合 |
| `/t/:id` | 論点に1問ずつ答える（理由のひとこと・論点の追加） |
| `/t/:id/results` | みんなの結果、反対側の理由と体験談、理解度の1問 |
| `/map` | 価値観マップ（1議題で途中経過、3議題で完成） |
| `/new` | 議題を作る（タイトル＋論点3つから） |
| `/admin` | 管理画面：計測（漏斗・離脱位置・再訪・理解度）、通報、価値観の軸の紐づけ |

## 構成
- `backend/`：FastAPI + SQLAlchemy。`app/values.py` に価値観の軸と初期議題、`app/metrics.py` に集計。
- `frontend/`：React + Vite + TypeScript。
- 本番は `Dockerfile` で両方をまとめて Render にデプロイする。

## 環境変数
| 名前 | 用途 |
|---|---|
| `DATABASE_URL` | Postgres の接続 URL（Neon など）。未設定なら `backend/data/seika.db`（SQLite） |
| `ADMIN_KEY` | 管理画面の合言葉。未設定なら管理画面は使えない |

## 手元で動かす
```bash
cd backend && uv sync && ADMIN_KEY=local-admin uv run uvicorn app.main:app --port 8000
```
```bash
cd frontend && npm install && npm run dev
```
テスト：`cd backend && uv run pytest`
