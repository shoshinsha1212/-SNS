"""成果型SNS (Agorus) 回答者自律成長エンジン (Persona Growth Engine)

2〜4日ごとに5〜10人の新規回答者（ペルソナ）を自律的に生成・追加し、
データベースへの登録と日次シミュレーションへの合流を自動化するモジュール。
"""

import datetime
import json
import random
import secrets
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.request

# パス定義
ROOT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
TESTERS_DIR = ROOT_DIR / "testers"
PERSONAS_FILE = TESTERS_DIR / "personas_100.json"
GROWTH_STATE_FILE = TESTERS_DIR / "growth_state.json"

# 日本の姓・名のサンプル（18〜25歳の若者に多い名前）
FAMILY_NAMES = [
    "佐藤", "鈴木", "高橋", "田中", "渡辺", "伊藤", "山本", "中村", "小林", "加藤",
    "吉田", "山田", "佐々木", "山口", "松本", "井上", "木村", "林", "斎藤", "清水",
    "山崎", "森", "池田", "橋本", "阿部", "石川", "山下", "中島", "石井", "小川",
    "前田", "岡田", "長谷川", "藤田", "後藤", "近藤", "村上", "遠藤", "青木", "坂本",
    "西村", "福田", "太田", "西田", "藤井", "岡本", "金子", "三浦", "中野", "原田"
]

GIVEN_NAMES_M = [
    "翔太", "蓮", "大翔", "悠真", "陸", "樹", "湊", "颯太", "大輝", "拓海",
    "陽翔", "健太", "亮太", "悠斗", "駿", "蒼", "翼", "隼人", "海斗", "翔",
    "陽太", "裕太", "直樹", "大樹", "圭吾", "陸斗", "一輝", "春輝", "涼介", "翔平"
]

GIVEN_NAMES_F = [
    "葵", "陽菜", "結衣", "美咲", "さくら", "莉子", "結菜", "凛", "芽依", "咲良",
    "七海", "優奈", "美月", "遥", "彩花", "真央", "ひなた", "花", "結月", "菜々子",
    "愛梨", "美緒", "萌", "千尋", "心愛", "琴音", "日和", "友梨", "杏奈", "瑠奈"
]

STUDENT_OCCUPATIONS = [
    ("法学部3年（司法試験勉強中）", "法学部", "〜22歳"),
    ("工学部情報工学科2年", "情報系", "〜22歳"),
    ("経済学部4年（金融業界内定）", "経済学部", "〜22歳"),
    ("文学部日本文学科1年", "文学部", "〜18歳"),
    ("教育学部3年（小学校教員志望）", "教育学部", "〜22歳"),
    ("医学部医学科2年", "医学部", "〜22歳"),
    ("看護学部4年（国家試験準備中）", "看護系", "〜22歳"),
    ("理学部物理学科3年", "理学部", "〜22歳"),
    ("国際教養学部2年（留学準備中）", "国際系", "〜22歳"),
    ("総合政策学部3年（地域活性化活動）", "政策系", "〜22歳"),
    ("社会学部2年（メディア研究）", "社会学部", "〜22歳"),
    ("農学部3年（環境バイオ研究）", "農学部", "〜22歳"),
    ("大学院情報理工学研究科修士1年", "大学院", "23〜29歳"),
    ("大学院人文科学研究科修士2年", "大学院", "23〜29歳"),
    ("短期大学保育科2年", "短大", "〜22歳"),
    ("専門学校ITデザイン科2年", "専門学校", "〜22歳"),
    ("外国語学部4年（観光業界就職予定）", "外国語学部", "〜22歳"),
    ("経営学部2年（学生起業サークル）", "経営学部", "〜22歳"),
    ("薬学部3年（創薬科学専攻）", "薬学部", "〜22歳"),
    ("心理学部2年（臨床心理志望）", "心理学部", "〜22歳"),
]

