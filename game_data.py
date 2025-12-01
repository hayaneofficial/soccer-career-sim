import random
import json
import datetime
import pandas as pd

# 要件定義書 4-2. 能力値ウェイト定義
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

class Player:
    def __init__(self, name, position, age=18, attributes=None):
        self.name = name
        self.position = position
        self.age = age
        self.current_date = datetime.date(2024, 4, 1)
        
        self.hp = 100
        self.mp = 100
        
        # ★ここを修正しました（安全装置）
        # 全てのウェイトキー（Decisionsなど）をループして確認する
        self.attributes = {}
        for key in WEIGHTS.keys():
            # Geminiから渡されたデータの中にキーがあればそれを使う
            if attributes and key in attributes:
                self.attributes[key] = attributes[key]
            else:
                # なければデフォルト値10.0を入れる
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
        
        # JSONから読み込む時も、万が一キーが足りなければ補完するようにマージする
        loaded_attrs = data["attributes"]
        p.attributes = {}
        for key in WEIGHTS.keys():
             p.attributes[key] = loaded_attrs.get(key, 10.0)

        p.hp = data["hp"]
        p.mp = data["mp"]
        p.ca = data["ca"]
        p.pa = data["pa"]
        return p

def save_game(player, filename="save_data.json"):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(player.to_dict(), f, ensure_ascii=False, indent=4)

def load_game(filename="save_data.json"):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Player.from_dict(data)
    except FileNotFoundError:
        return None
    
    # --- 以下、game_data.py の末尾に追加してください ---

# --- game_data.py の末尾の MatchState クラスをこれに差し替え ---
import pandas as pd # ファイルの一番上にこれを書くのがベストですが、ここでインポートしても動きます

class MatchState:
    def __init__(self, player_name, player_position):
        self.score_ally = 0
        self.score_enemy = 0
        self.rows = [1, 2, 3, 4, 5, 6]
        self.cols = ["A", "B", "C", "D", "E"]
        
        # ★ここを「ポジションごとの分岐」に戻します
        if "FW" in player_position or "WG" in player_position:
            self.player_pos = [2, "C"] # FWは敵陣深く
        elif "MF" in player_position:
            self.player_pos = [3, "C"] # MFは中盤
        else:
            self.player_pos = [5, "C"] # DFは自陣
            
        self.ball_pos = self.player_pos.copy()

    def get_grid_df(self):
        """現在の配置をきれいな表データとして返す"""
        # 1. 空っぽの6x5の表を作る（中身は全角スペースで埋める）
        data = [["　" for _ in self.cols] for _ in self.rows]
        
        # 2. 列番号を数字(0~4)に変換する辞書
        col_map = {"A": 0, "B": 1, "C": 2, "D": 3, "E": 4}
        
        # 3. プレイヤーを配置
        # int()で囲むことで、Geminiが文字で返してきても強制的に数字にする
        try:
            p_r = int(self.player_pos[0]) - 1 # 行番号(1-6)をインデックス(0-5)に
            p_c = col_map[self.player_pos[1]]
            data[p_r][p_c] = "🧍"
        except:
            pass # エラー時は配置しない（透明人間回避）

        # 4. ボールを配置
        try:
            b_r = int(self.ball_pos[0]) - 1
            b_c = col_map[self.ball_pos[1]]
            
            # プレイヤーと同じ位置ならセット表示
            if self.ball_pos == self.player_pos:
                data[b_r][b_c] = "🧍⚽"
            else:
                data[b_r][b_c] = "⚽"
        except:
            pass

        # 5. DataFrame（表）を作成
        df = pd.DataFrame(data, index=["敵G前", "敵陣深", "敵陣浅", "自陣浅", "自陣深", "自G前"], columns=self.cols)
        return df