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

# --- Google Drive 接続用関数 ---
def get_drive_service():
    """SecretsのJSONを使ってDrive APIに接続する"""
    if "gcp_json" not in st.secrets:
        return None
    
    try:
        # JSON文字列を辞書に変換
        creds_dict = json.loads(st.secrets["gcp_json"])
        # 認証情報オブジェクトを作成
        creds = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/drive']
        )
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Drive接続エラー: {e}")
        return None

def get_folder_id(service, folder_name="SoccerSimData"):
    """共有されたフォルダのIDを探す"""
    query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder'"
    results = service.files().list(q=query, fields="files(id)").execute()
    items = results.get('files', [])
    if items:
        return items[0]['id']
    return None

# --- Playerクラス ---
class Player:
    def __init__(self, name, position, age=18, attributes=None):
        self.name = name
        self.position = position
        self.age = age
        self.current_date = datetime.date(2024, 4, 1)
        self.hp = 100
        self.mp = 100
        
        self.attributes = {}
        for key in WEIGHTS.keys():
            if attributes and key in attributes:
                self.attributes[key] = attributes[key]
            else:
                self.attributes[key] = 10.0
            
        self.ca = 0.0
        self.pa = 150.0
        self.update_ca()

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
        self.current_date += datetime.timedelta(days=days)
        self.hp = min(100, self.hp + 5)

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
            "pa": self.pa
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

# --- セーブ＆ロード関数 (Google Drive対応版) ---

def save_game(player, filename="save_data.json"):
    """Google Driveに保存する"""
    # データ作成
    data_str = json.dumps(player.to_dict(), ensure_ascii=False, indent=4)
    media = MediaIoBaseUpload(io.BytesIO(data_str.encode('utf-8')), mimetype='application/json')
    
    service = get_drive_service()
    if not service:
        st.error("Google Driveに接続できません。Secretsを確認してください。")
        return

    # フォルダを探す
    folder_id = get_folder_id(service, "SoccerSimData")
    
    # 既存ファイルを探す
    query = f"name = '{filename}'"
    if folder_id:
        query += f" and '{folder_id}' in parents"
        
    results = service.files().list(q=query, fields="files(id)").execute()
    files = results.get('files', [])

    if files:
        # 上書き保存
        file_id = files[0]['id']
        service.files().update(fileId=file_id, media_body=media).execute()
    else:
        # 新規作成
        file_metadata = {'name': filename}
        if folder_id:
            file_metadata['parents'] = [folder_id]
        service.files().create(body=file_metadata, media_body=media).execute()

def load_game(filename="save_data.json"):
    """Google Driveから読み込む"""
    service = get_drive_service()
    if not service:
        return None
        
    # --- ここから下を書き換えてください ---

# ★ここにコピーしたフォルダIDを貼り付けてください！
FOLDER_ID = "1_IVb-lZUdM2B_n6yLQIjhCEA1HQhlbfH" 

def get_drive_service():
    """SecretsのJSONを使ってDrive APIに接続する"""
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

# フォルダを探す関数はもう不要なので削除してもいいですが、
# 念のため残す場合は使わないようにします。

# --- セーブ＆ロード関数 (ID指定・上書き専用版) ---

def save_game(player, filename="save_data.json"):
    """Google Driveの既存ファイルを上書き保存する"""
    service = get_drive_service()
    if not service:
        st.error("Google Driveに接続できません。")
        return

    # 1. まずフォルダ内のファイルを探す
    query = f"name = '{filename}' and '{FOLDER_ID}' in parents"
    results = service.files().list(q=query, fields="files(id)").execute()
    files = results.get('files', [])

    # データ作成
    data_str = json.dumps(player.to_dict(), ensure_ascii=False, indent=4)
    media = MediaIoBaseUpload(io.BytesIO(data_str.encode('utf-8')), mimetype='application/json')

    if files:
        # ★ある場合：上書き保存（これなら容量エラーが出ない！）
        file_id = files[0]['id']
        service.files().update(fileId=file_id, media_body=media).execute()
        # st.success("クラウドに保存しました！") # 毎回出るとうるさいのでコメントアウト
    else:
        # ★ない場合：エラーを出す（ロボットは新規作成できないため）
        st.error(f"Driveに '{filename}' が見つかりません。PCから手動でアップロードしてください。")

def load_game(filename="save_data.json"):
    """Google Driveから読み込む"""
    service = get_drive_service()
    if not service:
        return None
        
    # IDを使ってピンポイントで探す
    query = f"name = '{filename}' and '{FOLDER_ID}' in parents"
    results = service.files().list(q=query, fields="files(id)").execute()
    files = results.get('files', [])
    
    if not files:
        return None
        
    file_id = files[0]['id']
    request = service.files().get_media(fileId=file_id)
    file_data = request.execute()
    
    return Player.from_dict(json.loads(file_data.decode('utf-8')))