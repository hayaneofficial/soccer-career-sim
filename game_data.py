import random
import json
import datetime
import streamlit as st
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

# --- 定数定義 ---
WEIGHTS = {
    "Decisions": 4.0, "Anticipation": 3.5, "Composure": 3.5, "Concentration": 3.0,
    "WorkRate": 3.0, "Teamwork": 2.5, "Positioning": 2.5, "OffTheBall": 2.5,
    "Vision": 2.5, "Determination": 2.0, "Aggression": 1.5, "Bravery": 1.5,
    "Flair": 1.0, "Leadership": 1.0,
    "Acceleration": 5.0, "Pace": 5.0, "Stamina": 4.0, "NaturalFitness": 3.5,
    "Agility": 3.5, "Strength": 3.0, "Balance": 2.5, "JumpingReach": 2.5,
    "Passing": 4.0, "FirstTouch": 4.0, "Technique": 3.5, "Dribbling": 2.5,
    "Tackling": 2.5, "Marking": 2.5, "Finishing": 2.5, "Heading": 2.0,
    "Crossing": 2.0, "LongShots": 1.5, "PenaltyTaking": 1.0, "FreeKickTaking": 1.0,
    "Corners": 1.0, "LongThrows": 0.5,
    "WeakFoot": 9.0
}
THEORETICAL_MAX_SCORE = sum(WEIGHTS.values()) * 20

# ★ランク定義
TEAM_RANKS = {
    "S": {"name": "欧州1部", "req_ca": 150, "avg_salary": 300000000},
    "A": {"name": "J1上位", "req_ca": 120, "avg_salary": 80000000},
    "B": {"name": "J1中下位", "req_ca": 100, "avg_salary": 30000000},
    "C": {"name": "J2", "req_ca": 80, "avg_salary": 10000000},
    "D": {"name": "J3/JFL", "req_ca": 50, "avg_salary": 4000000}
}

# --- Google Drive 接続用 ---
# ★ここにご自身のフォルダIDを入れてください
FOLDER_ID = "1_IVb-lZUdM2B_n6yLQIjhCEA1HQhlbfH" 

def get_drive_service():
    if "gcp_json" not in st.secrets: return None
    try:
        creds_dict = json.loads(st.secrets["gcp_json"])
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=['https://www.googleapis.com/auth/drive']
        )
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Drive接続エラー: {e}")
        return None

# --- NPCクラス ---
class NPC:
    def __init__(self, name, role, relation=0, description="", ca=0.0):
        self.name = name
        self.role = role
        self.relation = relation
        self.description = description
        # ★安全策: caがNoneなら0.0にする
        self.ca = ca if ca is not None else 0.0

    def to_dict(self):
        return {
            "name": self.name,
            "role": self.role,
            "relation": self.relation,
            "description": self.description,
            "ca": self.ca
        }
    
    @classmethod
    def from_dict(cls, data):
        # ★読み込み時の安全策: getで取得した後、Noneなら0.0にする
        ca_val = data.get("ca")
        if ca_val is None: ca_val = 0.0
        
        return cls(
            data["name"], 
            data["role"], 
            data["relation"], 
            data.get("description", ""),
            ca_val
        )

