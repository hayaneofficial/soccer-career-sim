import streamlit as st
import google.generativeai as genai
import game_data
import json
import random

st.set_page_config(page_title="サッカーキャリアSim", layout="wide")

# --- 初期化 ---
if "player" not in st.session_state: st.session_state.player = None
if "game_phase" not in st.session_state: st.session_state.game_phase = "start"
if "messages" not in st.session_state: st.session_state.messages = []
if "match_state" not in st.session_state: st.session_state.match_state = None

# --- サイドバー ---
with st.sidebar:
    st.header("⚙️ システム設定")
    api_key = st.text_input("Gemini APIキー", type="password")
    
    if st.session_state.game_phase == "main":
        p = st.session_state.player
        
        st.divider()
        st.subheader("👥 チーム状況")
        
        # 序列の判定
        status, reason = p.get_squad_status()
        st.info(f"現在の序列: **{status}**\n\n({reason})")
        
        # 監督
        manager = p.get_npc_by_role("監督")
        if manager:
            trust_val = (manager.relation + 100) / 200
            st.progress(trust_val, text=f"監督信頼度: {manager.relation}")
        
        # ライバル表示
        rival = p.get_npc_by_role("ライバル")
        if rival:
            st.write(f"⚔️ **ライバル: {rival.name}**")
            st.caption(f"CA: {rival.ca:.1f} ({rival.description})")
            diff = p.ca - rival.ca
            if diff > 0: st.success(f"あなたの方が強い (+{diff:.1f})")
            else: st.error(f"ライバルの方が強い ({diff:.1f})")

        st.divider()
        if st.button("💾 セーブ"):
            game_data.save_game(p)
            st.success("保存完了")

    if st.button("📂 ロード"):
        loaded = game_data.load_game()
        if loaded:
            st.session_state.player = loaded
            st.session_state.game_phase = "main"
            st.session_state.messages = [{"role": "assistant", "content": "ロードしました。"}]
            st.rerun()

# --- フェーズ処理 ---

# ■ スタート
if st.session_state.game_phase == "start":
    st.title("⚽ Football Career AI")
    if st.button("▶ 新しくゲームを始める"):
        st.session_state.game_phase = "create"
        st.rerun()

# ■ キャラ作成 (ここに安全装置を追加しました！)
elif st.session_state.game_phase == "create":
    st.title("📝 選手登録")
    if not api_key: st.stop()

    c1, c2 = st.columns(2)
    with c1:
        name = st.text_input("名前", "佐藤 蹴斗")
        age = st.number_input("年齢", 18)
    with c2:
        position = st.selectbox("ポジション", ["CF", "OMF", "LWG", "RWG", "CMF", "DMF", "CB", "SB", "GK"])
        style = st.text_area("経歴", "高校時代は無名だったが...")

    if st.button("作成"):
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("models/gemini-2.0-flash", generation_config={"response_mime_type": "application/json"})
            
            prompt = f"""
            以下に基づき初期データ生成。JSON出力。
            選手: {name}, {age}歳, {position}, 経歴: {style}
            
            指示:
            1. 能力値(attributes)作成。
            2. NPC「監督」作成（relation=0）。
            3. NPC「ライバル」を一人作成。
               - 同じポジション。
               - 能力(ca)は、プレイヤーの初期CAより「やや高い」設定にすること（壁となる存在）。
               - 性格は「エリート」「努力家」など。
            
            Format:
            {{
                "attributes": {{...}},
                "manager": {{ "name": "...", "description": "..." }},
                "rival": {{ "name": "...", "description": "...", "ca": 110.5 }},
                "comment": "スカウトコメント"
            }}
            """
            
            res = model.generate_content(prompt)
            
            # ★安全装置: 文字列をJSONにする
            try:
                data = json.loads(res.text)
            except:
                st.error("AIからのデータ読み取りに失敗しました。もう一度押してください。")
                st.stop()

            # ★安全装置: もしリスト形式で返ってきたら、中身を取り出す
            if isinstance(data, list):
                if len(data) > 0:
                    data = data[0]
                else:
                    st.error("AIから空のデータが返ってきました。")
                    st.stop()
            
            # プレイヤー
            p = game_data.Player(name, position, age, attributes=data.get("attributes"))
            
            # 監督追加
            mgr_data = data.get("manager", {"name": "監督", "description": "普通"})
            p.add_npc(game_data.NPC(mgr_data.get("name", "監督"), "監督", 0, mgr_data.get("description", "")))
            
            # ライバル追加
            riv_data = data.get("rival", {"name": "ライバル", "description": "強敵", "ca": p.ca + 5})
            rival_npc = game_data.NPC(riv_data.get("name", "ライバル"), "ライバル", 0, riv_data.get("description", ""), ca=riv_data.get("ca", p.ca + 5))
            p.add_npc(rival_npc)
            
            st.session_state.player = p
            st.session_state.game_phase = "main"
            st.session_state.messages = [{"role": "assistant", "content": f"【入団】\n{data.get('comment', '入団手続き完了')}\n\n同じポジションには、{rival_npc.name}（CA:{rival_npc.ca:.1f}）という絶対的なレギュラーがいます。\n彼からスタメンを奪うのが最初の目標です！"}]
            st.rerun()
            
        except Exception as e:
            st.error(f"エラー: {e}")