NON_STUDENT_OCCUPATIONS = [
    ("ITベンチャー新卒エンジニア（1年目）", "エンジニア", "23〜29歳"),
    ("メーカー営業職（社会人2年目）", "営業", "23〜29歳"),
    ("地方公務員（市役所勤務2年目）", "公務員", "23〜29歳"),
    ("カフェ店員・フリーター（留学資金貯金中）", "飲食・サービス", "〜22歳"),
    ("フリーランスWebデザイナー（実務2年）", "クリエイティブ", "23〜29歳"),
    ("アパレルショップ店員（正社員1年目）", "販売", "〜22歳"),
    ("看護師（大学病院勤務2年目）", "医療", "23〜29歳"),
    ("保育士（認可保育園2年目）", "教育・保育", "23〜29歳"),
    ("金融機関総合職（1年目）", "金融", "23〜29歳"),
    ("高卒就職・製造業技術員（4年目）", "製造", "〜22歳"),
    ("スタートアップ勤務（マーケティング）", "マーケティング", "23〜29歳"),
    ("フリーター（資格試験浪人中）", "フリーター", "23〜29歳"),
]

CLUSTERS = [
    {
        "name": "革新的自由派（リベラル・テック志向）",
        "desc": "新技術や個人の自由を強く支持。変革と個人の選択肢拡大を好む。",
        "axes": {"liberty": 0.7, "change": 0.8, "solidarity": 0.3, "future": 0.6},
        "reasons": {
            "agree": ["個人の選択肢を広げるべきだから", "最新の技術や仕組みを活用して効率化すべき", "古い慣習にとらわれる必要はない"],
            "disagree": ["一律の規制や禁止は時代遅れだと思う", "選択の余地を奪うやり方には反対", "個人の自己決定権を尊重すべき"]
        }
    },
    {
        "name": "連帯・セーフティネット重視派（共助・福祉志向）",
        "desc": "格差是正や教育・社会保障の公的支援を重視。困っている人を社会で支え合う。",
        "axes": {"liberty": 0.2, "change": 0.4, "solidarity": 0.8, "future": 0.7},
        "reasons": {
            "agree": ["家庭環境による格差をなくすべき", "社会全体で支え合う仕組みが必要", "若い世代が安心して学べる環境を整えるべき"],
            "disagree": ["すべて自己責任にするのは酷だと思う", "支援を削る方向には賛成できない", "弱者への配慮が欠けている"]
        }
    },
    {
        "name": "現実・自立重視派（自助・実務志向）",
        "desc": "自己責任と財源の現実性を重視。安易なバラマキや過剰な規制に慎重。",
        "axes": {"liberty": 0.4, "change": -0.2, "solidarity": -0.6, "future": -0.3},
        "reasons": {
            "agree": ["個人の努力と責任が基本だと思う", "財源の裏付けがない政策は続かない", "公平な競争環境が大切"],
            "disagree": ["税負担ばかり増えるのは納得がいかない", "本人の選択に税金を使いすぎるのは疑問", "結果の平等より機会の公平を目指すべき"]
        }
    },
    {
        "name": "伝統・調和重視派（安定・秩序志向）",
        "desc": "社会の安定とルール、家族やコミュニティの一体感を大事にする。",
        "axes": {"liberty": -0.6, "change": -0.7, "solidarity": 0.3, "future": 0.1},
        "reasons": {
            "agree": ["秩序や規範を守ることが社会の安定につながる", "伝統や家族のつながりを大切にしたい", "慎重に議論を重ねて決めるべき"],
            "disagree": ["急激な変化は混乱を招くと思う", "自由を認めすぎるとモラルが崩壊する懸念がある", "現行の制度にも合理的な理由がある"]
        }
    },
    {
        "name": "バランス・中間派（柔軟・現実重視）",
        "desc": "極端な意見を避け、ケースバイケースで現実的な落としどころを探る。",
        "axes": {"liberty": 0.0, "change": 0.1, "solidarity": 0.2, "future": 0.2},
        "reasons": {
            "agree": ["メリットとデメリットを比較して妥当だと感じる", "段階的に進めるなら賛成できる", "現実的な解決策だと思う"],
            "disagree": ["もう少し運用面での配慮が必要", "一方の負担が大きすぎる懸念がある", "まだ議論が尽くされていないと感じる"]
        }
    }
]


