import streamlit as st
import google.generativeai as genai
import game_data
import json
import random

st.set_page_config(page_title="サッカーキャリアSim", layout="wide")

# --- セッションステート初期化 ---
if "player" not in st.session_state:
    st.session_state.player = None
if "game_phase" not in st.session_state:
    st.session_state.game_phase = "start"
if "messages" not in st.session_state:
    st.session_state.messages = []
if "match_state" not in st.session_state:
    st.session_state.match_state = None

# --- サイドバー ---
with st.sidebar:
    st.header("⚙️ システム設定")
    api_key = st.text_input("Gemini APIキー", type="password")
    
    if st.session_state.game_phase == "main":
        if st.button("💾 セーブ"):
            game_data.save_game(st.session_state.player)
            st.success("保存完了")
    
    if st.button("📂 ロード"):
        loaded = game_data.load_game()
        if loaded:
            st.session_state.player = loaded
            st.session_state.game_phase = "main"
            st.session_state.messages = [{"role": "assistant", "content": "ロードしました。"}]
            st.rerun()

# --- フェーズ分岐 ---

# ■ スタート画面
if st.session_state.game_phase == "start":
    st.title("⚽ Football Career AI")
    if st.button("▶ 新しくゲームを始める"):
        st.session_state.game_phase = "create"
        st.rerun()

# ■ キャラ作成画面
elif st.session_state.game_phase == "create":
    st.title("📝 選手登録")
    if not api_key:
        st.error("サイドバーでAPIキーを設定してください")
        st.stop()

    c1, c2 = st.columns(2)
    with c1:
        name = st.text_input("名前", "佐藤 蹴斗")
        age = st.number_input("年齢", 15, 35, 18)
    with c2:
        position = st.selectbox("ポジション", ["CF", "RWG", "LWG", "OMF", "CMF", "DMF", "RSB", "LSB", "CB", "GK"])
        style = st.text_area("経歴", "高校時代は無名だったが、50m5秒台の俊足を武器に活躍した。")

    if st.button("作成"):
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("models/gemini-2.0-flash", generation_config={"response_mime_type": "application/json"})
            prompt = f"名前:{name}, 年齢:{age}, ポジション:{position}, 経歴:{style}。ここから能力値(1.0-20.0)を推論しJSON出力。{{'attributes': {{...}}, 'comment': '...'}}"
            res = model.generate_content(prompt)
            data = json.loads(res.text)
            p = game_data.Player(name, position, age, attributes=data.get("attributes"))
            st.session_state.player = p
            st.session_state.game_phase = "main"
            st.session_state.messages = [{"role": "assistant", "content": f"スカウト「{data.get('comment')}」\n入団おめでとう！"}]
            st.rerun()
        except Exception as e:
            st.error(f"エラー: {e}")

# ■ メイン（日常）画面
elif st.session_state.game_phase == "main":
    p = st.session_state.player
    st.title(f"⚽ {p.name} の日常")
    st.caption(f"📅 {p.current_date} | ❤️HP:{p.hp} 🧠MP:{p.mp} | CA:{p.ca:.1f}")
    
    # 試合に出るボタン（HPが元気なときだけ）
    if p.hp > 60:
        if st.button("🏟️ 公式戦に出場する"):
            st.session_state.game_phase = "match"
            # まず試合状態を作る
            ms = game_data.MatchState(p.name, p.position)
            st.session_state.match_state = ms
            
            # ★座標を取得してテキストに埋め込む
            pos_r, pos_c = ms.player_pos
            grid_str = f"{pos_r}{pos_c}"
            
            # 行番号に応じた描写の変化（簡易版）
            location_desc = "相手ゴール前" if pos_r <= 2 else "中盤" if pos_r <= 4 else "自陣深く"
            
            start_scene = f"後半35分、スコアは0-0。{location_desc}（{grid_str}）でボールを受けた！"
            
            st.session_state.messages = [{"role": "assistant", "content": start_scene}]
            st.rerun()
    else:
        st.warning("⚠️ 体力が足りません。休養してください。")

    # チャット・入力エリア
    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    if prompt := st.chat_input("行動を入力（例：走り込み、休養）"):
        if not api_key: st.stop()
        with st.chat_message("user"): st.markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("models/gemini-2.0-flash", generation_config={"response_mime_type": "application/json"})
        
        order = f"日時:{p.current_date}, 選手:{p.name}, 行動:{prompt}。成長とHPMP消費をJSON出力。{{'story':'...', 'grow_stats':{{...}}, 'hp_cost':10, 'mp_cost':0}}"
        
        res = model.generate_content(order)
        data = json.loads(res.text)
        
        # データ更新
        story = data.get("story", "")
        st.markdown(story)
        st.session_state.messages.append({"role": "assistant", "content": story})
        
        p.hp = max(0, min(100, p.hp - data.get("hp_cost", 0)))
        p.mp = max(0, min(100, p.mp - data.get("mp_cost", 0)))
        for k, v in data.get("grow_stats", {}).items(): p.grow_attribute(k, v)
        p.advance_day(1)
        game_data.save_game(p)
        st.rerun()