# ■ メイン画面
elif st.session_state.game_phase == "main":
    p = st.session_state.player
    st.title(f"⚽ {p.name} の日常")
    
    # 試合出場判定
    status, reason = p.get_squad_status()
    
    if "スタメン" in status and p.hp > 60:
        if st.button("🏟️ 公式戦に出場する"):
            ms = game_data.MatchState(p.name, p.position)
            st.session_state.match_state = ms
            pos_r, pos_c = ms.player_pos
            st.session_state.game_phase = "match"
            st.session_state.messages = [{"role": "assistant", "content": f"後半35分、スコア0-0。{pos_r}{pos_c}でボールを受けた！"}]
            st.rerun()
    elif p.hp <= 60:
        st.warning("⚠️ 体力不足")
    else:
        st.error(f"🔒 試合に出られません（理由: {reason}）")
    
    # チャット
    for m in st.session_state.messages:
        with st.chat_message(m["role"]): st.markdown(m["content"])

    if prompt := st.chat_input("行動を入力"):
        if not api_key: st.stop()
        with st.chat_message("user"): st.markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("models/gemini-2.0-flash", generation_config={"response_mime_type": "application/json"})
        
        manager = p.get_npc_by_role("監督")
        rival = p.get_npc_by_role("ライバル")
        
        mgr_info = f"{manager.name}(信頼:{manager.relation})" if manager else "なし"
        riv_info = f"{rival.name}(CA:{rival.ca})" if rival else "なし"

        order = f"""
        日時:{p.current_date}, 選手:{p.name}, 行動:{prompt}
        監督:{mgr_info}, ライバル:{riv_info}
        
        指示:
        1. ユーザーの行動結果(story, grow_stats, hp/mp_cost, relation_change)を出力。
        2. さらに「ライバルも独自に練習している」。ライバルの成長値(rival_growth_ca)を 0.0〜0.3 の間で決めて出力。
        3. storyには、ライバルの様子（「〇〇も負けじと走り込んでいる」など）も含めて。
        4. 必ず単一のJSONオブジェクトで出力（リスト禁止）。
        
        Format: {{ 
            "story": "...", 
            "grow_stats": {{...}}, "hp_cost": 10, "mp_cost": 0, "relation_change": 0,
            "rival_growth_ca": 0.1
        }}
        """
        
        try:
            res = model.generate_content(order)
            
            # ★安全装置
            try: data = json.loads(res.text)
            except: data = {}
            if isinstance(data, list): data = data[0] if data else {}
            if not isinstance(data, dict): data = {}
            
            story = data.get("story", "描写なし")
            st.markdown(story)
            st.session_state.messages.append({"role": "assistant", "content": story})
            
            p.hp = max(0, min(100, p.hp - data.get("hp_cost", 0)))
            p.mp = max(0, min(100, p.mp - data.get("mp_cost", 0)))
            for k, v in data.get("grow_stats", {}).items(): p.grow_attribute(k, v)
            if manager: manager.relation = max(-100, min(100, manager.relation + data.get("relation_change", 0)))
            
            if rival:
                growth = data.get("rival_growth_ca", 0.05)
                rival.ca += growth
                st.toast(f"ライバルCA +{growth:.2f}")

            p.advance_day(1)
            game_data.save_game(p)
            st.rerun()
            
        except Exception as e:
            st.error(f"エラー: {e}")

# ■ 試合画面
elif st.session_state.game_phase == "match":
    p = st.session_state.player
    m_state = st.session_state.match_state
    
    st.title("🏟️ 公式戦")
    c1, c2 = st.columns([1, 2])
    with c1:
        st.metric("SCORE", f"{m_state.score_ally} - {m_state.score_enemy}")
        st.dataframe(m_state.get_grid_df(), use_container_width=True, height=250)
        
    with c2:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])
                
        if prompt := st.chat_input("プレーを選択"):
            if not api_key: st.stop()
            with st.chat_message("user"): st.markdown(prompt)
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("models/gemini-2.0-flash", generation_config={"response_mime_type": "application/json"})
            
            match_order = f"""
            状況: 試合中。主人公:{p.name}, 能力:{p.attributes}, 位置:{m_state.player_pos}
            行動: {prompt}
            Format: {{ "story": "...", "result": "success", "score_ally_add": 0, "new_position_row": 0, "new_position_col": "C", "is_match_end": false }}
            """
            res = model.generate_content(match_order)
            
            # ★ここにも安全装置
            try: data = json.loads(res.text)
            except: data = {}
            if isinstance(data, list): data = data[0] if data else {}
            if not isinstance(data, dict): data = {}

            story = data.get("story", "")
            m_state.score_ally += data.get("score_ally_add", 0)
            new_r = data.get("new_position_row")
            new_c = data.get("new_position_col")
            if new_r and new_c:
                m_state.player_pos = [int(new_r), str(new_c)]
                m_state.ball_pos = [int(new_r), str(new_c)]
            
            st.markdown(story)
            st.session_state.messages.append({"role": "assistant", "content": story})
            
            if data.get("is_match_end"):
                st.balloons()
                st.success("試合終了！")
                manager = p.get_npc_by_role("監督")
                if manager:
                    bonus = 5 if m_state.score_ally > m_state.score_enemy else 1
                    manager.relation += bonus
                
                rival = p.get_npc_by_role("ライバル")
                if rival and m_state.score_ally > 0:
                    st.toast("活躍によりライバルとの序列が変動！")

                if st.button("ロッカールームへ戻る"):
                    st.session_state.game_phase = "main"
                    p.hp = max(0, p.hp - 30)
                    p.advance_day(1)
                    game_data.save_game(p)
                    st.rerun()
            else:
                st.rerun()
    
    if st.sidebar.button("試合終了（強制）"):
        st.session_state.game_phase = "main"
        st.rerun()