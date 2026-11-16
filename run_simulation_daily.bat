@echo off
chcp 65001 > nul
echo =======================================================
echo   成果型SNS (Agorus) E2E シミュレーション: 日次実行
echo =======================================================
cd /d "C:\Antigravity\成果型SNS"

:: 毎日70名のペルソナを抽出し、約10時間（600分）に分散して実行
:: 1人あたり平均約8.5分間隔で活動します
python e2e_simulation.py --target http://localhost:5173 --mode daily --active-rate 70 --spread-hours 10 --channel msedge
