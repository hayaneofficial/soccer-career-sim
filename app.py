import streamlit as st
import google.generativeai as genai
import game_data
import json
import random
import datetime
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import time
import re

# ページ設定
st.set_page_config(page_title="Football Career AI", layout="wide", initial_sidebar_state="collapsed")

# --- セッション初期化 ---
if "player" not in st.session_state:
    st.session_state.player = None
if "game_phase" not in st.session_state:
    st.session_state.game_phase = "start"
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_event" not in st.session_state:
    st.session_state.current_event = None
if "create_log" not in st.session_state:
    st.session_state.create_log = []
if "temp_profile" not in st.session_state:
    st.session_state.temp_profile = {}
if "temp_data" not in st.session_state:
    st.session_state.temp_data = {}
if "transfer_notice" not in st.session_state:
    st.session_state.transfer_notice = None

# --- 便利関数（UI） ---
def render_stat(col, label, value, sub=None):
    """
    1行のメトリクスをコンパクトなカードで表示する。
    長い数字も折り返して潰れないようにする。
    """
    col.markdown(
        f"""
        <div style="
            padding:4px 6px;
            border-radius:6px;
            border:1px solid rgba(255,255,255,0.15);
            background-color:rgba(0,0,0,0.15);
            ">
          <div style="font-size:0.70rem; opacity:0.7; margin-bottom:2px;">
            {label}
          </div>
          <div style="
              font-size:0.95rem;
              font-weight:600;
              line-height:1.2;
              word-wrap:break-word;
              word-break:break-all;
          ">
            {value}
          </div>
          {f'<div style="font-size:0.65rem; opacity:0.65; margin-top:1px;">{sub}</div>' if sub else ""}
        </div>
        """,
        unsafe_allow_html=True
    )


# --- カテゴリ判定 ---
def determine_category(team_name: str) -> str:
    """
    チーム名からカテゴリを判定する共通関数。
    HighSchool / University / Youth / Professional のどれかを返す。
    """
    if not team_name:
        return "Professional"

    name = team_name.replace(" ", "").replace("　", "")
    name_low = name.lower()

    # 高校
    if ("高校" in name) or ("高等学校" in name) or ("highschool" in name_low) or ("high-school" in name_low):
        return "HighSchool"

    # 大学
    if ("大学" in name) or ("大學" in name) or ("univ" in name_low) or ("university" in name_low) or ("college" in name_low):
        return "University"

    # ユース / U-18 等
    if ("ユース" in name) or ("youth" in name_low):
        return "Youth"
    if re.search(r"\bu-?1[0-9]\b", name_low) or "u18" in name_low or "u17" in name_low or "u16" in name_low:
        return "Youth"
    if "u-18" in name_low or "u18" in name_low:
        return "Youth"

    # それ以外はプロ扱い
    return "Professional"


# --- 汎用ユーティリティ ---
def safe_json_load(text):
    try:
        text = text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text)
        if isinstance(data, list):
            return data[0] if data else {}
        return data
    except Exception:
        return {}


def safe_float(val, default=0.0):
    try:
        return float(val)
    except Exception:
        return default


def safe_int(val, default=0):
    try:
        if isinstance(val, (int, float)):
            return int(val)
        val_str = str(val).lower()
        multiplier = 1
        if 'm' in val_str:
            multiplier = 1_000_000
        elif 'k' in val_str:
            multiplier = 1_000
        elif '億' in val_str:
            multiplier = 100_000_000
        elif '万' in val_str:
            multiplier = 10_000
        clean_str = re.sub(r'[^\d.]', '', val_str)
        if not clean_str:
            return default
        return int(float(clean_str) * multiplier)
    except Exception:
        return default


def convert_position_by_foot(category: str, position: str, foot: str) -> str:
    if category not in ("HighSchool", "University"):
        return position
    if not foot:
        return position
    pos = position.upper()
    if pos == "CB":
        return "LCB" if foot.startswith("左") else "RCB"
    if pos == "CMF":
        return "LCM" if foot.startswith("左") else "RCM"
    if pos == "CF":
        return "RCF" if foot.startswith("左") else "LCF"
    return position


def ca_offer_bucket(ca: float) -> str:
    thresholds = [
        (37, "大学下位チームベンチ"),
        (40, "大学Dスタメン"),
        (45, "大学Cベンチ"),
        (50, "大学Cスタメン"),
        (55, "大学Bベンチ"),
        (60, "大学Bスタメン可"),
        (70, "大学Aスタメン争い"),
        (80, "大学Aスタメン / JFL特指クラス"),
        (90, "J1練習参加・特指レベル"),
        (100, "J1正規メンバー"),
        (110, "海外挑戦可能な若手"),
        (130, "J1エース級"),
        (140, "日本代表入りレベル"),
        (150, "日本代表主力"),
        (160, "欧州主要リーグスタメン級"),
        (170, "欧州トップクラブ主力候補"),
        (180, "世界的ビッグクラブ争奪戦"),
        (200, "歴史的レジェンド"),
    ]
    for bound, label in thresholds:
        if ca <= bound:
            return label
    return "特級"  # safety


def maybe_generate_transfer_offer(player):
    """Create a transfer offer based on CA buckets and return it if triggered."""
    ca = player.ca
    bucket = ca_offer_bucket(ca)
    base_chance = 0.0
    if ca >= 80:
        base_chance = 0.12
    elif ca >= 60:
        base_chance = 0.08
    elif ca >= 45:
        base_chance = 0.05
    elif ca >= 37:
        base_chance = 0.03
    if random.random() > base_chance:
        return None

    leagues = [
        "明治安田J1リーグ", "明治安田J2リーグ", "関東大学サッカーリーグ1部", "関西学生リーグ1部",
        "プレミアリーグ", "セリエA", "リーガ・エスパニョーラ", "ブンデスリーガ"
    ]
    club_prefix = ["FC", "SC", "AC", "ユナイテッド", "シティ", "ヴィレッジ", "カレッジ"]
    club_suffix = ["東京", "大阪", "名古屋", "札幌", "マドリード", "ロンドン", "デュッセルドルフ", "フィレンツェ"]
    category = "Professional" if ca >= 70 else player.team_category

    offer = {
        "club": f"{random.choice(club_suffix)}{random.choice(club_prefix)}",
        "league": random.choice(leagues),
        "category": category,
        "status": "new",
        "bucket": bucket,
        "created": player.current_date.isoformat(),
        "salary": max(player.salary, int(500000 + ca * 10_000)),
    }
    player.transfer_offers.append(offer)
    return offer


def apply_transfer(player, offer):
    """Apply an accepted offer to the player and regenerate team context."""
    player.team_name = offer.get("club", player.team_name)
    player.team_category = offer.get("category", "Professional")
    player.salary = offer.get("salary", player.salary)
    player.grade = game_data.TeamGenerator._grade_label(player.team_category, player.age)

    team_info = create_team_data(player.team_name, player.team_category, player.current_date)
    formation = team_info.get("formation") if team_info else None
    real_players = team_info.get("real_players", []) if team_info else []
    members, formation = game_data.TeamGenerator.generate_teammates(
        player.team_category,
        formation or game_data.TeamGenerator.DEFAULT_FORMATIONS.get(player.team_category, "4-3-3"),
        real_players
    )
    player.team_members = members
    player.formation = formation
    player.update_hierarchy()


def offer_summary_text(offer: dict) -> str:
    return (
        f"{offer.get('club')} (リーグ: {offer.get('league')})\n"
        f"想定ロール: {offer.get('bucket')} / 推定年俸: {offer.get('salary'):,}"
    )


# --- サイドバー ---
with st.sidebar:
    st.header("⚙️ 設定")
    api_key_input = st.text_input("Gemini APIキー", type="password")
    api_key = api_key_input.strip() if api_key_input else None

    # モデル選択
    model_options = [
        "models/gemini-2.0-flash",
        "models/gemini-1.5-pro",
        "models/gemini-3-pro-preview"
    ]
    selected_model = st.selectbox("使用モデル", model_options, index=0)

    if st.session_state.player:
        st.divider()
        if st.button("💾 手動セーブ"):
            game_data.save_game(st.session_state.player)
            st.success("保存しました")

    st.divider()
    if st.button("リセットして最初から"):
        st.session_state.clear()
        st.rerun()


# --- Gemini呼び出しラッパー ---
def call_gemini(prompt):
    if not api_key:
        return None
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            selected_model,
            generation_config={"response_mime_type": "application/json"}
        )
        res = model.generate_content(prompt)
        return safe_json_load(res.text)
    except Exception as e:
        st.error(f"Geminiエラー: {e}")
        return None