def load_growth_state() -> Dict[str, Any]:
    """現在の成長トラッキング状態をロード"""
    if GROWTH_STATE_FILE.exists():
        try:
            with GROWTH_STATE_FILE.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    # 初期状態
    initial_state = {
        "last_growth_date": "2026-11-14",  # 直近の基準日
        "next_interval_days": random.randint(2, 4),  # 2〜4日後
        "total_added_respondents": 0,
        "history": []
    }
    save_growth_state(initial_state)
    return initial_state


def save_growth_state(state: Dict[str, Any]) -> None:
    """成長トラッキング状態を保存"""
    try:
        with GROWTH_STATE_FILE.open("w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"成長状態の保存に失敗しました: {e}", file=sys.stderr)


def is_server_listening(url: str, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as res:
            return res.status in (200, 304, 404)
    except Exception:
        return False


def register_user_in_db(tokens: List[str], target_url: str) -> int:
    """ローカルSQLiteまたはバックエンドにユーザーを一括登録"""
    registered_count = 0

    # 1. ローカル SQLite DB への直接登録（手元にある場合）
    local_db_path = BACKEND_DIR / "data" / "seika.db"
    if local_db_path.exists():
        try:
            import sqlite3
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            with sqlite3.connect(str(local_db_path)) as con:
                cur = con.cursor()
                for tok in tokens:
                    row = cur.execute("SELECT id FROM users WHERE token = ?", (tok,)).fetchone()
                    if not row:
                        cur.execute(
                            "INSERT INTO users (token, profile_asked, created_at) VALUES (?, ?, ?)",
                            (tok, 0, now_iso)
                        )
                        registered_count += 1
                con.commit()
            return registered_count
        except Exception as e:
            print(f"ローカルDB登録エラー: {e}", file=sys.stderr)

    # 2. サーバーが起動している場合のみ API エンドポイント経由で登録
    if is_server_listening(target_url.rstrip("/") + "/api/topics"):
        for tok in tokens:
            api_url = target_url.rstrip("/") + "/api/me"
            try:
                req = urllib.request.Request(
                    api_url,
                    headers={
                        "Authorization": f"Bearer {tok}",
                        "User-Agent": "AgorusGrowthEngine"
                    }
                )
                with urllib.request.urlopen(req, timeout=2) as res:
                    registered_count += 1
            except Exception:
                pass

    return registered_count


def generate_single_persona(new_id: int) -> Dict[str, Any]:
    """1名分の新規ペルソナデータを生成"""
    token = secrets.token_urlsafe(16)
    is_student = random.random() < 0.70

    if is_student:
        occ_info = random.choice(STUDENT_OCCUPATIONS)
        if occ_info[2] == "〜18歳":
            age = 18
            age_band = "〜18歳"
        elif occ_info[2] == "23〜29歳":
            age = random.choice([23, 24])
            age_band = "23〜29歳"
        else:
            age = random.randint(19, 22)
            age_band = "19〜22歳"
        occupation = occ_info[0]
        field = occ_info[1]
    else:
        occ_info = random.choice(NON_STUDENT_OCCUPATIONS)
        if occ_info[2] == "〜22歳":
            age = random.randint(20, 22)
            age_band = "19〜22歳"
        else:
            age = random.randint(23, 25)
            age_band = "23〜29歳"
        occupation = occ_info[0]
        field = occ_info[1]

    gender = "M" if random.random() < 0.5 else "F"
    fname = random.choice(FAMILY_NAMES)
    gname = random.choice(GIVEN_NAMES_M if gender == "M" else GIVEN_NAMES_F)
    name = f"{fname} {gname}"

    cluster = random.choice(CLUSTERS)

    def clamp(val):
        return max(-1.0, min(1.0, round(val + random.uniform(-0.15, 0.15), 2)))

    axes = {
        "liberty": clamp(cluster["axes"]["liberty"]),
        "change": clamp(cluster["axes"]["change"]),
        "solidarity": clamp(cluster["axes"]["solidarity"]),
        "future": clamp(cluster["axes"]["future"]),
    }

    peak_hours = random.choice([
        [8, 9, 12, 13],
        [12, 13, 17, 18],
        [19, 20, 21, 22],
        [22, 23, 0, 1],
    ])

    return {
        "id": new_id,
        "user_id": new_id,
        "token": token,
        "name": name,
        "gender": "男性" if gender == "M" else "女性",
        "age": age,
        "age_band": age_band,
        "is_student": is_student,
        "occupation": occupation,
        "field": field,
        "cluster_name": cluster["name"],
        "cluster_desc": cluster["desc"],
        "axes": axes,
        "peak_hours": peak_hours,
        "sample_reasons": cluster["reasons"],
        "reason_prob": round(random.uniform(0.25, 0.50), 2),
        "base_understanding": random.choice([3, 4, 4, 5]),
        "joined_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }


def check_and_grow_respondents(
    target_url: str = "http://localhost:5173",
    force: bool = False,
    min_add: int = 5,
    max_add: int = 10,
    min_days: int = 2,
    max_days: int = 4
) -> List[Dict[str, Any]]:
    """2〜4日ごとに5〜10人の新規回答者を自動生成・追加する"""
    state = load_growth_state()
    today_str = datetime.date.today().strftime("%Y-%m-%d")

    last_date_str = state.get("last_growth_date", today_str)
    try:
        last_date = datetime.datetime.strptime(last_date_str, "%Y-%m-%d").date()
    except Exception:
        last_date = datetime.date.today()

    diff_days = (datetime.date.today() - last_date).days
    next_interval = state.get("next_interval_days", random.randint(min_days, max_days))

    # 増加のタイミング判定
    should_grow = force or (diff_days >= next_interval)

    if not should_grow:
        days_left = next_interval - diff_days
        # まだ成長タイミングではない
        return []

    # 5〜10人のランダム人数を決定
    add_count = random.randint(min_add, max_add)

    # 既存のペルソナ一覧をロード
    personas = []
    if PERSONAS_FILE.exists():
        try:
            with PERSONAS_FILE.open("r", encoding="utf-8") as f:
                personas = json.load(f)
        except Exception:
            pass

    start_id = max([p["id"] for p in personas], default=0) + 1

    new_personas = []
    for i in range(add_count):
        p = generate_single_persona(start_id + i)
        new_personas.append(p)

    # データベースにユーザー一括登録
    register_user_in_db([p["token"] for p in new_personas], target_url)

    # ペルソナファイルに追記
    personas.extend(new_personas)
    with PERSONAS_FILE.open("w", encoding="utf-8") as f:
        json.dump(personas, f, ensure_ascii=False, indent=2)

    # 成長状態を更新
    new_interval = random.randint(min_days, max_days)
    state["last_growth_date"] = today_str
    state["next_interval_days"] = new_interval
    state["total_added_respondents"] = state.get("total_added_respondents", 0) + add_count
    state["history"].append({
        "date": today_str,
        "added_count": add_count,
        "new_total": len(personas),
        "next_interval_days": new_interval
    })
    save_growth_state(state)

    print(f"🎉 【回答者自律成長】{add_count} 名の新規回答者がコミュニティに参加しました！（総数: {len(personas)}名 / 次回追加: {new_interval}日後）")
    return new_personas


if __name__ == "__main__":
    # 単体テスト用実行
    import argparse
    parser = argparse.ArgumentParser(description="回答者自律成長スクリプト")
    parser.add_argument("--force", action="store_true", help="間隔日数を無視して今すぐ5〜10名を追加する")
    parser.add_argument("--target", default="http://localhost:5173", help="対象URL")
    args = parser.parse_args()

    added = check_and_grow_respondents(target_url=args.target, force=args.force)
    if added:
        print(f"追加された回答者（{len(added)}名）:")
        for p in added:
            print(f"  - [{p['id']:03d}] {p['name']} ({p['age']}歳 / {p['occupation']})")
    else:
        state = load_growth_state()
        print(f"本日は追加サイクルではありませんでした（前回: {state.get('last_growth_date')}, 間隔: {state.get('next_interval_days')}日）。")
