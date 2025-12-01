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
        
        # ★NEW: 所属クラブ表示
        st.info(f"🏟️ **{p.team_name}** ({p.team_rank}ランク)")
        
        st.divider()
        st.subheader("💰 資産・契約")
        st.write(f"**所持金: ¥{p.funds:,}**")
        st.caption(f"年俸: ¥{p.salary:,}")
        
        st.divider()
        st.subheader("👥 チーム状況")
        status, reason = p.get_squad_status()
        st.info(f"序列: **{status}**\n({reason})")
        
        manager = p.get_npc_by_role("監督")
        if manager:
            trust_val = (manager.relation + 100) / 200
            st.progress(trust_val, text=f"監督信頼度: {manager.relation}")
        
        rival = p.get_npc_by_role("ライバル")
        if rival:
            diff = p.ca - rival.ca
            st.caption(f"VSライバル: {'優勢' if diff>0 else '劣勢'} ({diff:+.1f})")

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

# ■ キャラ作成
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
            選手: {name}, {age}歳, {position}, 経歴: {style}
            指示: 初期能力値、監督(relation=0)、ライバル(CA高め)を作成。JSON出力。
            Format: {{ "attributes": {{...}}, "manager": {{ "name": "...", "description": "..." }}, "rival": {{ "name": "...", "description": "...", "ca": 110.5 }}, "comment": "..." }}
            """
            
            res = model.generate_content(prompt)
            try: data = json.loads(res.text)
            except: data = {}
            if isinstance(data, list): data = data[0] if data else {}
            if not isinstance(data, dict): data = {}
            
            p = game_data.Player(name, position, age, attributes=data.get("attributes"))
            
            mgr = data.get("manager", {"name":"監督", "description":""})
            p.add_npc(game_data.NPC(mgr.get("name"), "監督", 0, mgr.get("description")))
            
            riv = data.get("rival", {"name":"ライバル", "description":"", "ca":p.ca+5})
            p.add_npc(game_data.NPC(riv.get("name"), "ライバル", 0, riv.get("description"), ca=riv.get("ca")))
            
            st.session_state.player = p
            st.session_state.game_phase = "main"
            st.session_state.messages = [{"role": "assistant", "content": f"【入団】\n{data.get('comment')}\n\n年俸 **480万円** で契約しました！\nプロ生活のスタートです。"}]
            st.rerun()
            
        except Exception as e:
            st.error(f"エラー: {e}")

# ■ メイン画面
elif st.session_state.game_phase == "main":
    p = st.session_state.player
    st.title(f"⚽ {p.name} の日常")
    
    # ★NEW: 移籍タブを追加
    tab1, tab2, tab3 = st.tabs(["🏃 行動", "🛍️ ショップ", "📩 移籍"])
    
    # --- タブ1: 行動 ---
    with tab1:
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
            mgr_info = f"{manager.name}(信頼:{manager.relation})" if manager else ""
            riv_info = f"{rival.name}(CA:{rival.ca})" if rival else ""

            order = f"""
            日時:{p.current_date}, 選手:{p.name}, 行動:{prompt}
            監督:{mgr_info}, ライバル:{riv_info}
            指示: 行動結果(story, grow, hp/mp_cost, rel_change)と、ライバルの成長(rival_growth)を出力。リスト禁止。
            Format: {{ "story": "...", "grow_stats": {{...}}, "hp_cost": 10, "mp_cost": 0, "relation_change": 0, "rival_growth_ca": 0.1 }}
            """
            
            try:
                res = model.generate_content(order)
                try: data = json.loads(res.text)
                except: data = {}
                if isinstance(data, list): data = data[0] if data else {}
                if not isinstance(data, dict): data = {}
                
                story = data.get("story", "...")
                st.markdown(story)
                st.session_state.messages.append({"role": "assistant", "content": story})
                
                p.hp = max(0, min(100, p.hp - data.get("hp_cost", 0)))
                p.mp = max(0, min(100, p.mp - data.get("mp_cost", 0)))
                for k, v in data.get("grow_stats", {}).items(): p.grow_attribute(k, v)
                if manager: manager.relation = max(-100, min(100, manager.relation + data.get("relation_change", 0)))
                if rival: rival.ca += data.get("rival_growth_ca", 0.05)

                # 給料＆オファー通知
                daily_log = p.advance_day(1)
                if daily_log:
                    st.toast("通知あり！", icon="🔔")
                    st.session_state.messages.append({"role": "assistant", "content": f"**{daily_log}**"})

                game_data.save_game(p)
                st.rerun()
            except Exception as e:
                st.error(f"エラー: {e}")

    # --- タブ2: ショップ ---
    with tab2:
        st.subheader("🛍️ アイテムショップ")
        st.write(f"所持金: **¥{p.funds:,}**")
        items = [
            {"name": "高級プロテイン", "price": 5000, "effect": "HP+30", "hp": 30, "mp": 0},
            {"name": "戦術分析書", "price": 10000, "effect": "MP+20 & Decisions微増", "hp": 0, "mp": 20, "stat": "Decisions"},
            {"name": "温泉旅行", "price": 50000, "effect": "HP/MP全快", "hp": 100, "mp": 100},
            {"name": "最新スパイク", "price": 100000, "effect": "Pace/Agility強化", "hp": 0, "mp": 10, "stat": "Pace"}
        ]
        for item in items:
            c_name, c_effect, c_btn = st.columns([2, 2, 1])
            c_name.write(f"**{item['name']}** (¥{item['price']:,})")
            c_effect.caption(item['effect'])
            if c_btn.button("購入", key=item['name']):
                if p.funds >= item['price']:
                    p.funds -= item['price']
                    p.hp = min(100, p.hp + item['hp'])
                    p.mp = min(100, p.mp + item['mp'])
                    if "stat" in item: p.grow_attribute(item['stat'], 0.5)
                    st.toast(f"{item['name']}を購入！")
                    game_data.save_game(p)
                    st.rerun()
                else:
                    st.error("お金が足りません！")

    # --- タブ3: 移籍市場 (NEW!) ---
    with tab3:
        st.subheader("📩 届いているオファー")
        if not p.offers:
            st.info("現在、オファーはありません。活躍して注目を集めましょう。")
        else:
            for i, offer in enumerate(p.offers):
                with st.container(border=True):
                    cols = st.columns([3, 2, 2])
                    cols[0].markdown(f"### {offer['team_name']}")
                    cols[0].caption(f"ランク: {offer['rank']}")
                    cols[1].metric("提示年俸", f"¥{offer['salary']:,}", delta=f"{offer['salary'] - p.salary:,}")
                    cols[2].write(f"契約: {offer['contract_years']}年")
                    
                    if st.button("契約書にサインする ✍️", key=f"sign_{i}"):
                        if api_key:
                            # 移籍処理
                            p.transfer_to(offer)
                            
                            # 新天地のNPC生成
                            try:
                                genai.configure(api_key=api_key)
                                model = genai.GenerativeModel("models/gemini-2.0-flash", generation_config={"response_mime_type": "application/json"})
                                prompt = f"""
                                プレイヤーが新チーム「{p.team_name}」に移籍しました。
                                ランク:{p.team_rank}, ポジション:{p.position}
                                
                                指示: 新しい「監督」と「ライバル」を作成してJSON出力。
                                ライバルのCAは {p.ca + 5} 程度にすること。
                                Format: {{ "manager": {{ "name": "...", "description": "..." }}, "rival": {{ "name": "...", "description": "...", "ca": 120.0 }} }}
                                """
                                res = model.generate_content(prompt)
                                data = json.loads(res.text)
                                mgr = data.get("manager", {"name":"新監督", "description":""})
                                p.add_npc(game_data.NPC(mgr.get("name"), "監督", 0, mgr.get("description")))
                                riv = data.get("rival", {"name":"新ライバル", "description":"", "ca":p.ca+5})
                                p.add_npc(game_data.NPC(riv.get("name"), "ライバル", 0, riv.get("description"), ca=riv.get("ca")))
                                
                                st.balloons()
                                st.session_state.messages = [{"role": "assistant", "content": f"🎉 **{p.team_name}** への移籍が完了しました！\n新しい仲間たちが待っています。"}]
                                game_data.save_game(p)
                                st.rerun()
                            except:
                                st.error("AI生成エラー")
                        else:
                            st.error("APIキーが必要です")

# ■ 試合画面 (変更なし)
elif st.session_state.game_phase == "match":
    # (前回と同じコード)
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
                    if m_state.score_ally > m_state.score_enemy:
                        win_bonus = 100000
                        p.funds += win_bonus
                        st.toast(f"勝利ボーナス +¥{win_bonus:,} GET!", icon="💰")
                    game_data.save_game(p)
                    st.rerun()
            else:
                st.rerun()
    
    if st.sidebar.button("試合終了（強制）"):
        st.session_state.game_phase = "main"
        st.rerun()