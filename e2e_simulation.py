"""成果型SNS (Agorus) E2E ブラウザ自動操作シミュレーション

Playwright を用いて、18〜25歳のペルソナが実際にブラウザ画面（localhost:5173）を開き、
ボタンクリックや理由の入力をシミュレートするスクリプト。

主な機能:
- 100名のペルソナ定義（personas_100.json）に基づいた意思決定
- 1日あたり約70%（70名）のペルソナをランダムに抽出し活動
- 時間をばらして実行する分散実行モード（--mode daily）
- 動作確認のための高速テストモード（--mode test）
- プロフィール入力（年齢層・学生）、議題の選択、論点ごとの賛否・理由入力、理解度評価までをE2Eで完走
"""

import argparse
import datetime
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error

# Windows コンソールのエンコーディング対策
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# プロジェクトルート
ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
PERSONAS_FILE = ROOT_DIR / "testers" / "personas_100.json"
TOPICS_POOL_FILE = ROOT_DIR / "testers" / "topics_pool_22.json"
TOPICS_EXTENDED_FILE = ROOT_DIR / "testers" / "topics_extended.json"
LOG_FILE = ROOT_DIR / "simulation.log"


def log(msg: str):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    print(formatted)
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(formatted + "\n")
    except Exception:
        pass


def is_server_listening(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as res:
            return res.status in (200, 304, 404)
    except urllib.error.HTTPError as e:
        return True
    except Exception:
        return False


def ensure_dev_servers_running(target_url: str):
    """ローカルサーバーが起動していない場合、バックエンドとフロントエンドを起動する"""
    if "localhost" not in target_url and "127.0.0.1" not in target_url:
        return None, None

    backend_ok = is_server_listening("http://localhost:8000/api/meta")
    frontend_ok = is_server_listening(target_url)

    proc_backend = None
    proc_frontend = None

    if not backend_ok:
        log("バックエンドサーバー (port 8000) をバックグラウンド起動しています...")
        cmd_backend = ["uv", "run", "uvicorn", "app.main:app", "--port", "8000"]
        proc_backend = subprocess.Popen(
            cmd_backend,
            cwd=str(BACKEND_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=True
        )

    if not frontend_ok:
        log("フロントエンドサーバー (Vite, port 5173) をバックグラウンド起動しています...")
        cmd_frontend = ["npm", "run", "dev"]
        proc_frontend = subprocess.Popen(
            cmd_frontend,
            cwd=str(FRONTEND_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=True
        )

    # 起動待機（最大15秒）
    start_time = time.time()
    while time.time() - start_time < 15:
        if is_server_listening(target_url):
            log(f"開発サーバーが正常に応答しています: {target_url}")
            return proc_backend, proc_frontend
        time.sleep(1.0)

    log(f"警告: {target_url} への接続確認がタイムアウトしました。処理を続行します。")
    return proc_backend, proc_frontend


def load_personas() -> List[Dict[str, Any]]:
    if not PERSONAS_FILE.exists():
        log(f"エラー: ペルソナ定義ファイルが見つかりません: {PERSONAS_FILE}")
        sys.exit(1)
    with PERSONAS_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_topic_pool() -> List[Dict[str, Any]]:
    """追加議題プール（22個の初期プール + 拡張プール）を統合ロード"""
    all_topics = []
    seen_titles = set()

    # 1. 22個の初期プール
    if TOPICS_POOL_FILE.exists():
        try:
            with TOPICS_POOL_FILE.open("r", encoding="utf-8") as f:
                for t in json.load(f):
                    if t["title"] not in seen_titles:
                        all_topics.append(t)
                        seen_titles.add(t["title"])
        except Exception as e:
            log(f"初期プール読み込みエラー: {e}")

    # 2. 拡張プール
    if TOPICS_EXTENDED_FILE.exists():
        try:
            with TOPICS_EXTENDED_FILE.open("r", encoding="utf-8") as f:
                for t in json.load(f):
                    if t["title"] not in seen_titles:
                        all_topics.append(t)
                        seen_titles.add(t["title"])
        except Exception as e:
            log(f"拡張プール読み込みエラー: {e}")

    return all_topics


def get_existing_topic_titles(base_url: str) -> set[str]:
    """現在登録されている議題のタイトル一覧を取得（ローカルDB + APIの両方から安全に確認）"""
    titles = set()

    # 1. ローカル SQLite DB から直接取得（存在する場合）
    local_db_path = BACKEND_DIR / "data" / "seika.db"
    if local_db_path.exists():
        try:
            import sqlite3
            with sqlite3.connect(str(local_db_path)) as con:
                cur = con.cursor()
                for (t_title,) in cur.execute("SELECT title FROM topics").fetchall():
                    titles.add(t_title)
        except Exception:
            pass

    # 2. API エンドポイントからの取得
    api_url = base_url.rstrip("/") + "/api/topics"
    for _ in range(3):
        try:
            req = urllib.request.Request(api_url, headers={"User-Agent": "AgorusE2ESimulator"})
            with urllib.request.urlopen(req, timeout=5) as res:
                topics = json.loads(res.read().decode("utf-8"))
                for t in topics:
                    titles.add(t["title"])
                break
        except Exception:
            time.sleep(1.0)

    return titles


def get_unregistered_topics(base_url: str) -> List[Dict[str, Any]]:
    """まだ登録されていないプール内の議題リストを返す"""
    existing_titles = get_existing_topic_titles(base_url)
    pool = load_topic_pool()
    unregistered = [t for t in pool if t["title"] not in existing_titles]
    return unregistered


def create_topic_via_api(base_url: str, persona: Dict[str, Any], topic_data: Dict[str, Any]) -> Optional[int]:
    """API経由で新規議題を投稿する（フォールバック用）"""
    api_url = base_url.rstrip("/") + "/api/topics"
    payload = {
        "title": topic_data["title"],
        "description": topic_data.get("description", ""),
        "statements": [
            {
                "body": s["body"],
                "axis_key": s.get("axis_key"),
                "direction": s.get("direction")
            }
            for s in topic_data.get("statements", [])
        ]
    }
    try:
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            api_url,
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {persona['token']}",
                "User-Agent": "AgorusE2ESimulator"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as res:
            res_data = json.loads(res.read().decode("utf-8"))
            return res_data.get("id")
    except Exception as e:
        log(f"API経由での議題作成に失敗しました [{topic_data['title']}]: {e}")
        return None


def create_topic_via_browser(page, persona: Dict[str, Any], topic_data: Dict[str, Any], target_url: str) -> bool:
    """ペルソナがブラウザ画面 (/topics/new) から新規議題をフォーム入力・作成する"""
    title = topic_data["title"]
    desc = topic_data.get("description", "")
    statements = topic_data.get("statements", [])

    log(f"  ★ [{persona['name']}] が新しい議題「{title}」の新規作成を開始します")

    try:
        new_topic_url = f"{target_url.rstrip('/')}/new"
        page.goto(new_topic_url, wait_until="domcontentloaded")
        time.sleep(1.0)

        # タイトル入力
        title_input = page.locator("label:has-text('タイトル') input")
        title_input.wait_for(timeout=5000)
        title_input.fill(title)
        time.sleep(0.3)

        # 説明文入力
        if desc:
            desc_area = page.locator("label:has-text('説明') textarea")
            if desc_area.is_visible():
                desc_area.fill(desc)
                time.sleep(0.3)

        # 論点の入力（3つ目までは初期表示、4つ目以降はボタンで追加）
        for idx, stmt in enumerate(statements):
            # 4つ目以降はカードを増やす
            if idx >= 3:
                add_stmt_btn = page.locator("button:has-text('＋ 論点を増やす')")
                if add_stmt_btn.is_visible(timeout=2000):
                    add_stmt_btn.click()
                    time.sleep(0.3)

            # 対象の論点カードを取得
            card = page.locator(".card").nth(idx + 1)  # 0番目はタイトル/説明のカード
            if card.is_visible(timeout=3000):
                # 本文入力
                textarea = card.locator("textarea")
                textarea.fill(stmt["body"])
                time.sleep(0.2)

                # 価値観の軸（任意）を設定
                axis_key = stmt.get("axis_key")
                direction = stmt.get("direction")
                if axis_key and direction:
                    try:
                        summary = card.locator("details summary")
                        if summary.is_visible():
                            summary.click()
                            time.sleep(0.2)

                        axis_select = card.locator("select[aria-label='価値観の軸']")
                        if axis_select.is_visible(timeout=1000):
                            axis_select.select_option(value=axis_key)
                            time.sleep(0.2)

                        dir_select = card.locator("select[aria-label='賛成するとどちら寄りか']")
                        if dir_select.is_visible(timeout=1000):
                            dir_select.select_option(value=str(direction))
                            time.sleep(0.2)
                    except Exception:
                        pass

        # 「議題を公開する」ボタンをクリック
        submit_btn = page.locator("button:has-text('議題を公開する')")
        submit_btn.wait_for(timeout=3000)
        time.sleep(0.5)

        # ボタンが押せる状態になるのを待機
        for _ in range(10):
            if submit_btn.is_enabled():
                break
            time.sleep(0.5)

        submit_btn.click()

        # URLが /t/... に遷移するまで最大8秒待機
        try:
            page.wait_for_url("**/t/*", timeout=8000)
        except Exception:
            pass

        # 作成成功の確認（URLが /t/... に遷移したか）
        if "/t/" in page.url:
            log(f"  ✔ [{persona['name']}] による新議題「{title}」の作成・公開に成功しました！(URL: {page.url})")
            return True
        else:
            log(f"  警告: 議題作成後のURL遷移が確認できませんでした (URL: {page.url})。APIで補完を試みます。")
            created_id = create_topic_via_api(target_url, persona, topic_data)
            return created_id is not None
    except Exception as e:
        log(f"  ブラウザ経由の議題作成中に例外が発生しました: {e}。APIでフォールバック作成します。")
        created_id = create_topic_via_api(target_url, persona, topic_data)
        if created_id:
            log(f"  ✔ API経由で新議題「{title}」を作成しました (ID: {created_id})")
            return True
        return False


def get_statement_meta_from_api(base_url: str) -> Dict[str, Any]:
    """バックエンドAPIから議題と論点のメタ情報を取得（存在すれば）"""
    api_url = base_url.rstrip("/") + "/api/topics"
    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": "AgorusE2ESimulator"})
        with urllib.request.urlopen(req, timeout=5) as res:
            return json.loads(res.read().decode("utf-8"))
    except Exception:
        return []


def decide_vote(statement_text: str, persona: Dict[str, Any]) -> tuple[int, Optional[str]]:
    """論点の文面とペルソナの価値観から賛否（1, -1, 0）と理由を決定する"""
    axes = persona["axes"]
    text = statement_text

    # ルールベース＋価値観スコアによる判定
    vote = 0
    reason = None

    # 各論点のキーワードと軸の対応
    score = 0.0
    matched = False

    # 1. 自由と秩序 (liberty)
    if any(k in text for k in ["無償", "選択", "自由", "話し合い", "認める", "学生一人ひとりの判断", "匿名"]):
        score += axes.get("liberty", 0.0) * 0.8
        matched = True
    if any(k in text for k in ["禁止", "規制", "義務", "罰する", "基準を厳しく", "判定するツール"]):
        score -= axes.get("liberty", 0.0) * 0.8
        matched = True

    # 2. 変化と安定 (change)
    if any(k in text for k in ["変える", "AI", "週休3日", "転職", "新しい", "作り直す", "外国人"]):
        score += axes.get("change", 0.0) * 0.8
        matched = True
    if any(k in text for k in ["守る", "一体感", "通称使用", "終身雇用", "慣れた"]):
        score -= axes.get("change", 0.0) * 0.8
        matched = True

    # 3. 連帯と自立 (solidarity)
    if any(k in text for k in ["社会全体", "国の負担", "支援", "無料で提供", "差はもっと小さく", "全員に配る"]):
        score += axes.get("solidarity", 0.0) * 0.9
        matched = True
    if any(k in text for k in ["自己責任", "本人や家庭が負担", "成果で給料"]):
        score -= axes.get("solidarity", 0.0) * 0.9
        matched = True

    # 4. 未来と今 (future)
    if any(k in text for k in ["将来", "若い世代", "増税", "投資", "若いうちは多少きつくても"]):
        score += axes.get("future", 0.0) * 0.8
        matched = True

    # ランダムな揺らぎ（個人の気分や迷い）
    score += random.uniform(-0.25, 0.25)

    if score > 0.15:
        vote = 1
    elif score < -0.15:
        vote = -1
    else:
        # 迷いやすい論点ではパスまたは微小な偏り
        vote = random.choice([1, -1, 0])

    # 理由を記入するかどうか判定
    if vote != 0 and random.random() < persona.get("reason_prob", 0.35):
        sample_pool = persona.get("sample_reasons", {}).get("agree" if vote == 1 else "disagree", [])
        if sample_pool:
            reason = random.choice(sample_pool)
            # ペルソナの背景に応じたプレフィックスを付ける場合がある
            if random.random() < 0.4:
                prefix = f"{persona['field']}の視点から、" if len(persona.get('field', '')) <= 6 else ""
                if prefix and len(prefix + reason) <= 80:
                    reason = prefix + reason

    return vote, reason


def simulate_persona_session(
    page,
    persona: Dict[str, Any],
    target_url: str,
    max_topics: int = 1,
    delay_factor: float = 1.0,
    topic_to_create: Optional[Dict[str, Any]] = None,
):
    """1人のペルソナによるブラウザ操作フロー"""
    p_name = persona["name"]
    p_age = persona["age"]
    p_occ = persona["occupation"]
    token = persona["token"]

    def human_sleep(min_sec: float, max_sec: float):
        sec = random.uniform(min_sec, max_sec) * delay_factor
        time.sleep(sec)

    log(f"> [{persona['id']:03d}] {p_name} ({p_age}歳 / {p_occ}) のセッション開始")

    # 1. テスタートークン付きURLでアクセス
    user_url = f"{target_url.rstrip('/')}/?t={token}"
    page.goto(user_url, wait_until="domcontentloaded")
    human_sleep(1.0, 2.0)

    # 2. プロフィール初期設定（初回のみ表示される）
    try:
        profile_card = page.locator("text=はじめに（任意）")
        if profile_card.is_visible(timeout=2000):
            log(f"  └─ 初回プロフィール入力画面を検出")
            # 年齢層の選択
            age_select = page.locator("label:has-text('年齢層') select")
            if age_select.is_visible():
                age_select.select_option(value=persona["age_band"])
                human_sleep(0.3, 0.7)

            # 大学生かどうかのラジオボタン
            if persona["is_student"]:
                student_radio = page.locator("label:has-text('はい') input[type='radio']")
            else:
                student_radio = page.locator("label:has-text('いいえ') input[type='radio']")

            if student_radio.is_visible():
                student_radio.check(force=True)
                human_sleep(0.3, 0.7)

            # 「この内容で始める」ボタンをクリック
            start_btn = page.locator("button:has-text('この内容で始める')")
            if start_btn.is_visible():
                start_btn.click()
                human_sleep(1.0, 1.5)
                log(f"  └─ プロフィール登録完了 (年齢: {persona['age_band']}, 学生: {persona['is_student']})")
    except Exception as e:
        # プロフィール入力が既に済んでいるかスキップされた場合
        pass

    # 2.5 新しい議題の作成・投稿（担当割り当てがある場合）
    if topic_to_create:
        create_ok = create_topic_via_browser(page, persona, topic_to_create, target_url)
        human_sleep(1.5, 2.5)

    # 3. 議題を選択して回答
    topics_completed = 0
    while topics_completed < max_topics:
        # トップページに戻る
        page.goto(target_url, wait_until="domcontentloaded")
        human_sleep(1.0, 1.5)

        # 未完了の議題カードを探す
        topic_cards = page.locator(".topic-card").all()
        if not topic_cards:
            log("  └─ 議題カードが見つかりませんでした。")
            break

        # 「答える」または「続きから」のカードを探す
        target_card = None
        for card in topic_cards:
            btn_text = card.locator(".btn").inner_text()
            if "答える" in btn_text or "続きから" in btn_text:
                target_card = card
                break

        # すべて回答済みなら最初のカードで結果を見るか終了
        if not target_card:
            log("  └─ 回答可能な未完了の議題がすべて完了しています。")
            break

        topic_title = target_card.locator("h3").inner_text()
        log(f"  └─ 議題「{topic_title}」を選択")
        target_card.click()
        human_sleep(1.2, 2.0)

        # 4. 論点への回答ループ
        stmt_count = 0
        while True:
            human_sleep(0.5, 1.0)

            # 結果画面に到達したか確認
            if "/results" in page.url:
                log(f"  └─ 議題「{topic_title}」の全論点に回答完了！結果画面へ遷移しました。")
                break

            # プロフィール入力（はじめに（任意））がこの画面で出た場合
            try:
                profile_heading = page.locator("h2:has-text('はじめに（任意）')")
                if profile_heading.is_visible(timeout=1500):
                    log(f"  └─ 初回プロフィール入力画面を検出")
                    age_select = page.locator("label:has-text('年齢層') select")
                    if age_select.is_visible(timeout=1000):
                        age_select.select_option(value=persona["age_band"])
                        human_sleep(0.3, 0.6)

                    student_label = "はい" if persona["is_student"] else "いいえ"
                    student_radio = page.locator(f"label:has-text('{student_label}') input[type='radio']")
                    if student_radio.is_visible(timeout=1000):
                        student_radio.check(force=True)
                        human_sleep(0.3, 0.6)

                    start_btn = page.locator("button:has-text('この内容で始める')")
                    if start_btn.is_visible(timeout=1000):
                        start_btn.click()
                        human_sleep(1.0, 1.5)
                        log(f"  └─ プロフィール登録完了 (年齢: {persona['age_band']}, 学生: {persona['is_student']})")
            except Exception:
                pass

            # 論点カードを探す
            stmt_card = page.locator(".statement-card")
            if not stmt_card.is_visible(timeout=4000):
                # 既に完了しているか画面遷移中の可能性
                human_sleep(1.0, 1.5)
                if "/results" in page.url:
                    log(f"  └─ 結果画面へ遷移しました。")
                    break
                else:
                    log(f"  └─ 論点カードが見つからず終了します (URL: {page.url})")
                    break

            stmt_count += 1
            stmt_text = page.locator(".statement-body").inner_text()
            vote, reason = decide_vote(stmt_text, persona)

            vote_label = "【賛成】" if vote == 1 else "【反対】" if vote == -1 else "【わからない】"
            log(f"    問{stmt_count}: 「{stmt_text[:35]}...」 => {vote_label}")

            # 理由を記入する場合
            if reason:
                try:
                    show_reason_btn = page.locator("button:has-text('＋ 理由をひとこと添える')")
                    if show_reason_btn.is_visible(timeout=1000):
                        show_reason_btn.click()
                        human_sleep(0.3, 0.6)

                    reason_input = page.locator("input#reason")
                    if reason_input.is_visible(timeout=1000):
                        # 人間らしいキーストロークのシミュレーション
                        reason_input.fill(reason)
                        human_sleep(0.4, 0.8)
                        log(f"      └─ 理由入力: 「{reason}」")
                except Exception:
                    pass

            # 投票ボタンをクリック
            if vote == 1:
                page.locator("button.btn.vote.agree").click()
            elif vote == -1:
                page.locator("button.btn.vote.disagree").click()
            else:
                page.locator("button.btn.vote.pass").click()

            human_sleep(0.8, 1.8)

        # 5. 結果画面で理解度評価
        if "/results" in page.url:
            human_sleep(1.0, 2.0)
            try:
                # 最後の理解度スコア (1〜5)
                score = min(5, max(1, persona.get("base_understanding", 4) + random.choice([-1, 0, 1])))
                score_btn = page.locator(f".scale button:has-text('{score}')")
                if score_btn.is_visible(timeout=2000):
                    score_btn.click()
                    human_sleep(0.5, 1.0)
                    log(f"  └─ 理解度を評価しました: {score} / 5")
            except Exception:
                pass

        topics_completed += 1

    # 6. 価値観マップ画面を閲覧
    try:
        page.goto(f"{target_url.rstrip('/')}/map", wait_until="domcontentloaded")
        human_sleep(1.0, 1.5)
        log(f"  └─ 価値観マップを確認しました。")
    except Exception:
        pass

    log(f"[OK] [{persona['id']:03d}] {p_name} のアクティビティ完了\n")


def seed_all_pool_topics(target_url: str, personas: List[Dict[str, Any]]) -> int:
    """未登録の議題プール（22個）をすべてAPI経由で一括作成する"""
    unregistered = get_unregistered_topics(target_url)
    if not unregistered:
        log("✔ プール内の議題（22個）はすべて登録済みです。追加の必要はありません。")
        return 0

    log(f"=== 未登録の議題 {len(unregistered)} 件の一括投入を開始します ===")
    created_count = 0
    for idx, topic_data in enumerate(unregistered):
        persona = personas[idx % len(personas)]
        created_id = create_topic_via_api(target_url, persona, topic_data)
        if created_id:
            log(f"  [{idx+1}/{len(unregistered)}] 作成成功 (ID: {created_id}): 「{topic_data['title']}」 by {persona['name']}")
            created_count += 1
        time.sleep(0.3)
    log(f"=== 一括投入完了: {created_count} / {len(unregistered)} 件作成成功 ===\n")
    return created_count


def run_simulation(args):
    # 開発サーバーの起動確認
    proc_b, proc_f = ensure_dev_servers_running(args.target)

    # 2〜4日ごとの回答者自律成長（5〜10名増加）チェック
    try:
        from testers.persona_growth import check_and_grow_respondents, load_growth_state
        newly_joined = check_and_grow_respondents(target_url=args.target, force=args.grow_now)
        if newly_joined:
            log(f"🎉 【コミュニティ成長】2〜4日サイクルにより、新しく {len(newly_joined)} 名の回答者が合流しました！")
        else:
            state = load_growth_state()
            log(f"回答者成長ステータス: 前回追加 {state.get('last_growth_date')} / 次回追加まで残り約 {state.get('next_interval_days')} 日間隔")
    except Exception as e:
        newly_joined = []
        log(f"回答者成長チェックのスキップ: {e}")

    personas = load_personas()
    log(f"=== Agorus E2E シミュレーション開始 (モード: {args.mode}) ===")
    log(f"対象URL: {args.target} (登録回答者総数: {len(personas)} 名)")

    # 一括シードモードが指定された場合
    if args.seed_all_topics:
        seed_all_pool_topics(args.target, personas)
        if args.mode == "test" and args.count == 0:
            log("一括投入が完了したため終了します。")
            return

    # 未登録の追加議題プールの確認
    unregistered_topics = get_unregistered_topics(args.target)
    log(f"利用可能な未登録議題プール: {len(unregistered_topics)} 件 (初期22件 + 拡張プール)")

    # 参加ペルソナの選定
    if args.mode == "test":
        count = args.count if args.count > 0 else 2
        active_personas = personas[:count]
        delay_factor = 0.5  # 高速テスト
        spread_seconds = 0
        log(f"テストモード: 最初の {len(active_personas)} 名で即時実行します。")
    elif args.mode == "single":
        p_id = args.user_id if args.user_id > 0 else 1
        active_personas = [p for p in personas if p["id"] == p_id]
        delay_factor = 1.0
        spread_seconds = 0
        log(f"単一実行モード: ID {p_id} のペルソナを実行します。")
    else:  # daily モード (毎日約70%活動)
        target_count = int(len(personas) * (args.active_rate / 100.0))
        # 本日新しく参加した回答者は優先的に活動メンバーに含める
        new_ids = {p["id"] for p in newly_joined}
        veteran_pool = [p for p in personas if p["id"] not in new_ids]
        sampled_veterans = random.sample(veteran_pool, min(len(veteran_pool), max(0, target_count - len(newly_joined))))
        active_personas = newly_joined + sampled_veterans
        random.shuffle(active_personas)

        delay_factor = 1.0
        spread_seconds = args.spread_hours * 3600
        log(f"日次モード: {len(personas)}名中 {len(active_personas)}名 (約{args.active_rate}%) を抽出しました。")
        if spread_seconds > 0:
            interval_sec = spread_seconds / len(active_personas)
            log(f"時間分散: {args.spread_hours} 時間にわたって実行します（ペルソナ間の平均待機時間: 約 {interval_sec/60:.1f} 分）。")

    # 議題作成の上限設定（未指定なら上限なし: None）
    create_limit = args.create_topics
    if create_limit is None:
        log("議題作成の上限: 【上限なし】各ペルソナが自発的に好きなように新しい議題を追加します。")
    else:
        log(f"議題作成の上限: 最大 {create_limit} 件まで")

    created_topics_count = 0

    # Playwright の起動
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        channel = args.channel
        headless = not args.headed

        browser = p.chromium.launch(headless=headless, channel=channel)
        log(f"ブラウザ起動完了 (Channel: {channel}, Headless: {headless})")

        total = len(active_personas)
        for i, persona in enumerate(active_personas, 1):
            log(f"--- 進行度: {i} / {total} ({(i/total)*100:.1f}%) ---")

            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 AgorusTester"
            )
            page = context.new_page()

            # ペルソナが自発的に新しい議題を作成するか判定（上限なし・各々好きなように追加）
            topic_to_create = None
            if create_limit is None or created_topics_count < create_limit:
                current_unregistered = get_unregistered_topics(args.target)
                if current_unregistered:
                    # ペルソナが議題を自発提起する確率 (日次: 約35%、テスト: 60%)
                    topic_prob = 0.60 if args.mode == "test" else 0.35
                    if random.random() < topic_prob:
                        topic_to_create = random.choice(current_unregistered)
                        created_topics_count += 1
                        log(f"💡 [{persona['name']}] が自発的に新しい議題「{topic_to_create['title']}」の提起を決定しました！（本日作成累計: {created_topics_count}件）")

            try:
                simulate_persona_session(
                    page=page,
                    persona=persona,
                    target_url=args.target,
                    max_topics=args.topics_per_user,
                    delay_factor=delay_factor,
                    topic_to_create=topic_to_create,
                )
            except Exception as e:
                log(f"エラー発生 [{persona['name']}]: {e}")
            finally:
                context.close()

            # 次のペルソナまでの待機時間
            if i < total:
                if spread_seconds > 0:
                    base_interval = spread_seconds / total
                    sleep_time = random.uniform(base_interval * 0.7, base_interval * 1.3)
                    log(f"次のペルソナまで {sleep_time/60:.1f} 分間待機します...")
                    time.sleep(sleep_time)
                else:
                    time.sleep(random.uniform(1.0, 2.5))

        browser.close()

    log(f"=== シミュレーション終了 (本日新規作成された議題: {created_topics_count}件) ===")


def main():
    parser = argparse.ArgumentParser(description="成果型SNS E2E ペルソナシミュレーター")
    parser.add_argument("--target", default="http://localhost:5173", help="対象URL (既定: http://localhost:5173)")
    parser.add_argument("--mode", choices=["daily", "test", "single"], default="daily", help="実行モード (daily: 70名分散, test: 少数即時, single: 1名)")
    parser.add_argument("--active-rate", type=float, default=70.0, help="日次活動率(%%, 既定: 70)")
    parser.add_argument("--count", type=int, default=2, help="testモード時の実行人数 (既定: 2)")
    parser.add_argument("--user-id", type=int, default=1, help="singleモード時のペルソナID (1〜100)")
    parser.add_argument("--topics-per-user", type=int, default=1, help="1人あたり回答する議題数 (既定: 1)")
    parser.add_argument("--create-topics", type=int, default=None, help="本セッションでペルソナが新規投稿する最大議題数 (既定: なし=上限を設定せず各々自発的に追加)")
    parser.add_argument("--grow-now", action="store_true", help="間隔日数を待たずに今すぐ新規回答者（5〜10名）を追加する")
    parser.add_argument("--seed-all-topics", action="store_true", help="22個の追加議題プールを今すぐAPIで一括作成する")
    parser.add_argument("--spread-hours", type=float, default=0.0, help="分散時間（時間単位。0なら即時連続実行）")
    parser.add_argument("--headed", action="store_true", help="ブラウザ画面を表示して実行する")
    parser.add_argument("--channel", default="msedge", choices=["msedge", "chrome", "chromium"], help="ブラウザ種別 (既定: msedge)")

    args = parser.parse_args()
    run_simulation(args)


if __name__ == "__main__":
    main()