# --- ゲームロジック関数 ---
def create_initial_data(profile_data, category, start_date):
    # FM準拠の能力キー一覧（game_data側と完全一致させる）
    ability_keys = list(game_data.WEIGHTS.keys())
    ability_keys_text = ", ".join([f'"{k}"' for k in ability_keys])

    base_prompt = f"""
    サッカースカウトAIとして以下を実行してください。
    プロフィール: {profile_data}
    カテゴリ: {category}
    開始日時: {start_date}

    能力値に関する前提:
    - 能力値はすべて 1.0〜20.0 の数値。
    - attributes には、必ず次のキーをすべて含めること:
      {ability_keys_text}
    - どのキーについても、情報が不足する場合は 10.0 を設定してよい。
    - 「WeakFoot」は逆足の使える度合い（1.0〜20.0）。

    指示:
    1. プロフィールに基づき、上記すべての能力値(1.0-20.0)を設定した attributes を作成する。
       - ただし CA 計算そのものは行わず、能力値のみを決めること。
    2. 経済状況から所持金(funds)と年俸(salary)を推定する（整数）。
    3. 人間関係から NPC を数名作成する。

    もし情報が不足している場合は、追加で尋ねるべき質問を返してください。
    その場合は次の形式で出力してください:
    {{
      "need_questions": true,
      "questions": ["質問1", "質問2", ...]
    }}

    十分な情報が揃っている場合は、次の形式で出力してください:
    {{
        "attributes": {{
            "Decisions": 11.5,
            "Anticipation": 10.0,
            "Composure": 9.0,
            ...
            "WeakFoot": 8.0
        }},
        "funds": 100000,
        "salary": 0,
        "npcs": [
            {{"role": "父親", "name": "佐藤 太一", "relation": -10, "description": "サッカーに反対している"}}
        ]
    }}
    """

    prompt = base_prompt
    for _ in range(3):
        res = call_gemini(prompt)
        if not res:
            return res
        if not res.get("need_questions"):
            return res

        # Geminiからの追加質問を再度投げ直し、足りない部分を推定させる
        q_text = "\\n".join(res.get("questions", []))
        prompt = base_prompt + "\n追加質問にはあなた自身が想像して回答し、全能力値を埋めてください。\n" + q_text

    return res


def create_team_data(team_name, category, start_date):
    prompt = f"""
    チーム名「{team_name}」({start_date}時点)のデータを生成せよ。
    カテゴリ: {category}

    指示:
    1. 基本フォーメーション(4-3-3等)を推定。
    2. 実在選手を【必ず25名】リストアップ（不足分は架空）。
       - 外国人選手・チーム名は「カタカナ」。日本人・日本チームは「漢字」。
       - 詳細データ: 背番号, 年齢, 利き足, 身長, 市場価値(数値のみ)

    Output JSON:
    {{
        "formation": "4-3-3",
        "real_players": [
            {{
                "name": "...",
                "position": "...",
                "value": 5000000,
                "number": 10,
                "age": 24,
                "foot": "右",
                "height": 178
            }}
        ]
    }}
    """
    return call_gemini(prompt)

def create_school_timetable(player):
    """
    高校/ユースの「学校時間割」を作成する。
    チーム週間スケジュールと矛盾しないように、授業は基本的に日中、部活は放課後という前提。
    """
    team_plan = getattr(player, "team_weekly_plan", [])

    prompt = f"""
    あなたは日本の高校サッカー部員（または高校年代ユース選手）の
    「学校の時間割」を設計するAIです。

    [前提]
    - 氏名: {player.name}
    - 年齢: {player.age}
    - チーム: {player.team_name}
    - チームカテゴリ: {player.team_category}
    - サッカーの週間スケジュール(概略):
      {json.dumps(team_plan, ensure_ascii=False)}

    [制約・方針]
    - 日本の一般的な高校の時間割をベースにすること。
      - 平日は Mon〜Fri を必須、必要なら Sat に午前授業を入れてよい。
      - 1日あたりおおよそ 5〜6コマ（p1〜p6）を想定。
    - サッカー部のトレーニングは「放課後」に行われる前提とし、
      この時間割の p1〜p6 の中には原則サッカー部の活動を含めないこと。
    - サッカーの週間スケジュールと大きく矛盾しないように、
      例: トレーニングが非常にハードな日の翌日は、授業のコマ数をやや抑える など、
      最低限の整合性は意識してください（ただし細かい時刻までは考えなくてよい）。

    [出力形式]
    次の形式の JSON のみを出力してください:

    {{
      "timetable": [
        {{
          "weekday": "Mon",
          "p1": "現代文",
          "p2": "数学I",
          "p3": "英語コミュニケーション",
          "p4": "世界史",
          "p5": "体育",
          "p6": "HR"
        }}
      ]
    }}

    - weekday は "Mon","Tue","Wed","Thu","Fri","Sat","Sun" のいずれか。
    - 少なくとも Mon〜Fri の5日分を含めること。
    - JSON 以外のテキストは出力してはいけません。
    """

    res = call_gemini(prompt)
    if not res:
        # フォールバック（かなり単純なデフォルト）
        default = [
            {"weekday": "Mon", "p1": "現代文", "p2": "数学I", "p3": "英語", "p4": "世界史", "p5": "体育", "p6": "HR"},
            {"weekday": "Tue", "p1": "数学I", "p2": "英語", "p3": "化学基礎", "p4": "古典", "p5": "地理", "p6": "LHR"},
            {"weekday": "Wed", "p1": "英語", "p2": "物理基礎", "p3": "現代社会", "p4": "数学A", "p5": "体育", "p6": "HR"},
            {"weekday": "Thu", "p1": "古典", "p2": "数学I", "p3": "英語", "p4": "生物基礎", "p5": "国語総合", "p6": "HR"},
            {"weekday": "Fri", "p1": "世界史", "p2": "数学A", "p3": "英語", "p4": "情報", "p5": "体育", "p6": "HR"},
        ]
        return {"timetable": default}

    if "timetable" not in res:
        res["timetable"] = []
    return res


def create_univ_timetable(player):
    """
    大学生用の「履修時間割」を作成する。
    チーム週間スケジュールと矛盾しないように、トレーニング時間帯を避けて講義を配置させる。
    """
    team_plan = getattr(player, "team_weekly_plan", [])

    prompt = f"""
    あなたは日本の大学サッカー部員の履修相談に乗るAIです。

    [前提]
    - 氏名: {player.name}
    - 年齢: {player.age}
    - 所属チーム: {player.team_name}
    - チームカテゴリ: {player.team_category}
    - サッカーの週間スケジュール(概略):
      {json.dumps(team_plan, ensure_ascii=False)}

    [前提（抽象）]
    - 一般的な日本の大学を想定してよい（例: 1限 9:00〜、2限 10:40〜... 程度）。
    - サッカーのトレーニングは主に「夕方〜夜」に行われる想定で、
      heavy な講義はその時間帯には入れないように配慮すること。

    [タスク]
    - Mon〜Fri を中心に、「1週間の履修時間割」を作成してください。
    - 各曜日について、p1〜p5 までの5コマを定義し、
      それぞれに講義名または「空きコマ」「自習」などを設定してください。
    - サッカーのトレーニングが「午後〜夕方」に集中している曜日は、
      p4, p5 を空きコマにする など、最低限の両立を意識してください。
    - それぞれのコマには、次の付加情報を必ず付けてください:
      - required: "必修" または "選択"
      - delivery: "オンライン" / "オンデマンド" / "オフライン" のいずれか
    - 履修科目名は、それっぽい日本語の講義名で構いません
      （例: 「経済学入門」「スポーツ科学基礎」「統計学Ⅰ」など）。

    [出力形式]
    次の形式の JSON のみを出力してください:

    {{
      "timetable": [
        {{
          "weekday": "Mon",
          "p1": "経済学入門",
          "p1_required": "必修",
          "p1_delivery": "オフライン",
          "p2": "統計学Ⅰ",
          "p2_required": "選択",
          "p2_delivery": "オンライン",
          "p3": "空きコマ",
          "p3_required": "選択",
          "p3_delivery": "オンデマンド",
          "p4": "スポーツ科学基礎",
          "p4_required": "選択",
          "p4_delivery": "オフライン",
          "p5": "空きコマ",
          "p5_required": "選択",
          "p5_delivery": "オンデマンド"
        }}
      ]
    }}

    - weekday は "Mon","Tue","Wed","Thu","Fri","Sat","Sun" のいずれか。
    - 少なくとも Mon〜Fri の5日分を含めること。
    - JSON 以外のテキストは出力してはいけません。
    """

    res = call_gemini(prompt)
    if not res:
        default = [
            {"weekday": "Mon", "p1": "基礎ゼミ", "p1_required": "必修", "p1_delivery": "オフライン", "p2": "統計学Ⅰ", "p2_required": "必修", "p2_delivery": "オフライン", "p3": "空きコマ", "p3_required": "選択", "p3_delivery": "オンデマンド", "p4": "スポーツ科学入門", "p4_required": "選択", "p4_delivery": "オフライン", "p5": "空きコマ", "p5_required": "選択", "p5_delivery": "オンライン"},
            {"weekday": "Tue", "p1": "経済学入門", "p1_required": "必修", "p1_delivery": "オフライン", "p2": "英語リーディング", "p2_required": "必修", "p2_delivery": "オンライン", "p3": "空きコマ", "p3_required": "選択", "p3_delivery": "オンデマンド", "p4": "情報リテラシー", "p4_required": "選択", "p4_delivery": "オンライン", "p5": "空きコマ", "p5_required": "選択", "p5_delivery": "オンデマンド"},
            {"weekday": "Wed", "p1": "社会学概論", "p1_required": "必修", "p1_delivery": "オフライン", "p2": "空きコマ", "p2_required": "選択", "p2_delivery": "オンデマンド", "p3": "第二外国語", "p3_required": "選択", "p3_delivery": "オフライン", "p4": "空きコマ", "p4_required": "選択", "p4_delivery": "オンデマンド", "p5": "空きコマ", "p5_required": "選択", "p5_delivery": "オンライン"},
            {"weekday": "Thu", "p1": "憲法学", "p1_required": "必修", "p1_delivery": "オフライン", "p2": "空きコマ", "p2_required": "選択", "p2_delivery": "オンデマンド", "p3": "スポーツ心理学", "p3_required": "選択", "p3_delivery": "オフライン", "p4": "空きコマ", "p4_required": "選択", "p4_delivery": "オンライン", "p5": "空きコマ", "p5_required": "選択", "p5_delivery": "オンデマンド"},
            {"weekday": "Fri", "p1": "空きコマ", "p1_required": "選択", "p1_delivery": "オンデマンド", "p2": "空きコマ", "p2_required": "選択", "p2_delivery": "オンライン", "p3": "プロジェクト科目", "p3_required": "必修", "p3_delivery": "オフライン", "p4": "空きコマ", "p4_required": "選択", "p4_delivery": "オンデマンド", "p5": "空きコマ", "p5_required": "選択", "p5_delivery": "オンライン"},
        ]
        return {"timetable": default}

    if "timetable" not in res:
        res["timetable"] = []
    return res


