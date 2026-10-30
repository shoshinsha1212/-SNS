# 成果型SNS バックエンド（FastAPI + Python）

Polis のクラスタリング・合意度計算を参考にしつつ、「立場ごとの見え方の違い（立場依存度・ギャップ）」「短い原則×背景の原体験の2層構造」「成果物ドキュメントの自動編纂と貢献記録」を行う API サーバーです。

## 起動方法

```powershell
cd backend
uv run uvicorn app.main:app --reload --port 8000
```

- 初回起動時に `backend/data/seika.db`（SQLite）が自動作成され、サンプルデータ（80名の参加者・12件の原則・原体験・成果物 v1.0）が投入されます。
- 環境変数 `OPENAI_API_KEY` を設定すると LLM による変換・編纂が有効になり、未設定の場合はルール・テンプレートによる決定論的モードで動作します。

## テストの実行

```powershell
cd backend
.\.venv\Scripts\pytest.exe -v
```
