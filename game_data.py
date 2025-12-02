 (cd "$(git rev-parse --show-toplevel)" && git apply --3way <<'EOF' 
diff --git a/game_data.py b/game_data.py
index 66c3349450e4c6b15aa6a0181f11a17c9d52ac3d..945c6e2e7687dcde11d15dc1302b2a7a3208993e 100644
--- a/game_data.py
+++ b/game_data.py
@@ -1,84 +1,148 @@
 import random
 import json
 import datetime
 import streamlit as st
 import pandas as pd
 from google.oauth2 import service_account
 from googleapiclient.discovery import build
 from googleapiclient.http import MediaIoBaseUpload
 import io
 import re
 import math
 
 # --- 定数・辞書定義 ---
-WEIGHTS = {
-    "Decisions": 4.0, "Anticipation": 3.5, "Composure": 3.5, "Concentration": 3.0,
-    "WorkRate": 3.0, "Teamwork": 2.5, "Positioning": 2.5, "OffTheBall": 2.5,
-    "Vision": 2.5, "Determination": 2.0, "Aggression": 1.5, "Bravery": 1.5,
-    "Flair": 1.0, "Leadership": 1.0,
-    "Acceleration": 5.0, "Pace": 5.0, "Stamina": 4.0, "NaturalFitness": 3.5,
-    "Agility": 3.5, "Strength": 3.0, "Balance": 2.5, "JumpingReach": 2.5,
-    "Passing": 4.0, "FirstTouch": 4.0, "Technique": 3.5, "Dribbling": 2.5,
-    "Tackling": 2.5, "Marking": 2.5, "Finishing": 2.5, "Heading": 2.0,
-    "Crossing": 2.0, "LongShots": 1.5, "PenaltyTaking": 1.0, "FreeKickTaking": 1.0,
-    "Corners": 1.0, "LongThrows": 0.5,
-    "WeakFoot": 9.0
-}
+WEIGHTS = {
+    "Decisions": 4.0, "Anticipation": 3.5, "Composure": 3.5, "Concentration": 3.0,
+    "WorkRate": 3.0, "Teamwork": 2.5, "Positioning": 2.5, "OffTheBall": 2.5,
+    "Vision": 2.5, "Determination": 2.0, "Aggression": 1.5, "Bravery": 1.5,
+    "Flair": 1.0, "Leadership": 1.0,
+    "Acceleration": 5.0, "Pace": 5.0, "Stamina": 4.0, "NaturalFitness": 3.5,
+    "Agility": 3.5, "Strength": 3.0, "Balance": 2.5, "JumpingReach": 2.5,
+    "Passing": 4.0, "FirstTouch": 4.0, "Technique": 3.5, "Dribbling": 2.5,
+    "Tackling": 2.5, "Marking": 2.5, "Finishing": 2.5, "Heading": 2.0,
+    "Crossing": 2.0, "LongShots": 1.5, "PenaltyTaking": 1.0, "FreeKickTaking": 1.0,
+    "Corners": 1.0, "LongThrows": 0.5,
+    "Adaptability": 1.0, "Ambition": 1.0, "Controversy": 0.5, "Loyalty": 0.5,
+    "Pressure": 1.5, "Professionalism": 1.5, "Sportsmanship": 0.5, "Temperament": 0.5,
+    "InjuryProneness": 1.5, "Versatility": 1.5, "Dirtiness": 0.5, "ImportantMatches": 1.0,
+    "WeakFoot": 9.0
+}
 THEORETICAL_MAX_SCORE = sum(WEIGHTS.values()) * 20
 
 TEAM_RANKS = {
     "S": {"name": "欧州1部", "req_ca": 150, "avg_salary": 300000000},
     "A": {"name": "J1上位", "req_ca": 120, "avg_salary": 80000000},
     "B": {"name": "J1中下位", "req_ca": 100, "avg_salary": 30000000},
     "C": {"name": "J2", "req_ca": 80, "avg_salary": 10000000},
     "D": {"name": "J3/JFL", "req_ca": 50, "avg_salary": 4000000}
 }
 
 FORMATIONS = {
     "4-3-3": ["GK", "LSB", "LCB", "RCB", "RSB", "DMF", "LCM", "RCM", "LWG", "RWG", "CF"],
     "4-2-3-1": ["GK", "LSB", "LCB", "RCB", "RSB", "LDMF", "RDMF", "LMF", "OMF", "RMF", "CF"],
     "4-4-2": ["GK", "LSB", "LCB", "RCB", "RSB", "LMF", "LCM", "RCM", "RMF", "CF", "CF"],
     "3-5-2": ["GK", "LCB", "CCB", "RCB", "LWB", "LCM", "DMF", "RCM", "RWB", "CF", "CF"],
     "3-4-2-1": ["GK", "LCB", "CCB", "RCB", "LWB", "LCM", "RCM", "RWB", "LOMF", "ROMF", "CF"],
     "3-4-3": ["GK", "LCB", "CCB", "RCB", "LWB", "LCM", "RCM", "RWB", "LWG", "RWG", "CF"]
 }
 
 HIERARCHY_UNI = ["ASta", "ASub", "BSta", "BSub", "CSta", "CSub", "DSta", "DSub", "E"]
 HIERARCHY_HS = ["ASta", "ASub", "BSta", "BSub", "CSta", "CSub", "D"]
 
-LAST_NAMES = ["佐藤", "鈴木", "高橋", "田中", "伊藤", "渡辺", "山本", "中村", "小林", "加藤",
-              "吉田", "山田", "佐々木", "山口", "松本", "井上", "木村", "林", "斎藤", "清水"]
-FIRST_NAMES = ["翔", "大翔", "蓮", "蒼", "湊", "樹", "悠真", "陽翔", "大和", "陽向",
-               "陸", "海", "空", "翼", "健太", "拓哉", "直樹", "亮太", "達也", "駿"]
+LAST_NAMES = [
+    "佐藤", "鈴木", "高橋", "田中", "伊藤", "渡辺", "山本", "中村", "小林", "加藤",
+    "吉田", "山田", "佐々木", "山口", "松本", "井上", "木村", "林", "斎藤", "清水",
+    "森", "池田", "橋本", "阿部", "石川", "山崎", "村上", "藤田", "青木", "福田",
+    "岡田", "藤井", "中島", "小川", "後藤", "岡本", "長谷川", "村田", "近藤", "大野",
+    "柴田", "高木", "河野", "山内", "石田", "三浦", "原田", "森田", "竹内", "酒井",
+    "西村", "千葉", "荒木", "和田", "内田", "中野", "清田", "真鍋", "岩本", "堀江"
+]
+FIRST_NAMES = [
+    "翔", "大翔", "蓮", "蒼", "湊", "樹", "悠真", "陽翔", "大和", "陽向",
+    "陸", "海", "空", "翼", "健太", "拓哉", "直樹", "亮太", "達也", "駿",
+    "隼人", "直樹", "啓太", "恭平", "大輝", "颯太", "隼也", "和真", "悠斗", "祥平",
+    "凛", "瑛斗", "泰生", "駿介", "瑛太", "圭吾", "悠汰", "悠太", "拓海", "大樹",
+    "悠人", "颯真", "匠", "航太", "晴", "康平", "誠", "友也", "友樹", "修斗"
+]
 
 FOLDER_ID = "1_IVb-lZUdM2B_n6yLQIjhCEA1HQhlbfH"  # ★あなたのID
 
-POSSIBLE_POSITIONS = [
-    "CF", "OMF", "RWG", "LWG", "CMF", "DMF", "RMF", "LMF",
-    "RWB", "LWB", "RSB", "LSB", "CB", "GK"
-]
+POSSIBLE_POSITIONS = [
+    "CF", "OMF", "RWG", "LWG", "CMF", "DMF", "RMF", "LMF",
+    "RWB", "LWB", "RSB", "LSB", "CB", "GK"
+]
+
+
+def _sample_ca_by_category(category: str, grade: int = 1) -> float:
+    if category == "HighSchool":
+        if random.random() < 0.005:
+            return random.uniform(80, 90)
+        base = random.gauss(34 + grade * 3, 8)
+        return max(20.0, min(90.0, base))
+    if category == "University":
+        if random.random() < 0.005:
+            return random.uniform(90, 110)
+        base = random.gauss(42 + grade * 3, 7)
+        return max(30.0, min(110.0, base))
+    return max(30.0, min(160.0, random.gauss(90, 15)))
+
+
+def _sample_pa() -> float:
+    roll = random.random()
+    if roll < 0.001:
+        return random.uniform(150, 200)
+    if roll < 0.006:
+        return random.uniform(120, 160)
+    if roll < 0.026:
+        return random.uniform(100, 140)
+    base = random.gauss(55, 12)
+    return max(40.0, min(160.0, base))
+
+
+def _sample_height(position: str) -> int:
+    pos_upper = position.upper()
+    if "GK" in pos_upper:
+        roll = random.random()
+        if roll < 0.2:
+            return random.randint(190, 200)
+        if roll < 0.9:
+            return random.randint(180, 189)
+        return random.randint(170, 179)
+    if any(tag in pos_upper for tag in ["RCB", "LCB", "CF", "RCF", "LCF"]):
+        roll = random.random()
+        if roll < 0.05:
+            return random.randint(190, 198)
+        if roll < 0.65:
+            return random.randint(180, 189)
+        return random.randint(170, 179)
+    roll = random.random()
+    if roll < 0.15:
+        return random.randint(180, 190)
+    if roll < 0.35:
+        return random.randint(170, 179)
+    return random.randint(171, 185)
 
 
 def get_drive_service():
     if "gcp_json" not in st.secrets:
         return None
     try:
         creds_dict = json.loads(st.secrets["gcp_json"])
         creds = service_account.Credentials.from_service_account_info(
             creds_dict,
             scopes=['https://www.googleapis.com/auth/drive']
         )
         return build('drive', 'v3', credentials=creds)
     except Exception as e:
         st.error(f"Drive接続エラー: {e}")
         return None
 
 
 def safe_int_parse(val, default=0):
     if val is None:
         return default
     try:
         if isinstance(val, (int, float)):
             return int(val)
         val_str = str(val).lower()
         multiplier = 1
@@ -237,271 +301,274 @@ class TeamGenerator:
         # raw_ca = alpha * log(value) + beta*age + gamma + intercept
         # => log(value) = (ca - beta*age - gamma - intercept) / alpha
         gamma = pos_bias.get(position_type, 0.0)
         log_value = (ca - (beta * age) - gamma - intercept) / alpha
         try:
             value = math.exp(log_value)
         except OverflowError:
             value = 100_000_000
 
         # 🔽 下限を 50,000 → 10,000 に下げて、
         # 大学・高校レベルのCAでもちゃんと差が出るようにする
         value = max(1, min(int(value), 200_000_000))
         return value
 
 
     # ★復元: 自動生成ロジック (app.pyから呼ばれる)
     @staticmethod
     def generate_teammates(category, formation_name, real_players_data=None):
         if formation_name not in FORMATIONS:
             formation_name = random.choice(list(FORMATIONS.keys()))
         positions = FORMATIONS[formation_name]
 
         teammates = []
         hierarchy_list = []
 
-        # --- 大学 (University) ---
-        if category == "University":
-            for grade in range(1, 5):
-                for pos in positions:
-                    for _ in range(2):
-                        base_ca = 35 + (grade * 5) + random.uniform(-10, 10)
-                        ca = min(80, max(33, base_ca))
-                        pa = min(150, ca + random.uniform(10, 30))
-                        teammates.append(NPC(
-                            TeamGenerator.generate_random_name(),
-                            "チームメイト",
-                            0,
-                            "",
-                            ca,
-                            pos,
-                            0,
-                            18 + grade,
-                            pa
-                        ))
-            for i, pos in enumerate(positions):
-                if i == 0:
-                    continue
-                ca = random.uniform(30, 36)
-                grade = random.randint(1, 4)
-                teammates.append(NPC(
-                    TeamGenerator.generate_random_name(),
-                    "チームメイト",
-                    0,
-                    "",
-                    ca,
-                    pos,
-                    0,
-                    18 + grade,
-                    ca + 5
-                ))
-            hierarchy_list = HIERARCHY_UNI
-
-        # --- 高校 (HighSchool) ---
-        elif category == "HighSchool":
-            for grade in range(1, 4):
-                for pos in positions:
-                    for _ in range(2):
-                        base_ca = 25 + (grade * 10) + random.uniform(-10, 10)
-                        ca = min(80, max(20, base_ca))
-                        pa = min(150, ca + random.uniform(15, 40))
-                        teammates.append(NPC(
-                            TeamGenerator.generate_random_name(),
-                            "チームメイト",
-                            0,
-                            "",
-                            ca,
-                            pos,
-                            0,
-                            15 + grade,
-                            pa
-                        ))
-            for i, pos in enumerate(positions):
-                if i == 0:
-                    continue
-                ca = random.uniform(15, 25)
-                grade = random.randint(1, 3)
-                teammates.append(NPC(
-                    TeamGenerator.generate_random_name(),
-                    "チームメイト",
-                    0,
-                    "",
-                    ca,
-                    pos,
-                    0,
-                    15 + grade,
-                    ca + 10
-                ))
-            hierarchy_list = HIERARCHY_HS
+        # --- 大学 (University) ---
+        if category == "University":
+            for grade in range(1, 5):
+                for pos in positions:
+                    for _ in range(2):
+                        ca = _sample_ca_by_category("University", grade)
+                        pa = max(ca, _sample_pa())
+                        teammates.append(NPC(
+                            TeamGenerator.generate_random_name(),
+                            "チームメイト",
+                            0,
+                            "",
+                            ca,
+                            pos,
+                            0,
+                            18 + grade,
+                            pa,
+                            height=_sample_height(pos)
+                        ))
+            for i, pos in enumerate(positions):
+                if i == 0:
+                    continue
+                ca = _sample_ca_by_category("University", random.randint(1, 4))
+                grade = random.randint(1, 4)
+                teammates.append(NPC(
+                    TeamGenerator.generate_random_name(),
+                    "チームメイト",
+                    0,
+                    "",
+                    ca,
+                    pos,
+                    0,
+                    18 + grade,
+                    max(ca, _sample_pa()),
+                    height=_sample_height(pos)
+                ))
+            hierarchy_list = HIERARCHY_UNI
+
+        # --- 高校 (HighSchool) ---
+        elif category == "HighSchool":
+            for grade in range(1, 4):
+                for pos in positions:
+                    for _ in range(2):
+                        ca = _sample_ca_by_category("HighSchool", grade)
+                        pa = max(ca, _sample_pa())
+                        teammates.append(NPC(
+                            TeamGenerator.generate_random_name(),
+                            "チームメイト",
+                            0,
+                            "",
+                            ca,
+                            pos,
+                            0,
+                            15 + grade,
+                            pa,
+                            height=_sample_height(pos)
+                        ))
+            for i, pos in enumerate(positions):
+                if i == 0:
+                    continue
+                ca = _sample_ca_by_category("HighSchool", random.randint(1, 3))
+                grade = random.randint(1, 3)
+                teammates.append(NPC(
+                    TeamGenerator.generate_random_name(),
+                    "チームメイト",
+                    0,
+                    "",
+                    ca,
+                    pos,
+                    0,
+                    15 + grade,
+                    max(ca, _sample_pa()),
+                    height=_sample_height(pos)
+                ))
+            hierarchy_list = HIERARCHY_HS
 
         # --- プロ/ユース (Professional / Youth) ---
         else:
             target_count = 26
             if real_players_data:
                 for rp in real_players_data:
                     if len(teammates) >= target_count:
                         break
                     val = safe_int_parse(rp.get("value", 0), 0)
                     age = safe_int_parse(rp.get("age", 25))
                     pos_str = rp.get("position", "MF")
                     pos_type = TeamGenerator.get_position_type(pos_str)
                     ca, pa = TeamGenerator.calculate_real_stats(val, age, pos_type)
                     if category == "Youth":
                         ca = ca * 0.85
                         pa = min(200, pa * 0.95)
                     # ★ここでは value をまだ入れず、あとで CA から一括計算する
                     teammates.append(NPC(
                         rp.get("name", "Unknown"),
                         "チームメイト",
                         0,
                         "実在選手",
                         ca,
                         pos_str,
                         safe_int_parse(rp.get("number", 0)),
                         age,
                         pa,
                         0,
                         rp.get("foot", "右"),
                         safe_int_parse(rp.get("height", 175))
                     ))
 
             current_count = len(teammates)
             if current_count < target_count:
                 for _ in range(target_count - current_count):
                     pos = random.choice(positions)
                     base = 90 if category == "Professional" else 40
                     ca = base + random.uniform(-20, 20)
                     age = 20
                     pos_type = TeamGenerator.get_position_type(pos)
                     # ここでも一旦 value=0 で作って、後でまとめて推定
-                    teammates.append(NPC(
-                        TeamGenerator.generate_random_name(),
-                        "チームメイト",
-                        0,
-                        "架空",
-                        ca,
-                        pos,
-                        0,
-                        age,
-                        ca + 10,
-                        0
-                    ))
+                    teammates.append(NPC(
+                        TeamGenerator.generate_random_name(),
+                        "チームメイト",
+                        0,
+                        "架空",
+                        ca,
+                        pos,
+                        0,
+                        age,
+                        ca + 10,
+                        0,
+                        height=_sample_height(pos)
+                    ))
 
             hierarchy_list = [
                 "スター選手", "重要な選手", "スタメン", "スタメン争い",
                 "ローテーション要員", "控え", "有望な若手", "放出前提の若手", "戦力外"
             ]
 
         # --- 序列割り当て (初期生成用) ---
         if category in ["University", "HighSchool"]:
             ...
         else:
             ...
 
         # ★全員について、CA・年齢・ポジションから市場価値を一括計算
         for t in teammates:
             pos_type = TeamGenerator.get_position_type(t.position)
             t.value = TeamGenerator.estimate_market_value(t.ca, t.age, pos_type)
 
         return teammates, formation_name
 
 
     # ★NEW: ユーザーが編集したリストからチームを確定する処理
     @staticmethod
     def finalize_team(category, formation_name, raw_members):
         if formation_name not in FORMATIONS:
             formation_name = random.choice(list(FORMATIONS.keys()))
         positions = FORMATIONS[formation_name]
 
         final_teammates = []
 
         # RawデータからNPCオブジェクト化
         for m in raw_members:
-            val = safe_int_parse(m.get("value", 0), 0)
-            age = safe_int_parse(m.get("age", 20))
-            pos_str = m.get("position", "MF")
-            current_ca = safe_int_parse(m.get("ca", 0))
-            ca = current_ca
-            pa = safe_int_parse(m.get("pa", 0))
+            val = safe_int_parse(m.get("value", 0), 0)
+            age = safe_int_parse(m.get("age", 20))
+            pos_str = m.get("position", "MF")
+            current_ca = safe_int_parse(m.get("ca", 0))
+            ca = current_ca
+            pa = safe_int_parse(m.get("pa", 0))
 
             # CA未設定なら計算
             if ca == 0:
                 pos_type = TeamGenerator.get_position_type(pos_str)
                 if category in ["University", "HighSchool"]:
                     base = 35 if category == "University" else 25
                     ca = base + random.uniform(-10, 30)
                     # 大学・高校は「ポテンシャル込みでプロに届くかもしれない」幅を持たせる
                     pa = min(150, ca + random.uniform(10, 35))
                 else:
                     ca, pa_est = TeamGenerator.calculate_real_stats(val, age, pos_type)
                     if category == "Youth":
                         ca *= 0.85
                     pa = pa_est
             else:
                 # CA はユーザー編集を尊重しつつ、PA=0 の場合は CA とカテゴリに応じて推定
                 if pa == 0:
                     if category in ["University", "HighSchool"]:
                         # 4-8 のレンジにだいたい沿うように CA からギャップを決める
                         if ca <= 37:
                             gap_min, gap_max = 15, 35   # 大学下位ベンチ〜将来ワンチャン
                         elif ca <= 50:
                             gap_min, gap_max = 10, 30   # C〜Bクラス
                         elif ca <= 70:
                             gap_min, gap_max = 5, 25    # Aチーム／JFL特指ライン
                         else:
                             gap_min, gap_max = 0, 20    # ほぼ完成
                         pa = min(150, ca + random.uniform(gap_min, gap_max))
                     else:
                         # プロ／ユース
                         pos_type = TeamGenerator.get_position_type(pos_str)
                         if val > 0:
                             _, pa_est = TeamGenerator.calculate_real_stats(val, age, pos_type)
                             pa = max(ca, pa_est)
                         else:
                             # 市場価値情報がないときは CA 基準でざっくり
                             if ca <= 90:
                                 gap_min, gap_max = 10, 30
                             elif ca <= 130:
                                 gap_min, gap_max = 5, 25
                             else:
                                 gap_min, gap_max = 0, 15
                             pa = min(200, ca + random.uniform(gap_min, gap_max))
 
-            npc = NPC(
-                m.get("name", "Unknown"),
-                "チームメイト",
-                0,
-                "Member",
-                ca,
-                pos_str,
-                safe_int_parse(m.get("number", 0)),
-                age,
-                pa,
-                val,
-                m.get("foot", "右"),
-                safe_int_parse(m.get("height", 175))
-            )
+            npc = NPC(
+                m.get("name", "Unknown"),
+                "チームメイト",
+                0,
+                "Member",
+                ca,
+                pos_str,
+                safe_int_parse(m.get("number", 0)),
+                age,
+                pa,
+                val,
+                m.get("foot", "右"),
+                safe_int_parse(m.get("height", _sample_height(pos_str)))
+            )
             final_teammates.append(npc)
 
         # 市場価値が 0 / 未設定の選手には CA・年齢・ポジションから推定値を付与
         for t in final_teammates:
             if not t.value or t.value <= 0:
                 pos_type = TeamGenerator.get_position_type(t.position)
                 t.value = TeamGenerator.estimate_market_value(t.ca, t.age, pos_type)
 
         # 序列と背番号の再割り当ては Player.update_hierarchy 側に任せる
         return final_teammates
 
 
 
 
 class Player:
     def __init__(
         self,
         name,
         position,
         age=18,
         attributes=None,
         funds=100000,
         salary=0,
         team_name="無所属",
         start_date=None
@@ -532,58 +599,57 @@ class Player:
         self.ca = 0.0
         self.pa = 150.0
         self.value = 0  # €換算の市場価値
         self.npcs = []
 
         # 故障リスク（0〜100想定）
         self.injury_risk = 0.0
 
         # ポジション適性とPAP
         self.position_apt = {p: 0.0 for p in POSSIBLE_POSITIONS}
         if self.position in self.position_apt:
             self.position_apt[self.position] = 20.0
         self.pap_max = 0.0
         self.pap_remaining = 0.0
 
         self.update_ca()  # CA / PAP / MarketValue 更新
 
     # =========================
     # 能力・成長関連
     # =========================
     def update_pap(self):
         """
         PAP_raw = Decisions+Anticipation+Composure+WorkRate+Teamwork+Positioning+OffTheBall+Vision+Versatility(仮)
         9〜180 → 20〜260に線形スケーリング
         """
-        mental_keys = [
-            "Decisions", "Anticipation", "Composure", "WorkRate",
-            "Teamwork", "Positioning", "OffTheBall", "Vision"
-        ]
-        # Versatility はとりあえず10固定（後でhidden属性を実装しても良い）
-        pap_raw = 10.0
-        for k in mental_keys:
-            pap_raw += self.attributes.get(k, 10.0)
+        mental_keys = [
+            "Decisions", "Anticipation", "Composure", "WorkRate",
+            "Teamwork", "Positioning", "OffTheBall", "Vision", "Versatility"
+        ]
+        pap_raw = 0.0
+        for k in mental_keys:
+            pap_raw += self.attributes.get(k, 10.0)
 
         src_min, src_max = 9.0, 180.0
         dst_min, dst_max = 20.0, 260.0
         ratio = (pap_raw - src_min) / (src_max - src_min)
         ratio = max(0.0, min(1.0, ratio))
         pap = dst_min + (dst_max - dst_min) * ratio
 
         self.pap_max = pap
         if self.pap_remaining == 0.0:
             self.pap_remaining = pap
 
     def update_ca(self):
         total_score = sum(self.attributes[key] * weight for key, weight in WEIGHTS.items())
         self.ca = (total_score / THEORETICAL_MAX_SCORE) * 200
 
         # PAP・市場価値もここで更新
         self.update_pap()
         pos_type = TeamGenerator.get_position_type(self.position)
         self.value = TeamGenerator.estimate_market_value(self.ca, self.age, pos_type)
 
     def grow_attribute(self, attr_name, amount):
         if attr_name in self.attributes:
             self.attributes[attr_name] = min(20.0, self.attributes[attr_name] + amount)
             self.update_ca()
             self.update_hierarchy()
 
EOF
)