def create_team_weekly_plan(team_name, category):
    """
    チームの「曜日ごとの基本スケジュール」を Gemini に作らせる。
    例：月: OFF / 火: 午前ジム・午後TR など。
    """
    prompt = f"""
    あなたはサッカーコーチ兼スケジューラーAIです。

    [前提]
    - チーム名: {team_name}
    - カテゴリ: {category}

    [タスク]
    このチームの「1週間の基本スケジュール」を作成してください。
    - 対象: 月曜〜日曜
    - 各曜日について、
      - morning: 午前の活動（例: OFF, フィジカル, ミーティング, コンディショニング など）
      - afternoon: 午後の活動（例: チームトレーニング, 戦術トレーニング など）
      - evening: 夜の活動（例: 自由, 映像分析, 寮での自習 など）
      を日本語テキストで1〜2フレーズ程度記述してください。

    カテゴリ別のイメージ:
    - Professional: 週1〜2日OFF、他の日はトレーニング中心。試合前日は軽め。
    - University / HighSchool / Youth:
      学校の授業がある前提で、放課後にトレーニングが入る構成を意識してください。

    [出力形式]
    次の形式の JSON のみを出力してください:

    {{
      "plan": [
        {{
          "weekday": "Mon",
          "morning": "OFF",
          "afternoon": "チームトレーニング（戦術＋ポゼッション）",
          "evening": "自由 / 映像分析"
        }}
      ]
    }}

    - weekday は "Mon","Tue","Wed","Thu","Fri","Sat","Sun" のいずれか。
    - 必ず 7 行（7曜日分）を含めてください。
    - JSON 以外のテキストは出力してはいけません。
    """

    res = call_gemini(prompt)
    if not res:
        # フォールバック：ごく単純なデフォルト
        default_plan = [
            {"weekday": "Mon", "morning": "OFF", "afternoon": "チームトレーニング", "evening": "自由"},
            {"weekday": "Tue", "morning": "ジム", "afternoon": "チームトレーニング", "evening": "自由"},
            {"weekday": "Wed", "morning": "OFF", "afternoon": "戦術トレーニング", "evening": "映像分析"},
            {"weekday": "Thu", "morning": "ジム", "afternoon": "チームトレーニング", "evening": "自由"},
            {"weekday": "Fri", "morning": "軽めの調整", "afternoon": "セットプレー確認", "evening": "自由"},
            {"weekday": "Sat", "morning": "試合 or 試合前日TR", "afternoon": "試合 or リカバリー", "evening": "自由"},
            {"weekday": "Sun", "morning": "OFF", "afternoon": "OFF", "evening": "OFF"},
        ]
        return {"plan": default_plan}

    if "plan" not in res:
        # 形式がおかしいときの最低限の保険
        res["plan"] = []
    return res


def create_schedule_data(team_name, category, year):
    """
    チーム名・カテゴリ・年から、現実に近い大会構造と年間スケジュールを Gemini に推定させる。
    - competitions: 大会メタ情報
    - schedule: 1年分の試合リスト
    """
    prompt = f"""
    あなたは世界中のサッカー大会構造に詳しいデータアナリストAIです。

    [前提]
    - チーム名: {team_name}
    - カテゴリ: {category}
    - シーズン: {year}年

    [タスク概要]
    1. 可能な範囲で一般的な知識を使い、
       このチームが {year} シーズンに参加する可能性が高い大会を列挙してください。
       - プロクラブの場合:
         - 国内リーグ (必須)
         - 国内カップ (原則含める)
         - 欧州クラブであれば、チャンピオンズリーグ(CL) / ヨーロッパリーグ(EL) /
           カンファレンスリーグ(ECL)の出場可能性も検討すること。
       - 高校・大学・ユースの場合:
         - 地域リーグ（例: 関東リーグ）
         - インディペンデンスリーグ
         - 全国大会・カップ戦　などを推定すること。

    2. 各大会について、次のメタ情報を推定してください:
       - code: "LEAGUE", "CUP", "CL", "EL", "ECL", "REGIONAL", "SCHOOL_CUP" など短い識別子
       - name: 大会正式名称
       - type: "league" または "knockout"
       - priority: 数値 (1=最重要。通常はリーグ > カップ のように設定)
       - season_start: "{year}-MM-DD" 形式の大会期間開始日（だいたいでよい）
       - season_end:   "{year}-MM-DD" 形式の大会期間終了日（だいたいでよい）
       - match_days: 代表的な試合曜日の配列 (例: ["Sat","Sun","Wed"])
       - team_count: おおよそのチーム数
       - rounds: リーグの場合は総当たり回数(1 or 2)、
                 カップの場合はそのチームが最大で到達しうるラウンド数
       - include_for_player: true/false
         このゲーム内で扱うべき大会かどうか。マイナー大会は false でもよい。

    3. 上記メタ情報にもとづいて、{year}年のこのチームの年間試合日程を作成してください。
       制約:
       - "schedule" には、少なくとも 30 試合以上を含めること。
       - 国内リーグは現実に近い試合数になるようにすること。
         - 18〜22チームのホーム&アウェーなら 34〜42 試合が目安。
       - 国内カップは 1〜6 試合程度でよい（このチームの格に応じて推定してよい）。
       - 欧州コンペティションは、現実の出場状況を知らない場合でも、
         出場の可能性が相応にある強豪クラブなら数試合を想定して良い。
       - 試合間隔はできるだけ 3 日以上あけること。
       - 明らかなオフシーズン（リーグ終了後〜年末など）は試合を入れない。
       - "date" は "{year}-01-01"〜"{year}-12-31" の範囲に収めること。

    [出力形式]
    100% 有効な JSON だけを出力してください。
    次のスキーマに厳密に従ってください:

    {{
      "competitions": [
        {{
          "code": "LEAGUE",
          "name": "J1リーグ",
          "type": "league",
          "priority": 1,
          "season_start": "{year}-02-20",
          "season_end":   "{year}-12-05",
          "match_days": ["Sat","Sun"],
          "team_count": 18,
          "rounds": 2,
          "include_for_player": true
        }}
      ],
      "schedule": [
        {{
          "date": "{year}-02-25",
          "opponent": "横浜F・マリノス",
          "home": true,
          "competition_code": "LEAGUE",
          "round": "MD1"
        }}
      ]
    }}

    注意:
    - 上記は例です。実際には {team_name} に合わせた大会・対戦相手・日程を生成してください。
    - JSON 以外のテキスト（説明文やコメント）は一切出力してはいけません。
    """

    res = call_gemini(prompt)

    # Gemini から何も返ってこなかったときのフォールバック（日程だけダミー生成）
    if not res:
        dummy_schedule = []
        start = datetime.date(year, 3, 1)
        for i in range(30):
            d = start + datetime.timedelta(days=7 * i)
            dummy_schedule.append({
                "date": d.isoformat(),
                "opponent": f"クラブ{i+1}",
                "home": (i % 2 == 0),
                "competition_code": "LEAGUE",
                "round": f"MD{i+1}"
            })
        return {"competitions": [], "schedule": dummy_schedule}

    # competitions / schedule が無い場合の保険
    if "competitions" not in res:
        res["competitions"] = []
    if "schedule" not in res:
        res["schedule"] = []

    return res


