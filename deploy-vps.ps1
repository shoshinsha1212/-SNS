# 成果型SNS を ConoHa VPS に配る。
#
#   使い方（リポジトリの一番上で）： .\deploy-vps.ps1
#
# 手元で画面を作り、backend と frontend/dist をまとめて送り、
# /srv/seika/releases/<日時> に展開して current を付け替え、seika.service を再起動する。
# 起動確認に失敗したら、前の版に戻す。直近5版を残す。
$ErrorActionPreference = "Stop"

$Server = "root@160.251.236.158"
$Key = "$HOME\.ssh\kondate_vps"
$Root = $PSScriptRoot
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$Archive = Join-Path ([IO.Path]::GetTempPath()) "seika-$Stamp.tar.gz"

Write-Host "== 画面を作る"
Push-Location "$Root\frontend"
try { npm run build; if ($LASTEXITCODE) { throw "npm run build に失敗しました" } } finally { Pop-Location }

Write-Host "== まとめて送る"
tar -czf $Archive -C $Root backend/app backend/pyproject.toml backend/uv.lock backend/README.md frontend/dist
if ($LASTEXITCODE) { throw "tar に失敗しました" }
scp -i $Key -o BatchMode=yes $Archive "${Server}:/tmp/seika-$Stamp.tar.gz"
if ($LASTEXITCODE) { throw "scp に失敗しました" }
Remove-Item $Archive

Write-Host "== サーバーで展開して切り替える"
$remote = @"
set -eu
REL=/srv/seika/releases/$Stamp
mkdir -p `$REL
tar -xzf /tmp/seika-$Stamp.tar.gz -C `$REL
rm /tmp/seika-$Stamp.tar.gz
cd `$REL/backend
UV_PYTHON_INSTALL_DIR=/opt/uv-python uv sync --frozen --no-dev --python 3.12 --quiet
PREV=`$(readlink /srv/seika/current || true)
ln -sfn `$REL /srv/seika/current
systemctl restart seika
for i in `$(seq 1 20); do
  if curl -fs http://127.0.0.1:8001/api/meta >/dev/null; then echo "起動を確認しました: $Stamp"; break; fi
  sleep 1
  if [ `$i = 20 ]; then
    echo "起動を確認できませんでした。前の版に戻します" >&2
    [ -n "`$PREV" ] && ln -sfn "`$PREV" /srv/seika/current && systemctl restart seika
    exit 1
  fi
done
ls -1dt /srv/seika/releases/* | tail -n +6 | xargs -r rm -rf
"@
# PowerShell は標準入力に CRLF で書くので、サーバー側で \r を落としてから実行する
$remote | ssh -i $Key -o BatchMode=yes $Server "tr -d '\r' | bash -s"
if ($LASTEXITCODE) { throw "サーバー側の配備に失敗しました" }
