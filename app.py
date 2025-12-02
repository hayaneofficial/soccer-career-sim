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

# --- 便利関数 ---
def determine_category(team_name):
    name = team_name.replace(" ", "").replace("　", "").upper()
    if "高校" in name or "高等学校" in name or "HIGH" in name or "ACADEMY" in name:
        return "HighSchool"
    elif "大学" in name or "大學" in name or "UNIV" in name:
        return "University"
    elif "U-" in name or "U1" in name or "U2" in name or "YOUTH" in name or "ユース" in name:
        return "Youth"
    else:
        return "Professional"


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

    prompt = f"""
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

    return call_gemini(prompt)



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


def create_schedule_data(team_name, category, year):
    prompt = f"""
    チーム「{team_name}」({year}年)の年間スケジュールを作成せよ。
    リーグ戦を中心に30試合以上。
    Output JSON:
    {{
        "schedule": [
            {{ "date": "yyyy-mm-dd", "opponent": "...", "home": true }}
        ]
    }}
    """
    return call_gemini(prompt)


def generate_story(player, topic):
    prompt = f"""
    選手: {player.name}, 所属:{player.team_name}
    状況: {topic}
    指示: 短い物語を作成。

    Output JSON:
    {{
        "story": "..."
    }}
    """
    res = call_gemini(prompt)
    return res.get("story", "") if res else ""


def generate_next_event(player):
    sorted_npcs = sorted(player.npcs, key=lambda x: abs(float(x.relation)), reverse=True)[:5]
    npcs_txt = ", ".join([f"{n.role}:{n.name}({n.relation})" for n in sorted_npcs])

    next_match = None
    if player.schedule:
        sorted_sched = sorted(player.schedule, key=lambda x: x.get('date', '9999'))
        for m in sorted_sched:
            if m.get('date', '9999') >= str(player.current_date):
                next_match = m
                break
    schedule_info = f"次戦: {next_match.get('date')} vs {next_match.get('opponent','未定')}" if next_match else "予定なし"

    prompt = f"""
    選手: {player.name}, 所属:{player.team_name}
    現在日時: {player.current_date}
    スケジュール: {schedule_info}
    人間関係: {npcs_txt}

    指示:
    - 次に起こるイベントを作成する。
    - 選択肢は必ず3つ用意する。

    Output JSON:
    {{
      "title": "...",
      "description": "...",
      "choices": [
        {{"text":"...", "hint":"..." }},
        {{"text":"...", "hint":"..." }},
        {{"text":"...", "hint":"..." }}
      ]
    }}
    """
    res = call_gemini(prompt)
    if not res:
        return {"title": "日常", "description": "特になし", "choices": [{"text": "自主練", "hint": ""}]}
    return res


def resolve_action(player, choice_text, event_desc):
    prompt = f"""
    状況: {event_desc}
    選択: {choice_text}
    選手: {player.name}
    能力: {player.attributes}

    あなたはフットボールコーチAIです。
    その日のサッカー活動強度(Base)と、体感採点に対応するPerformanceも決めてください。

    - Base: TRや試合、自主練の合計。だいたい 0.01〜0.30 の範囲。
    - Performance: 0.6〜1.5（標準は0.8〜1.0）

    Format (必ずこのキーを含めてJSONで出力):
    {{
      "result_story": "...",
      "grow_stats": {{
         "Decisions": 0.1,
         "Acceleration": 0.2
      }},
      "hp_cost": 10,
      "mp_cost": 5,
      "relation_change": {{
         "role": "...",
         "val": 5
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
                    "position": position
                }
                st.session_state.game_phase = "review_stats"
                st.rerun()

# --- 2. Review Stats ---
elif st.session_state.game_phase == "review_stats":
    st.title("📊 能力値・人間関係の確認")
    st.info("AIが生成したデータを編集して確定してください。")

    data = st.session_state.temp_data["stats"]

    # 🔽 ここから修正
    # Gemini が返した attributes に、FM準拠の全キーをマージして 10.0 で初期化する
    raw_attr = data.get("attributes", {}) or {}
    base_attrs = {k: 10.0 for k in game_data.WEIGHTS.keys()}
    for k in base_attrs.keys():
        if k in raw_attr and raw_attr[k] is not None:
            base_attrs[k] = float(raw_attr[k])

    # CAプレビューも出しておくと便利
    total_score = sum(base_attrs[key] * game_data.WEIGHTS[key] for key in game_data.WEIGHTS.keys())
    ca_preview = (total_score / game_data.THEORETICAL_MAX_SCORE) * 200

    c1, c2 = st.columns(2)
    with c1:
        st.write("能力値（FM準拠・全項目）")
        st.caption(f"現在の推定CA: {ca_preview:.2f}")
        edited_attr = st.data_editor(
            pd.DataFrame([base_attrs]),
            use_container_width=True
        )
    # 🔼 ここまで修正

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

        pos_val = st.session_state.temp_data.get("position", "MF")

        p = game_data.Player(
            prof["name"],
            pos_val,
            prof["age"],
            attributes=edited_attr.to_dict(orient='records')[0],
            funds=funds,
            salary=salary,
            team_name=prof["team"],
            start_date=start_d
        )
        p.pa = float(st.session_state.temp_data["base"]["pa"])
        p.team_category = st.session_state.temp_data["cat"]

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
        st.session_state.game_phase = "story_intro"
        st.rerun()

# --- 3. Story Intro ---
elif st.session_state.game_phase == "story_intro":
    p = st.session_state.player
    st.title("🎬 入団")

    if "intro_text" not in st.session_state:
        with st.spinner("物語を生成中..."):
            topic = "入団会見" if p.team_category == "Professional" else "部室での自己紹介"
            st.session_state.intro_text = generate_story(p, topic)

    st.markdown(st.session_state.intro_text)

    if st.button("チームメイトと対面する"):
        st.session_state.game_phase = "review_team"
        del st.session_state.intro_text
        st.rerun()

# --- 4. Review Team ---
elif st.session_state.game_phase == "review_team":
    st.title("👥 チームメイト確認")
    p = st.session_state.player

    if not p.team_members:
        with st.spinner("チームデータを生成中..."):
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
            "Value": int(getattr(m, "value", 0))
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
                "value": row.get("Value")
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

    st.success(f"あなたの現在の序列: **{p.hierarchy}**")

    my_idx = next((i for i, m in enumerate(p.team_members) if m.name == p.name), 0)
    rivals = p.team_members[max(0, my_idx - 2): min(len(p.team_members), my_idx + 3)]
    st.write("### ポジション争い")
    for m in rivals:
        mark = "👈 YOU" if m.name == p.name else ""
        st.write(f"{m.hierarchy} | {m.name} (CA:{m.ca:.1f}) {mark}")

    if st.button("日程を確認する"):
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
                p.schedule = res.get("schedule", [])
                game_data.save_game(p)

    edited_sched = st.data_editor(
        pd.DataFrame(p.schedule),
        num_rows="dynamic",
        use_container_width=True
    )

    if st.button("日程確定 & シーズン開幕"):
        p.schedule = edited_sched.to_dict(orient='records')
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
        c1.metric("Date", str(p.current_date))
        c2.metric("Funds", f"¥{p.funds:,}")
        c3.metric("CA/PA", f"{p.ca:.1f}/{p.pa:.1f}")
        c4.metric("Value", f"€{int(p.value):,}")
        c5.metric("HP", f"{p.hp}")
        c6.metric("MP", f"{p.mp}")

        tab_attr, tab_roster, tab_year, tab_week, tab_timetable, tab_rel, tab_shop, tab_transfer = st.tabs(
            ["📊 能力/適性", "👥 名簿", "📅 年間日程", "🗓 週間日程", "⏰ 時間割", "🤝 人間関係", "🛍️ ショップ", "📩 移籍"]
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
                    "Height": getattr(m, "height", ""),
                    "Value": f"€{getattr(m, 'value', 0):,}"
                }
                # 高校・大学のときは年齢も見えた方が嬉しいので常に入れる
                row["Age"] = getattr(m, "age", "")
                data.append(row)

            if data:
                st.dataframe(
                    pd.DataFrame(data),
                    height=500,
                    use_container_width=True
                )
            else:
                st.info("チームメンバーがまだいません。")

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

        # ========== タブ: 週間日程（現在日付から7日分のざっくりビュー） ==========
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
            if p.npcs:
                rel_rows = []
                for n in p.npcs:
                    rel_rows.append({
                        "Role": n.role,
                        "Name": n.name,
                        "Relation": n.relation,
                        "Description": n.description
                    })
                st.dataframe(
                    pd.DataFrame(rel_rows),
                    use_container_width=True,
                    height=400
                )
            else:
                st.info("人間関係データがまだありません。")

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
            st.write("オファーなし（今はダミー表示）")

    # =========================
    # 右カラム：行動・イベント & ログ
    # =========================
    with col_chat:
        st.markdown("### 🏃 行動 / イベント")

        ev = st.session_state.current_event

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
                            st.session_state.current_event = None
                            game_data.save_game(p)
                            st.rerun()

            # 自由記述アクション
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
                    st.session_state.current_event = None
                    game_data.save_game(p)
                    st.rerun()

        # ログ表示
        st.markdown("### 📜 ログ")
        with st.container(height=400):
            for m in st.session_state.messages:
                st.chat_message(m["role"]).write(m["content"])