def summarize_annual_outline(schedule, year):
    """Rough monthly outline (off-season, transfer, camps) before daily play."""
    month_buckets = {m: [] for m in range(1, 13)}
    for match in schedule:
        date_str = match.get("date")
        try:
            d = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception:
            continue
        if d.year != year:
            continue
        month_buckets[d.month].append(match)

    outline = []
    for month in range(1, 13):
        matches = month_buckets[month]
        match_count = len(matches)
        label = "リーグ/カップ進行"
        if match_count == 0:
            label = "オフ・自主トレ期間"
        elif match_count <= 2:
            label = "キャンプ・調整中心"
        if month in (1, 7):
            label += " / 移籍期間を想定"
        outline.append({
            "month": f"{month}月",
            "matches": match_count,
            "note": label
        })
    return outline


def align_weekly_plan_with_schedule(plan, schedule):
    """Match weekly plan match-days to the most common schedule weekdays."""
    if not plan or not schedule:
        return plan, False

    weekday_count = {}
    for match in schedule:
        try:
            d = datetime.datetime.strptime(match.get("date", ""), "%Y-%m-%d").date()
        except Exception:
            continue
        wd = d.strftime("%a")
        weekday_count[wd] = weekday_count.get(wd, 0) + 1

    if not weekday_count:
        return plan, False

    common_days = sorted(weekday_count.items(), key=lambda x: x[1], reverse=True)
    target_days = {day for day, _ in common_days[:2]}

    updated = False
    new_plan = []
    for entry in plan:
        weekday = entry.get("weekday")
        if weekday in target_days:
            afternoon = entry.get("afternoon", "")
            evening = entry.get("evening", "")
            if "試合" not in afternoon:
                afternoon = "試合 / 公式戦" if afternoon == "" else f"試合 / 公式戦 / {afternoon}"
                updated = True
            if "試合" not in evening:
                evening = "リカバリー or 移動" if evening == "" else f"{evening} / リカバリー"
                updated = True
            entry = {**entry, "afternoon": afternoon, "evening": evening}
        new_plan.append(entry)

    return new_plan, updated



def generate_story(player, topic):
    prompt = f"""
    あなたはリアル志向のサッカー小説家です。

    【選手設定】
    - 名前: {player.name}
    - 所属クラブ / チーム: {player.team_name}
    - 年齢: {player.age}
    - ポジション: {player.position}
    - 現在の日付: {player.current_date}

    【シーン】
    - 状況: {topic}

    【執筆方針】
    - 一人称視点（「僕」）で書くこと。
    - 地の文と会話文をバランスよく混ぜること。
    - 感情・身体感覚・周囲の空気感を具体的に描写すること
      （例: 汗の匂い、スタンドのざわめき、スパイクの音、視線の重さなど）。
    - ご都合主義ではなく、等身大のリアリティのあるトーン。
    - 分量の目安は 400〜800字程度。

    Output JSON ONLY:
    {{
        "story": "ここに日本語テキストを入れる。改行は \\n を使う。"
    }}
    """
    res = call_gemini(prompt)
    return res.get("story", "") if res else ""


def generate_next_event(player):
    sorted_npcs = sorted(player.npcs, key=lambda x: abs(float(x.relation)), reverse=True)[:5]
    npcs_txt = ", ".join([f"{n.role}:{n.name}({n.relation})" for n in sorted_npcs]) or "重要な人間関係はまだ少ない"

    next_match = None
    if player.schedule:
        sorted_sched = sorted(player.schedule, key=lambda x: x.get('date', '9999'))
        for m in sorted_sched:
            if m.get('date', '9999') >= str(player.current_date):
                next_match = m
                break
    schedule_info = (
        f"次戦: {next_match.get('date')} vs {next_match.get('opponent','未定')}"
        if next_match else "次戦予定なし"
    )

    prompt = f"""
    あなたはリアル志向のサッカー小説家兼ゲームマスターです。

    【プレイヤー情報】
    - 名前: {player.name}
    - 所属: {player.team_name}
    - カテゴリ: {player.team_category}
    - ポジション: {player.position}
    - 年齢: {player.age}
    - 現在日付: {player.current_date}
    - 現在CA: {player.ca:.2f}, PA: {player.pa:.2f}
    - HP: {player.hp}, MP: {player.mp}

    【文脈】
    - 直近スケジュール情報: {schedule_info}
    - 関係性が強い/こじれているNPC一覧: {npcs_txt}

    【タスク】
    - 「今このタイミングで起こりうる、等身大のイベント」を1つ作りなさい。
      - 例: 練習後のロッカーでの会話 / 寮での夜の独り時間 / 恋人とのすれ違い /
            監督との面談 / 次戦メンバー発表 など。
      - サッカー要素と生活要素が両方少しずつ絡むのが理想。

    【表現ルール】
    - title: 20文字以内の短いイベント名。
    - description: 400〜900字程度の本文。
      - 一人称の地の文＋会話文。
      - 感情・身体感覚・空気感を丁寧に描写。
      - 直近の試合・序列・練習への不安や期待なども自然に織り込んでよい。

    【選択肢】
    - choices は必ず3つ。
    - text: プレイヤーが即座に選べる行動（短文）。
    - hint: その行動がプレイヤーのキャリアに与えそうな影響のニュアンスを一言で。

    Output JSON ONLY:
    {{
      "title": "短いイベント名",
      "description": "本文テキスト。改行は \\n を使う。",
      "choices": [
        {{"text":"...", "hint":"..." }},
        {{"text":"...", "hint":"..." }},
        {{"text":"...", "hint":"..." }}
      ]
    }}
    """
    res = call_gemini(prompt)
    if not res:
        return {
            "title": "静かな一日",
            "description": "今日は大きな出来事はなかった。\\n\\n寮の部屋で一人、次の練習と試合のことを考えながらストレッチをしている。",
            "choices": [{"text": "軽く自主練に出る", "hint": "わずかに成長"}]
        }
    return res


def resolve_action(player, choice_text, event_desc):
    prompt = f"""
    あなたはリアル志向のサッカーコーチ兼ストーリーテラーです。

    【前提状況】
    - イベント本文: {event_desc}
    - プレイヤーの選択: {choice_text}

    【選手情報】
    - 名前: {player.name}
    - 所属: {player.team_name}
    - カテゴリ: {player.team_category}
    - ポジション: {player.position}
    - 年齢: {player.age}
    - 現在日付: {player.current_date}
    - 現在CA: {player.ca:.2f}, PA: {player.pa:.2f}
    - HP: {player.hp}, MP: {player.mp}

    【タスク】
    1. この選択をした結果、その日の出来事がどう展開したかを
       一人称視点で 400〜800字程度のストーリー(result_story)にまとめること。
       - 練習・試合内容、周囲の反応、自分の感情や身体感覚、
         帰り道や夜のベッドの中での反芻までを描いてよい。
       - 「成功した／失敗した」だけでなく、モヤモヤや学びも描写すること。

    2. その日のサッカー活動強度(Base)と、体感採点に対応するPerformanceを決めること。
       - Base: TRや試合、自主練の合計。だいたい 0.01〜0.30 の範囲。
       - Performance: 0.6〜1.5（標準は0.8〜1.0）

    3. 成長させるべき能力(grow_stats)を2〜6個程度選び、
       それぞれ 0.01〜0.30 程度の微小な成長値を割り当てること。
       - 行動内容に整合的な能力のみを上げること
         （例: ハードなフィジカルトレ → Stamina, Strength など）。
       - JSONのキーは game_data.WEIGHTS にある能力名と一致させること。

    4. 必要に応じて人間関係relation_changeも1件だけ指定してよい。
       - role: 関係性のラベル（例: "監督", "チームメイト", "恋人" など）
       - val: -10〜+10の整数。

    【出力フォーマット】
    以下のJSONだけを出力してください:

    {{
      "result_story": "本文。改行は \\n を使う。",
      "grow_stats": {{
         "Decisions": 0.05,
         "Acceleration": 0.10
      }},
      "hp_cost": 10,
      "mp_cost": 5,
      "relation_change": {{
         "role": "監督",
         "val": 3
      }},
      "base": 0.12,
      "performance": 0.9
    }}
    """
    return call_gemini(prompt)


# ==========================================
# メインレイアウト
# ==========================================

if st.session_state.game_phase == "start":
    st.title("⚽ Football Career AI")
    if st.button("エントリーシートを書く"):
        st.session_state.game_phase = "create"
        st.rerun()