# --- Playerクラス ---
class Player:
    def __init__(self, name, position, age=18, attributes=None):
        self.name = name
        self.position = position
        self.age = age
        self.current_date = datetime.date(2024, 4, 1)
        self.hp = 100
        self.mp = 100
        
        # 経済・契約
        self.funds = 100000
        self.salary = 4800000
        self.contract_years = 1
        
        # チーム情報
        self.team_name = "南葛SC (初期)"
        self.team_rank = "D"
        self.offers = []
        
        self.attributes = {}
        for key in WEIGHTS.keys():
            if attributes and key in attributes:
                self.attributes[key] = attributes[key]
            else:
                self.attributes[key] = 10.0
            
        self.ca = 0.0
        self.pa = 150.0
        self.update_ca()
        self.npcs = [] 

    def update_ca(self):
        total_score = sum(self.attributes[key] * weight for key, weight in WEIGHTS.items())
        self.ca = (total_score / THEORETICAL_MAX_SCORE) * 200

    def grow_attribute(self, attr_name, amount):
        if attr_name in self.attributes:
            self.attributes[attr_name] = min(20.0, self.attributes[attr_name] + amount)
            self.update_ca()
            return True
        return False
    
    def advance_day(self, days=1):
        old_month = self.current_date.month
        self.current_date += datetime.timedelta(days=days)
        new_month = self.current_date.month
        
        logs = []
        
        # 給料日
        if old_month != new_month:
            monthly_pay = int(self.salary / 12)
            self.funds += monthly_pay
            logs.append(f"💰 給料日が来ました！ +¥{monthly_pay:,}")
        
        # 自然回復
        self.hp = min(100, self.hp + 5)
        
        # オファー抽選
        current_rank_info = TEAM_RANKS.get(self.team_rank, TEAM_RANKS["D"])
        next_ranks = [r for r, info in TEAM_RANKS.items() if info["req_ca"] <= self.ca + 10]
        
        if len(self.offers) < 3 and random.random() < 0.10:
            if next_ranks:
                target_rank = random.choice(next_ranks)
                info = TEAM_RANKS[target_rank]
                offer_salary = int(info["avg_salary"] * random.uniform(0.8, 1.2))
                
                prefixes = ["FC", "AS", "SC", "レアル", "ユナイテッド"]
                cities = ["東京", "大阪", "横浜", "ロンドン", "マドリード", "ミュンヘン"]
                team_name = f"{random.choice(prefixes)}{random.choice(cities)}"
                
                new_offer = {
                    "team_name": team_name,
                    "rank": target_rank,
                    "salary": offer_salary,
                    "contract_years": random.randint(1, 3)
                }
                self.offers.append(new_offer)
                logs.append(f"📩 {team_name} ({target_rank}ランク) からオファーが届きました！")

        return "\n".join(logs) if logs else None

    def transfer_to(self, offer):
        self.team_name = offer["team_name"]
        self.team_rank = offer["rank"]
        self.salary = offer["salary"]
        self.contract_years = offer["contract_years"]
        self.offers = []
        self.npcs = [] 
        return True

    def add_npc(self, npc):
        self.npcs.append(npc)

    def get_npc_by_role(self, role):
        for npc in self.npcs:
            if npc.role == role:
                return npc
        return None
    
    def get_squad_status(self):
        manager = self.get_npc_by_role("監督")
        rival = self.get_npc_by_role("ライバル")
        
        if not manager: return "スタメン", "監督不在"

        trust_bonus = max(0, manager.relation * 0.2) 
        my_score = self.ca + trust_bonus
        
        if not rival:
            if my_score > 80: return "スタメン", "ライバル不在"
            else: return "ベンチ外", "実力不足"
            
        # ★修正: ライバルのCAがNoneの場合のガード
        rival_score = rival.ca if rival.ca is not None else 0.0
        
        if my_score > rival_score + 2:
            return "スタメン", f"ライバル({rival.name})に勝利"
        elif my_score > rival_score - 2:
            return "スタメン争い", f"ライバル({rival.name})と拮抗"
        else:
            return "ベンチ", f"ライバル({rival.name})の後塵"

    def to_dict(self):
        return {
            "name": self.name,
            "position": self.position,
            "age": self.age,
            "current_date": self.current_date.strftime("%Y-%m-%d"),
            "attributes": self.attributes,
            "hp": self.hp,
            "mp": self.mp,
            "ca": self.ca,
            "pa": self.pa,
            "npcs": [npc.to_dict() for npc in self.npcs],
            "funds": self.funds,
            "salary": self.salary,
            "contract_years": self.contract_years,
            "team_name": self.team_name,
            "team_rank": self.team_rank,
            "offers": self.offers
        }

    @classmethod
    def from_dict(cls, data):
        p = cls(data["name"], data["position"], data["age"])
        y, m, d = map(int, data["current_date"].split("-"))
        p.current_date = datetime.date(y, m, d)
        
        loaded_attrs = data["attributes"]
        p.attributes = {}
        for key in WEIGHTS.keys():
             p.attributes[key] = loaded_attrs.get(key, 10.0)

        p.hp = data["hp"]
        p.mp = data["mp"]
        p.ca = data["ca"]
        p.pa = data["pa"]
        p.funds = data.get("funds", 100000)
        p.salary = data.get("salary", 4800000)
        p.contract_years = data.get("contract_years", 1)
        p.team_name = data.get("team_name", "南葛SC (初期)")
        p.team_rank = data.get("team_rank", "D")
        p.offers = data.get("offers", [])

        if "npcs" in data:
            p.npcs = [NPC.from_dict(n) for n in data["npcs"]]
        return p

# --- 試合ステートクラス ---
class MatchState:
    def __init__(self, player_name, player_position):
        self.score_ally = 0
        self.score_enemy = 0
        self.rows = [1, 2, 3, 4, 5, 6]
        self.cols = ["A", "B", "C", "D", "E"]
        if "FW" in player_position or "WG" in player_position:
            self.player_pos = [2, "C"]
        elif "MF" in player_position:
            self.player_pos = [3, "C"]
        else:
            self.player_pos = [5, "C"]
        self.ball_pos = self.player_pos.copy()

    def get_grid_df(self):
        data = [["　" for _ in self.cols] for _ in self.rows]
        col_map = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}
        try:
            p_r = int(self.player_pos[0]) - 1
            p_c = col_map[self.player_pos[1]]
            data[p_r][p_c] = "🧍"
        except: pass
        try:
            b_r = int(self.ball_pos[0]) - 1
            b_c = col_map[self.ball_pos[1]]
            if self.ball_pos == self.player_pos:
                data[b_r][b_c] = "🧍⚽"
            else:
                data[b_r][b_c] = "⚽"
        except: pass
        return pd.DataFrame(data, index=["敵G前", "敵陣深", "敵陣浅", "自陣浅", "自陣深", "自G前"], columns=self.cols)

# --- セーブ＆ロード関数 ---
def save_game(player, filename="save_data.json"):
    service = get_drive_service()
    if not service: return
    query = f"name = '{filename}' and '{FOLDER_ID}' in parents"
    results = service.files().list(q=query, fields="files(id)").execute()
    files = results.get('files', [])
    data_str = json.dumps(player.to_dict(), ensure_ascii=False, indent=4)
    media = MediaIoBaseUpload(io.BytesIO(data_str.encode('utf-8')), mimetype='application/json')
    if files:
        service.files().update(fileId=files[0]['id'], media_body=media).execute()
    else:
        pass 

def load_game(filename="save_data.json"):
    service = get_drive_service()
    if not service: return None
    query = f"name = '{filename}' and '{FOLDER_ID}' in parents"
    results = service.files().list(q=query, fields="files(id)").execute()
    files = results.get('files', [])
    if not files: return None
    file_id = files[0]['id']
    request = service.files().get_media(fileId=file_id)
    file_data = request.execute()
    return Player.from_dict(json.loads(file_data.decode('utf-8')))