# ■ 試合（マッチ）画面
elif st.session_state.game_phase == "match":
    p = st.session_state.player
    m_state = st.session_state.match_state
    
    st.title("🏟️ 公式戦")
    
    # スコアボードとグリッド表示
    c1, c2 = st.columns([1, 2])
    with c1:
        st.metric("SCORE", f"{m_state.score_ally} - {m_state.score_enemy}")
        # グリッドを表として表示
        st.dataframe(
            m_state.get_grid_df(), 
            use_container_width=True, # 横幅いっぱいに広げる
            height=250 # 高さを固定
        )
        
    with c2:
        # 試合中のチャット
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                
        # 試合用入力フォーム
        if prompt := st.chat_input("プレーを選択（例：左(2A)へドリブルしてクロス！）"):
            if not api_key: st.stop()
            with st.chat_message("user"): st.markdown(prompt)
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("models/gemini-2.0-flash", generation_config={"response_mime_type": "application/json"})
            
            # 試合用の特殊プロンプト
            match_order = f"""
            状況: サッカーの試合中。
            主人公: {p.name} ({p.position}), 能力:{p.attributes}
            現在地: {m_state.player_pos}
            ユーザーのプレー宣言: {prompt}
            
            指示:
            1. プレーの成否を能力値に基づいて判定してください。
            2. 成功なら 'result': 'success', 失敗なら 'failure'。
            3. 次の展開（移動先グリッドやスコア変動）を決めてください。
            4. 結果描写(story)は臨場感たっぷりに。
            
            出力JSON:
            {{
                "story": "実況描写",
                "result": "success",
                "score_ally_add": 1 (得点なら1, なしなら0),
                "new_position_row": 2,
                "new_position_col": "A",
                "is_match_end": false (試合終了ならtrue)
            }}
            """
            
            res = model.generate_content(match_order)
            data = json.loads(res.text)
            
            # 試合データの更新
            story = data.get("story", "")
            m_state.score_ally += data.get("score_ally_add", 0)
            
            # 位置更新
            new_r = data.get("new_position_row")
            new_c = data.get("new_position_col")
            if new_r and new_c:
                m_state.player_pos = (new_r, new_c)
                # ボールも一緒に移動したとみなす
                m_state.ball_pos = (new_r, new_c)
            
            st.markdown(story)
            st.session_state.messages.append({"role": "assistant", "content": story})
            
            # 試合終了判定
            if data.get("is_match_end"):
                st.balloons() # 風船を飛ばす演出
                st.success("試合終了！")
                if st.button("ロッカールームへ戻る"):
                    st.session_state.game_phase = "main"
                    # 試合の疲れを反映
                    p.hp = max(0, p.hp - 30)
                    p.advance_day(1)
                    game_data.save_game(p)
                    st.rerun()
            else:
                st.rerun()

                # 位置更新の修正版
            new_r = data.get("new_position_row")
            new_c = data.get("new_position_col")
            if new_r and new_c:
                # int() で囲んで、文字がきても数字に直す！
                m_state.player_pos = [int(new_r), str(new_c)]
                m_state.ball_pos = [int(new_r), str(new_c)]
                
    # 試合をやめるボタン（デバッグ用）
    if st.sidebar.button("試合終了（強制）"):
        st.session_state.game_phase = "main"
        st.rerun()

        