# --- 1. 入力フェーズ ---
elif st.session_state.game_phase == "create":
    st.title("📝 選手エントリーシート")
    if not api_key:
        st.error("← サイドバー(左上)を開いてAPIキーを設定してください")
        st.stop()

    with st.expander("基本情報", expanded=True):
        c1, c2 = st.columns(2)
        name = c1.text_input("名前", "佐藤 蹴斗")
        nickname = c2.text_input("ニックネーム", "シュート")
        c3, c4 = st.columns(2)
        start_date = c3.date_input("開始日時", datetime.date(2024, 4, 1))
        dob = c4.date_input("生年月日", datetime.date(2006, 4, 1))
        age = (start_date - dob).days // 365
        c5, c6 = st.columns(2)
        height = c5.number_input("身長 (cm)", 160, 200, 175)
        weight = c6.number_input("体重 (kg)", 50, 100, 68)
        foot = st.selectbox("利き足", ["右", "左", "両"])

    with st.expander("詳細設定", expanded=True):
        history = st.text_area("経歴", "高校時代は無名だったが...")
        style = st.text_area("特徴", "足は速いが、スタミナがない。")
        relation_desc = st.text_area("人間関係", "父は反対している。")
        money_desc = st.text_area("経済状況", "実家は太い。")
        housing = st.text_input("住居", "寮")

        c_pa, c_tm, c_pos = st.columns(3)
        target_pa = c_pa.slider("希望PA", 1, 200, 150)
        init_team = c_tm.text_input("初期チーム", "慶應義塾大学ソッカー部C2チーム")
        position = c_pos.selectbox(
            "ポジション",
            ["CF", "RWG", "LWG", "OMF", "CMF", "DMF", "RSB", "LSB", "CB", "GK"]
        )

    if st.button("データ生成開始"):
        with st.spinner(f"チームデータを生成中... ({selected_model})"):
            cat = determine_category(init_team)
            prof = {
                "name": name,
                "age": age,
                "height": height,
                "weight": weight,
                "foot": foot,
                "history": history,
                "style": style,
                "relations": relation_desc,
                "economics": money_desc,
                "housing": housing,
                "pa": target_pa,
                "team": init_team
            }
            res = create_initial_data(prof, cat, start_date)

            if res:
                # 将来的に need_questions を見て追加質問フローを挟む余地を残しておく
                st.session_state.temp_data = {
                    "base": prof,
                    "cat": cat,
                    "start_date": str(start_date),
                    "stats": res,
                    "position": position,
                    "foot": foot,
                }
                st.session_state.game_phase = "review_stats"
                st.rerun()

# --- 2. Review Stats ---
elif st.session_state.game_phase == "review_stats":
    st.title("📊 能力値・人間関係の確認")
    st.info("AIが生成したデータを編集して確定してください。")

    data = st.session_state.temp_data["stats"]

    # Gemini が返した attributes に、FM準拠の全キーをマージして 10.0 で初期化する
    raw_attr = data.get("attributes", {}) or {}
    base_attrs = {k: 10.0 for k in game_data.WEIGHTS.keys()}
    for k in base_attrs.keys():
        if k in raw_attr and raw_attr[k] is not None:
            base_attrs[k] = float(raw_attr[k])

    c1, c2 = st.columns(2)
    with c1:
        st.write("能力値（FM準拠・全項目）")
        edited_attr = st.data_editor(
            pd.DataFrame([base_attrs]),
            use_container_width=True
        )
        ca_dict = edited_attr.to_dict(orient='records')[0]
        total_score = sum(ca_dict[key] * game_data.WEIGHTS[key] for key in game_data.WEIGHTS.keys())
        ca_preview = (total_score / game_data.THEORETICAL_MAX_SCORE) * 200
        st.caption(f"現在の推定CA: {ca_preview:.2f}")

    with c2:
        st.write("人間関係")
        edited_npcs = st.data_editor(
            pd.DataFrame(data.get("npcs", [])),
            num_rows="dynamic"
        )

        st.write("経済")
        funds = st.number_input("所持金", value=safe_int(data.get("funds", 100000)))
        salary = st.number_input("年俸", value=safe_int(data.get("salary", 0)))

    if st.button("確定して入団"):
        prof = st.session_state.temp_data["base"]
        start_d = datetime.datetime.strptime(
            st.session_state.temp_data["start_date"],
            "%Y-%m-%d"
        ).date()
        category = st.session_state.temp_data.get("cat", "Professional")
        raw_position = st.session_state.temp_data.get("position", "MF")
        foot = st.session_state.temp_data.get("foot", "")
        pos_val = convert_position_by_foot(category, raw_position, foot)

        p = game_data.Player(
            prof["name"],
            pos_val,
            prof["age"],
            attributes=edited_attr.to_dict(orient='records')[0],
            funds=funds,
            salary=salary,
            team_name=prof["team"],
            start_date=start_d,
            team_category=category,
            pa=float(st.session_state.temp_data["base"].get("pa", 150)),
        )

        for _, row in edited_npcs.iterrows():
            p.add_npc(
                game_data.NPC(
                    row.get("name"),
                    row.get("role"),
                    safe_float(row.get("relation")),
                    row.get("description")
                )
            )

        st.session_state.player = p

        # カテゴリに応じて次フェーズを分岐
        cat_raw = p.team_category or ""
        cat_norm = cat_raw.lower()

        if ("professional" in cat_norm) or ("pro" in cat_norm):
            st.session_state.game_phase = "agent_choice"
        elif "youth" in cat_norm:
            st.session_state.game_phase = "agent_choice"
        elif ("highschool" in cat_norm) or ("高校" in cat_raw):
            st.session_state.game_phase = "team_intro"
        elif ("university" in cat_norm) or ("大学" in cat_raw):
            st.session_state.game_phase = "team_intro"
        else:
            st.session_state.game_phase = "team_intro"

        st.rerun()

# --- 2.5 代理人選択 ---
elif st.session_state.game_phase == "agent_choice":
    p = st.session_state.player
    st.title("🤝 代理人の選択")

    st.write(
        "これからのキャリアを考えて、代理人（エージェント）を付けるかどうかを決めます。"
        "ここでは物語とニュアンスだけに影響し、まだ契約条件ロジックには直結させません。"
    )

    default_index = 2 if p.team_category == "Professional" else 1
    option = st.radio(
        "あなたの現在の状況に一番近いものを選んでください。",
        ["付けない", "身近な人が兼ねる（家族・先輩など）", "専任のエージェントが付いている"],
        index=default_index
    )

    if st.button("決定して次へ"):
        # とりあえずプレイヤーオブジェクトにぶら下げる（セーブは後で考える）
        p.agent_type = option

        if p.team_category == "Professional":
            st.session_state.game_phase = "pro_contract"
        else:
            # ユースはすぐに入団会見へ
            st.session_state.game_phase = "story_intro"

        st.rerun()

# --- 2.6 プロ限定：契約交渉 ---
elif st.session_state.game_phase == "pro_contract":
    p = st.session_state.player
    st.title("📝 契約交渉")

    if "pro_contract_story" not in st.session_state:
        with st.spinner("契約交渉のシーンを生成中..."):
            st.session_state.pro_contract_story = generate_story(
                p,
                "代理人（または自分）とクラブが年俸や契約年数について詰めている契約交渉のシーン"
            )

    st.markdown(st.session_state.pro_contract_story)

    # いまは条件いじらず、演出だけ
    if st.button("契約にサインする"):
        del st.session_state.pro_contract_story
        st.session_state.game_phase = "story_intro"
        st.rerun()

# --- 3. Story Intro（プロ・ユースの入団会見） ---
elif st.session_state.game_phase == "story_intro":
    p = st.session_state.player
    st.title("🎬 入団")

    if "intro_text" not in st.session_state:
        with st.spinner("物語を生成中..."):
            if p.team_category in ["Professional", "Youth"]:
                topic = "入団会見とメディア向けフォトセッション"
            else:
                topic = "部室での自己紹介"
            st.session_state.intro_text = generate_story(p, topic)

    st.markdown(st.session_state.intro_text)

    if st.button("チームメイトと対面する"):
        # プロ/ユースはここからチーム内自己紹介へ
        st.session_state.game_phase = "team_intro"
        del st.session_state.intro_text
        st.rerun()

# --- 3.5 チーム内自己紹介（全カテゴリ共通） ---
elif st.session_state.game_phase == "team_intro":
    p = st.session_state.player
    st.title("👥 チーム内自己紹介")

    if "intro_text" not in st.session_state:
        with st.spinner("自己紹介シーンを生成中..."):
            if p.team_category in ["University", "HighSchool"]:
                topic = "部室での自己紹介と、先輩・同級生との最初の会話"
            elif p.team_category in ["Professional", "Youth"]:
                topic = "ロッカールームでの自己紹介と、チームメイトとの最初のやり取り"
            else:
                topic = "チームメイトへの自己紹介"

            st.session_state.intro_text = generate_story(p, topic)

    st.markdown(st.session_state.intro_text)

    if st.button("チームメイト一覧を確認する"):
        del st.session_state.intro_text
        st.session_state.game_phase = "review_team"
        st.rerun()

# --- 4. Review Team ---
elif st.session_state.game_phase == "review_team":
    st.title("👥 チームメイト確認")
    p = st.session_state.player

    if not p.team_members:
        with st.spinner("チームデータを生成中..."):
            # 念のためここで再度カテゴリをチーム名から強制判定
            p.team_category = determine_category(p.team_name)

            res = create_team_data(p.team_name, p.team_category, p.current_date)
            if res:
                p.formation = res.get("formation", "4-4-2")
                members, fmt = game_data.TeamGenerator.generate_teammates(
                    p.team_category,
                    p.formation,
                    res.get("real_players", [])
                )
                p.team_members = members
                game_data.save_game(p)

    st.info("メンバーを編集し、確定ボタンを押すと序列が計算されます。")

    data = []
    for m in p.team_members:
        data.append({
            "No": m.number,
            "Pos": m.position,
            "Name": m.name,
            "Age": m.age,
            "CA": float(m.ca),
            "PA": float(getattr(m, "pa", 0)),
            "Value": int(getattr(m, "value", 0)),
            "Grade": getattr(m, "grade", "") if p.team_category in ("HighSchool", "University") else ""
        })
    edited_df = st.data_editor(
        pd.DataFrame(data),
        num_rows="dynamic",
        use_container_width=True
    )

    if st.button("メンバー確定 & 序列計算"):
        raw_members = []
        for _, row in edited_df.iterrows():
            raw_members.append({
                "number": row.get("No"),
                "position": row.get("Pos"),
                "name": row.get("Name"),
                "age": row.get("Age"),
                "ca": row.get("CA"),
                "pa": row.get("PA"),
                "value": row.get("Value"),
                "grade": row.get("Grade", "")
            })

        p.team_members = game_data.TeamGenerator.finalize_team(
            p.team_category,
            p.formation,
            raw_members
        )
        p.update_hierarchy()
        game_data.save_game(p)

        st.session_state.game_phase = "story_hierarchy"
        st.rerun()

# --- 5. Story Hierarchy ---
elif st.session_state.game_phase == "story_hierarchy":
    p = st.session_state.player
    st.title("📋 序列発表")

    my_member = next((m for m in p.team_members if m.name == p.name), None)
    my_rank = getattr(my_member, "hierarchy", None)
    rank_label = f"{my_rank}位 / {len(p.team_members)}" if my_rank else "順位計測中"
    st.success(f"あなたの現在の序列: **{rank_label}**")

    my_idx = next((i for i, m in enumerate(p.team_members) if m.name == p.name), 0)
    rivals = p.team_members[max(0, my_idx - 2): min(len(p.team_members), my_idx + 3)]
    st.write("### ポジション争い")
    for i, m in enumerate(rivals, start=max(1, my_idx - 1)):
        rank = getattr(m, "hierarchy", i)
        mark = "👈 YOU" if m.name == p.name else ""
        st.write(f"{rank}位 | {m.name} (CA:{m.ca:.1f}) {mark}")

    # ★変更：まずはチームの週間スケジュールを見に行く
    if st.button("チームの週間スケジュールを見る"):
        st.session_state.game_phase = "team_weekly_plan"
        st.rerun()
# --- 5.5 Team Weekly Plan ---
elif st.session_state.game_phase == "team_weekly_plan":
    p = st.session_state.player
    st.title("🗓 チームの週間スケジュール")

    # まだ作っていなければ Gemini で生成
    if not getattr(p, "team_weekly_plan", None):
        with st.spinner("チームの週間スケジュールを作成中..."):
            res = create_team_weekly_plan(p.team_name, p.team_category)
            if res:
                p.team_weekly_plan = res.get("plan", [])
                game_data.save_game(p)

    st.info("コーチ陣が決めたベースの週間スケジュールです。必要なら編集してください。")

    if p.team_weekly_plan:
        df_plan = pd.DataFrame(p.team_weekly_plan)
    else:
        df_plan = pd.DataFrame(columns=["weekday", "morning", "afternoon", "evening"])

    edited_plan = st.data_editor(
        df_plan,
        num_rows="dynamic",
        use_container_width=True
    )

    if st.button("確定して次へ"):
        p.team_weekly_plan = edited_plan.to_dict(orient="records")
        game_data.save_game(p)

        # ★カテゴリ・年齢に応じて遷移先を分岐
        if p.team_category == "University":
            st.session_state.game_phase = "univ_timetable"
        elif p.team_category in ["HighSchool", "Youth"] and p.age <= 18:
            st.session_state.game_phase = "school_timetable"
        else:
            # 社会人・プロなどはそのまま年間日程へ
            st.session_state.game_phase = "review_schedule"

        st.rerun()

# --- 5.6 School Timetable (HighSchool / Youth <=18) ---
elif st.session_state.game_phase == "school_timetable":
    p = st.session_state.player
    st.title("🏫 学校の時間割")

    if not getattr(p, "school_timetable", None):
        with st.spinner("学校の時間割を作成中..."):
            res = create_school_timetable(p)
            if res:
                p.school_timetable = res.get("timetable", [])
                game_data.save_game(p)

    st.info("担任や進路指導の先生と相談して決めた、あなたの学校の時間割です。必要なら少し編集してください。")

    if p.school_timetable:
        df_tt = pd.DataFrame(p.school_timetable)
    else:
        df_tt = pd.DataFrame(columns=["weekday", "p1", "p2", "p3", "p4", "p5", "p6"])

    edited_tt = st.data_editor(
        df_tt,
        num_rows="dynamic",
        use_container_width=True
    )

    if st.button("確定して年間日程へ進む"):
        p.school_timetable = edited_tt.to_dict(orient="records")
        game_data.save_game(p)
        st.session_state.game_phase = "review_schedule"
        st.rerun()

# --- 5.7 Univ Timetable (履修登録) ---
elif st.session_state.game_phase == "univ_timetable":
    p = st.session_state.player
    st.title("🎓 履修登録（時間割）")

    if not getattr(p, "school_timetable", None):
        with st.spinner("履修時間割を作成中..."):
            res = create_univ_timetable(p)
            if res:
                # 大学でも school_timetable にまとめて持たせる
                p.school_timetable = res.get("timetable", [])
                game_data.save_game(p)

    st.info("サッカー部の予定と両立できるように、AIが提案した履修時間割です。必修/選択と受講形態（オンライン/オンデマンド/オフライン）も編集できます。")

    if p.school_timetable:
        df_tt = pd.DataFrame(p.school_timetable)
    else:
        df_tt = pd.DataFrame(
            columns=[
                "weekday",
                "p1",
                "p1_required",
                "p1_delivery",
                "p2",
                "p2_required",
                "p2_delivery",
                "p3",
                "p3_required",
                "p3_delivery",
                "p4",
                "p4_required",
                "p4_delivery",
                "p5",
                "p5_required",
                "p5_delivery",
            ]
        )

    edited_tt = st.data_editor(
        df_tt,
        num_rows="dynamic",
        use_container_width=True
    )

    if st.button("確定して年間日程へ進む"):
        p.school_timetable = edited_tt.to_dict(orient="records")
        game_data.save_game(p)
        st.session_state.game_phase = "review_schedule"
        st.rerun()


# --- 6. Review Schedule ---
elif st.session_state.game_phase == "review_schedule":
    st.title("📅 スケジュール確認")
    p = st.session_state.player

    if not p.schedule:
        with st.spinner("リーグ日程を編成中..."):
            res = create_schedule_data(p.team_name, p.team_category, p.current_date.year)
            if res:
                # 大会メタ情報（今はまだ画面には出さないが、今後の順位表などで使う）
                if hasattr(p, "competitions"):
                    p.competitions = res.get("competitions", [])
                # 実際に使う年間日程
                p.schedule = res.get("schedule", [])
                if p.team_weekly_plan:
                    aligned, changed = align_weekly_plan_with_schedule(p.team_weekly_plan, p.schedule)
                    if changed:
                        p.team_weekly_plan = aligned
                        st.info("年間試合日程に合わせて週間スケジュールの試合日を同期しました。")
                game_data.save_game(p)

    edited_sched = st.data_editor(
        pd.DataFrame(p.schedule),
        num_rows="dynamic",
        use_container_width=True
    )

    if st.button("日程確定 & シーズン開幕"):
        p.schedule = edited_sched.to_dict(orient='records')
        if p.team_weekly_plan:
            aligned, changed = align_weekly_plan_with_schedule(p.team_weekly_plan, p.schedule)
            if changed:
                p.team_weekly_plan = aligned
                st.info("編集後の日程に合わせて週間スケジュールを調整しました。")
        game_data.save_game(p)
        st.session_state.game_phase = "story_schedule"
        st.rerun()


# --- 7. Story Schedule ---
elif st.session_state.game_phase == "story_schedule":
    p = st.session_state.player
    st.title("⚽ シーズン開幕")
    if p.schedule:
        opener = p.schedule[0]
        st.info(f"開幕戦は **{opener.get('date')}** vs **{opener.get('opponent')}** です！")

    if p.schedule:
        outline = summarize_annual_outline(p.schedule, p.current_date.year)
        st.subheader("ざっくり年間スケジュール")
        st.dataframe(pd.DataFrame(outline), use_container_width=True)

    if st.button("日常パートへ"):
        st.session_state.game_phase = "main"
        ev = generate_next_event(p)
        st.session_state.current_event = ev
        st.rerun()

# --- 8. Main ---
elif st.session_state.game_phase == "main":
    p = st.session_state.player
    p.update_hierarchy()

    st.markdown(
        f"## ⚽ {p.name} <small>({p.team_name})</small>",
        unsafe_allow_html=True
    )
    col_main, col_chat = st.columns([7, 3])

    # =========================
    # 左カラム：ステータス & 各種メニュー
    # =========================
    with col_main:
        c1, c2, c3, c4, c5, c6 = st.columns(6)

        # Date
        date_label = f"{p.current_date} ({p.current_date.strftime('%a')})"
        render_stat(c1, "Date", date_label)

        # Funds（長い桁数でも折り返して表示）
        render_stat(c2, "Funds (¥)", f"{p.funds:,}")

        # CA / PA
        render_stat(c3, "CA / PA", f"{p.ca:.2f} / {p.pa:.2f}")

        # Market Value（€）
        render_stat(c4, "Value (€)", f"{int(p.value):,}")

        # HP / MP
        render_stat(c5, "HP", f"{p.hp}")
        render_stat(c6, "MP", f"{p.mp}")

        # 生活水準の即時切替（HPやコストに影響）
        living_levels = {"節約": 1000, "標準": 3000, "充実": 8000}
        new_level = st.select_slider(
            "生活水準 (1日コスト)",
            options=list(living_levels.keys()),
            value=getattr(p, "living_standard", "標準"),
            format_func=lambda x: f"{x} / ¥{living_levels[x]:,}/day"
        )
        if new_level != p.living_standard:
            p.living_standard = new_level
            game_data.save_game(p)
            st.toast("生活水準を更新しました")

        tab_attr, tab_roster, tab_standings, tab_year, tab_week, tab_timetable, tab_rel, tab_shop, tab_transfer = st.tabs(
            ["📊 能力/適性", "👥 名簿", "📈 順位表", "📅 年間日程", "🗓 週間日程", "⏰ 時間割", "🤝 人間関係", "🛍️ ショップ", "📩 移籍"]
        )

        # ========== タブ: 能力 / ポジション適性 ==========
        with tab_attr:
            # 能力値一覧
            attr_rows = [
                {"Ability": k, "Value": round(v, 2)}
                for k, v in p.attributes.items()
            ]
            if attr_rows:
                st.write("### 能力値一覧")
                st.dataframe(
                    pd.DataFrame(attr_rows).sort_values("Ability"),
                    use_container_width=True,
                    height=400
                )
            else:
                st.info("能力値データがありません。")

            # ポジション適性
            if hasattr(p, "position_apt"):
                st.write("### ポジション適性")
                apt_rows = [
                    {"Position": pos, "Aptitude": round(val, 2)}
                    for pos, val in p.position_apt.items()
                ]
                st.dataframe(
                    pd.DataFrame(apt_rows).sort_values("Position"),
                    use_container_width=True,
                    height=300
                )
            else:
                st.info("ポジション適性データがありません。")

        # ========== タブ: 名簿 ==========
        with tab_roster:
            data = []
            sorted_members = sorted(
                p.team_members,
                key=lambda x: float(x.ca) if getattr(x, "ca", None) is not None else 0,
                reverse=True
            )
            for m in sorted_members:
                is_me = (m.name == p.name)
                row = {
                    "No": m.number,
                    "Pos": m.position,
                    "Name": f"★ {m.name}" if is_me else m.name,
                    "CA": f"{getattr(m, 'ca', 0):.1f}",
                    "PA": f"{getattr(m, 'pa', 0):.1f}",
                    "Hierarchy": getattr(m, "hierarchy", ""),
                    "Foot": getattr(m, "foot", ""),
                    "Height": getattr(m, "height_cm", getattr(m, "height", "")),
                    "Value": f"€{getattr(m, 'value', 0):,}",
                    "Grade": getattr(m, "grade", ""),
                    "TransferFlag": getattr(m, "transfer_flag", False),
                }
                # 高校・大学のときは年齢も見えた方が嬉しいので常に入れる
                row["Age"] = getattr(m, "age", "")
                data.append(row)

            if data:
                edited_df = st.data_editor(
                    pd.DataFrame(data),
                    height=500,
                    use_container_width=True,
                    num_rows="dynamic"
                )
                if st.button("名簿を更新"):
                    new_members = []
                    for _, row in edited_df.iterrows():
                        try:
                            new_members.append(
                                game_data.TeamMember(
                                    name=str(row.get("Name", "")).replace("★ ", ""),
                                    position=row.get("Pos", ""),
                                    number=int(row.get("No", 0)),
                                    age=int(row.get("Age", 0)) if row.get("Age", "") != "" else 0,
                                    ca=float(str(row.get("CA", 0)).replace("★", "")),
                                    pa=float(str(row.get("PA", 0)).replace("★", "")),
                                    height_cm=int(row.get("Height", 0)) if row.get("Height", "") != "" else 0,
                                    value=safe_int(row.get("Value", 0)),
                                    grade=row.get("Grade", ""),
                                    transfer_flag=bool(row.get("TransferFlag", False)),
                                )
                            )
                        except Exception:
                            continue
                    if new_members:
                        p.team_members = new_members
                        p.update_hierarchy()
                        game_data.save_game(p)
                        st.success("名簿を更新しました")
            else:
                st.info("チームメンバーがまだいません。")

        # ========== タブ: 順位表 ==========
        with tab_standings:
            st.write("### 順位表（編集可）")
            standings = p.competitions or []
            if not standings:
                # 簡易初期値：スケジュールから大会名を拾う
                comp_names = list({m.get("competition", "") for m in p.schedule if m.get("competition")})
                if not comp_names:
                    comp_names = ["リーグ"]
                standings = [
                    {"competition": comp, "team": p.team_name, "played": 0, "win": 0, "draw": 0, "loss": 0, "points": 0}
                    for comp in comp_names
                ]

            df_st = pd.DataFrame(standings)
            edited_st = st.data_editor(df_st, num_rows="dynamic", use_container_width=True)
            if st.button("順位表を保存"):
                p.competitions = edited_st.to_dict(orient="records")
                game_data.save_game(p)
                st.toast("順位表を保存しました")

        # ========== タブ: 年間日程 ==========
        with tab_year:
            if p.schedule:
                st.dataframe(
                    pd.DataFrame(p.schedule),
                    use_container_width=True,
                    height=500
                )
            else:
                st.info("年間日程がまだ編成されていません。")

        # ========== タブ: 週間日程（現在日付から7日分） ==========
        with tab_week:
            from datetime import timedelta

            rows = []
            for i in range(7):
                d = p.current_date + timedelta(days=i)
                d_str = str(d)
                match = None
                for m in p.schedule or []:
                    if m.get("date") == d_str:
                        match = m
                        break
                if match:
                    kind = "試合"
                    detail = f"vs {match.get('opponent', '')} ({'H' if match.get('home') else 'A'})"
                else:
                    kind = "トレーニング / 休養"
                    detail = "-"
                rows.append({
                    "Date": d_str,
                    "Type": kind,
                    "Detail": detail
                })

            st.dataframe(
                pd.DataFrame(rows),
                use_container_width=True,
                height=300
            )
            st.caption("※ ざっくりプレビュー。詳細ロジックは今後拡張余地あり。")

        # ========== タブ: 時間割 ==========
        with tab_timetable:
            st.write("### 時間割（カテゴリ別の目安）")
            if p.team_category in ["University", "HighSchool", "Youth"]:
                if p.team_category == "University":
                    st.markdown(
                        """
**大学生イメージ（平日）**

- 07:00 起床・朝食  
- 09:00〜12:00 授業 / 自習  
- 12:00〜13:00 昼食  
- 13:00〜16:00 授業 / 課題 / バイト  
- 17:00〜20:00 部活動（トレーニング・ミーティング）  
- 21:00〜24:00 自由時間 / 復習 / リカバリー
                        """
                    )
                elif p.team_category == "HighSchool":
                    st.markdown(
                        """
**高校生イメージ（平日）**

- 07:00 起床・登校  
- 08:30〜15:30 授業  
- 16:00〜19:00 部活動（トレーニング・試合）  
- 20:00〜22:30 夕食・宿題・自由時間
                        """
                    )
                else:  # Youth
                    st.markdown(
                        """
**ユース（U18）イメージ**

- 08:30〜13:00 学校  
- 15:00〜18:00 クラブトレーニング  
- 19:00〜22:00 夕食・宿題・リカバリー
                        """
                    )
            else:
                st.markdown(
                    """
**プロカテゴリ**

- 個人スケジュールはクラブとエージェントの裁量が大きいため、  
  ここでは詳細時間割の管理は行っていません（今後実装余地あり）。
                    """
                )

        # ========== タブ: 人間関係 ==========
        with tab_rel:
            rel_rows = []
            for n in p.npcs or []:
                rel_rows.append({
                    "Role": n.role,
                    "Name": n.name,
                    "Relation": n.relation,
                    "Description": n.description
                })
            df_rel = pd.DataFrame(rel_rows) if rel_rows else pd.DataFrame(columns=["Role", "Name", "Relation", "Description"])
            edited_rel = st.data_editor(df_rel, num_rows="dynamic", use_container_width=True, height=400)
            if st.button("人間関係を更新"):
                new_npcs = []
                for _, row in edited_rel.iterrows():
                    if not row.get("Name"):
                        continue
                    new_npcs.append(game_data.NPC(
                        role=row.get("Role", ""),
                        name=row.get("Name", ""),
                        relation=safe_float(row.get("Relation", 0)),
                        description=row.get("Description", ""),
                    ))
                p.npcs = new_npcs
                game_data.save_game(p)
                st.success("人間関係を更新しました")

        # ========== タブ: ショップ ==========
        with tab_shop:
            st.write("アイテムショップ")
            items = [
                {"name": "プロテイン", "price": 5000},
                {"name": "戦術書", "price": 10000}
            ]
            for item in items:
                if st.button(f"{item['name']} (¥{item['price']})", key=f"shop_{item['name']}"):
                    if p.funds >= item['price']:
                        p.funds -= item['price']
                        p.hp = min(100, p.hp + 30)
                        st.toast("購入")
                        game_data.save_game(p)
                        st.rerun()
                    else:
                        st.error("金欠")

        # ========== タブ: 移籍 ==========
        with tab_transfer:
            st.write("### 受信オファー一覧")
            if p.transfer_offers:
                df = pd.DataFrame(p.transfer_offers)
                st.dataframe(df, use_container_width=True, height=300)
                for idx, offer in enumerate(p.transfer_offers):
                    st.markdown(f"**{offer.get('club')}** ({offer.get('league')}) - 状態: {offer.get('status')}")
                    cols = st.columns(3)
                    if cols[0].button("承諾", key=f"accept_offer_{idx}"):
                        offer["status"] = "accepted"
                        apply_transfer(p, offer)
                        game_data.save_game(p)
                        st.success(f"{offer.get('club')} に加入しました！")
                        st.rerun()
                    if cols[1].button("保留", key=f"hold_offer_{idx}"):
                        offer["status"] = "held"
                        game_data.save_game(p)
                        st.info("オファーを保留にしました。")
                    if cols[2].button("辞退", key=f"decline_offer_{idx}"):
                        offer["status"] = "declined"
                        game_data.save_game(p)
                        st.warning("オファーを辞退しました。")
            else:
                st.info("現在オファーはありません。")

    # =========================
    # 右カラム：ログ & 行動・イベント
    # =========================
    with col_chat:
        # 先にイベント状態だけ取得しておく
        ev = st.session_state.current_event

        # 新着オファー通知
        notice = st.session_state.transfer_notice
        if notice:
            with st.warning("📩 新しい移籍オファー", icon="📨"):
                st.write(offer_summary_text(notice))
                c1, c2, c3 = st.columns(3)
                if c1.button("承諾", key="notice_accept"):
                    notice["status"] = "accepted"
                    apply_transfer(p, notice)
                    st.session_state.transfer_notice = None
                    game_data.save_game(p)
                    st.success(f"{notice.get('club')} に加入しました！")
                    st.rerun()
                if c2.button("保留", key="notice_hold"):
                    notice["status"] = "held"
                    st.session_state.transfer_notice = None
                    game_data.save_game(p)
                    st.info("オファーを保留しました。移籍タブで確認できます。")
                if c3.button("辞退", key="notice_decline"):
                    notice["status"] = "declined"
                    st.session_state.transfer_notice = None
                    game_data.save_game(p)
                    st.warning("オファーを辞退しました。")

        # =========================
        # 上：ログ表示
        # =========================
        st.markdown("### 📜 ログ")
        with st.container(height=400):
            for m in st.session_state.messages:
                st.chat_message(m["role"]).write(m["content"])

        # =========================
        # 下：行動 / イベント
        # =========================
        st.markdown("### 🏃 行動 / イベント")

        # イベントがない → 「時間を進める」ボタンだけ
        if not ev:
            if st.button("時間を進める", key="advance_time_main"):
                with st.spinner("イベント生成中..."):
                    ev_new = generate_next_event(p)
                    st.session_state.current_event = ev_new
                    st.rerun()
        else:
            # イベント表示
            if isinstance(ev, str):
                ev = {"title": "Ev", "description": ev, "choices": []}
            st.markdown(f"**{ev.get('title')}**")
            st.info(ev.get('description'))

            # 選択肢ボタン
            choices = ev.get('choices', [])
            if choices:
                cols = st.columns(len(choices))
                for i, c in enumerate(choices):
                    if cols[i].button(c.get('text'), help=c.get('hint'), key=f"choice_{i}"):
                        res = resolve_action(p, c.get('text'), ev.get('description'))
                        if res:
                            # ログ追加
                            st.session_state.messages.append({
                                "role": "assistant",
                                "content": f"**{c.get('text')}**\n{res.get('result_story')}"
                            })

                            # 成長処理
                            grow_stats = res.get("grow_stats", {})
                            base_intensity = safe_float(res.get("base", 0.0))
                            performance = safe_float(res.get("performance", 0.8))
                            if base_intensity <= 0:
                                base_intensity = 0.05

                            target_ca_gain = p.compute_daily_growth_ca(
                                base_intensity,
                                performance
                            )

                            raw_gain = 0.0
                            if grow_stats:
                                tmp_attrs = p.attributes.copy()
                                for k, v in grow_stats.items():
                                    if k in tmp_attrs:
                                        tmp_attrs[k] = min(
                                            20.0,
                                            tmp_attrs[k] + safe_float(v)
                                        )
                                tmp_total = sum(
                                    tmp_attrs[key] * game_data.WEIGHTS[key]
                                    for key in game_data.WEIGHTS.keys()
                                )
                                tmp_ca = (tmp_total / game_data.THEORETICAL_MAX_SCORE) * 200
                                raw_gain = max(0.0, tmp_ca - p.ca)

                            scale = 1.0
                            if target_ca_gain > 0 and raw_gain > 0:
                                scale = target_ca_gain / raw_gain

                            for k, v in grow_stats.items():
                                p.grow_attribute(k, safe_float(v) * scale)

                            p.hp -= safe_int(res.get("hp_cost", 0))
                            p.mp -= safe_int(res.get("mp_cost", 0))
                            p.advance_day(1)
                            offer = maybe_generate_transfer_offer(p)
                            if offer:
                                st.session_state.transfer_notice = offer
                                st.session_state.messages.append({
                                    "role": "assistant",
                                    "content": f"📩 新しいオファー\n{offer_summary_text(offer)}"
                                })
                            st.session_state.current_event = None
                            game_data.save_game(p)
                            st.rerun()

        # 自由記述アクション
        if ev:
            free = st.chat_input("自由記述で行動する", key="free_action")
            if free:
                res = resolve_action(p, free, ev.get('description'))
                if res:
                    st.session_state.messages.append({"role": "user", "content": free})
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": res.get('result_story')
                    })

                    grow_stats = res.get("grow_stats", {})
                    base_intensity = safe_float(res.get("base", 0.0))
                    performance = safe_float(res.get("performance", 0.8))
                    if base_intensity <= 0:
                        base_intensity = 0.05

                    target_ca_gain = p.compute_daily_growth_ca(
                        base_intensity,
                        performance
                    )

                    raw_gain = 0.0
                    if grow_stats:
                        tmp_attrs = p.attributes.copy()
                        for k, v in grow_stats.items():
                            if k in tmp_attrs:
                                tmp_attrs[k] = min(
                                    20.0,
                                    tmp_attrs[k] + safe_float(v)
                                )
                        tmp_total = sum(
                            tmp_attrs[key] * game_data.WEIGHTS[key]
                            for key in game_data.WEIGHTS.keys()
                        )
                        tmp_ca = (tmp_total / game_data.THEORETICAL_MAX_SCORE) * 200
                        raw_gain = max(0.0, tmp_ca - p.ca)

                    scale = 1.0
                    if target_ca_gain > 0 and raw_gain > 0:
                        scale = target_ca_gain / raw_gain

                    for k, v in grow_stats.items():
                        p.grow_attribute(k, safe_float(v) * scale)

                    p.hp -= safe_int(res.get("hp_cost", 0))
                    p.mp -= safe_int(res.get("mp_cost", 0))
                    p.advance_day(1)
                    offer = maybe_generate_transfer_offer(p)
                    if offer:
                        st.session_state.transfer_notice = offer
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": f"📩 新しいオファー\n{offer_summary_text(offer)}"
                        })
                    st.session_state.current_event = None
                    game_data.save_game(p)
                    st.rerun()
