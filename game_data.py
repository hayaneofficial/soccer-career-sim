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

LAST_NAMES = ["佐藤", "鈴木", "高橋", "田中", "伊藤", "渡辺", "山本", "中村", "小林", "加藤",
              "吉田", "山田", "佐々木", "山口", "松本", "井上", "木村", "林", "斎藤", "清水"]
FIRST_NAMES = ["翔", "大翔", "蓮", "蒼", "湊", "樹", "悠真", "陽翔", "大和", "陽向",
               "陸", "海", "空", "翼", "健太", "拓哉", "直樹", "亮太", "達也", "駿"]

FOLDER_ID = "1_IVb-lZUdM2B_n6yLQIjhCEA1HQhlbfH"  # ★あなたのID

POSSIBLE_POSITIONS = [
    "CF", "OMF", "RWG", "LWG", "CMF", "DMF", "RMF", "LMF",
    "RWB", "LWB", "RSB", "LSB", "CB", "GK"
]


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


class NPC:
    def __init__(
        self,
        name,
        role,
        relation=0,
        description="",
        ca=0.0,
        position="",
        number=0,
        age=18,
        pa=0.0,
        value=0,
        foot="右",
        height=175
    ):
        self.name = name
        self.role = role
        self.relation = relation
        self.description = description
        self.ca = ca if ca is not None else 0.0
        self.pa = pa if pa is not None else self.ca
        self.position = position
        self.number = number
        self.age = age
        self.value = value
        self.foot = foot
        self.height = height
        self.hierarchy = ""

    def to_dict(self):
        return {
            "name": self.name,
            "role": self.role,
            "relation": self.relation,
            "description": self.description,
            "ca": self.ca,
            "pa": self.pa,
            "position": self.position,
            "number": self.number,
            "age": self.age,
            "value": self.value,
            "hierarchy": self.hierarchy,
            "foot": self.foot,
            "height": self.height
        }

    @classmethod
    def from_dict(cls, data):
        n = cls(
            data.get("name", ""),
            data.get("role", ""),
            data.get("relation", 0),
            data.get("description", ""),
            data.get("ca", 0.0),
            data.get("position", ""),
            data.get("number", 0),
            data.get("age", 18),
            data.get("pa", 0.0),
            data.get("value", 0),
            data.get("foot", "右"),
            data.get("height", 175)
        )
        n.hierarchy = data.get("hierarchy", "")
        return n


class TeamGenerator:
    @staticmethod
    def generate_random_name():
        return f"{random.choice(LAST_NAMES)} {random.choice(FIRST_NAMES)}"

    @staticmethod
    def get_position_type(pos):
        pos = pos.upper()
        if "GK" in pos:
            return 'GK'
        if any(x in pos for x in ["CB", "SB", "WB", "DF", "LB", "RB"]):
            return 'DEF'
        if any(x in pos for x in ["MF", "DM", "CM", "OM", "LM", "RM"]):
            return 'MID'
        if any(x in pos for x in ["FW", "ST", "WG", "CF", "RW", "LW"]):
            return 'FW'
        return 'MID'

    @staticmethod
    def calculate_real_stats(tm_value_euro, age, position_type):
        tm_value_euro = safe_int_parse(tm_value_euro, 100000)
        if tm_value_euro < 100000:
            tm_value_euro = 100000
        try:
            log_value = math.log(tm_value_euro)
        except Exception:
            log_value = 10.0

        alpha = 8.6
        beta = 0.7
        pos_bias = {'GK': 5.0, 'DEF': 3.0, 'MID': 0.0, 'FW': -3.0}
        gamma = pos_bias.get(position_type, 0.0)
        intercept = -22.0

        raw_ca = (alpha * log_value) + (beta * age) + gamma + intercept
        ca = int(max(1, min(195, raw_ca)))

        peak_age = 29
        remaining_years = max(0, peak_age - age)
        potential_premium = (log_value * 10) / ca if ca > 0 else 1.0
        growth_rate = 0.5
        if potential_premium > 1.25:
            growth_rate = 3.5
        elif potential_premium > 1.15:
            growth_rate = 2.5
        elif potential_premium > 1.05:
            growth_rate = 1.5

        if remaining_years > 0:
            raw_pa = ca + (growth_rate * remaining_years)
        else:
            raw_pa = ca + 4
        pa = int(max(ca, min(200, raw_pa)))
        return ca, pa

    @staticmethod
    def estimate_market_value(ca, age, position_type):
        """
        CA・年齢・ポジション種別から市場価値（ユーロ）を推定する。
        calculate_real_stats の逆関数的な近似。
        """
        if ca <= 0:
            return 100_000

        alpha = 8.6
        beta = 0.7
        intercept = -22.0
        pos_bias = {'GK': 5.0, 'DEF': 3.0, 'MID': 0.0, 'FW': -3.0}

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

        # --- 大学 (University) ---
        if category == "University":
            for grade in range(1, 5):
                for pos in positions:
                    for _ in range(2):
                        base_ca = 35 + (grade * 5) + random.uniform(-10, 10)
                        ca = min(80, max(33, base_ca))
                        pa = min(150, ca + random.uniform(10, 30))
                        teammates.append(NPC(
                            TeamGenerator.generate_random_name(),
                            "チームメイト",
                            0,
                            "",
                            ca,
                            pos,
                            0,
                            18 + grade,
                            pa
                        ))
            for i, pos in enumerate(positions):
                if i == 0:
                    continue
                ca = random.uniform(30, 36)
                grade = random.randint(1, 4)
                teammates.append(NPC(
                    TeamGenerator.generate_random_name(),
                    "チームメイト",
                    0,
                    "",
                    ca,
                    pos,
                    0,
                    18 + grade,
                    ca + 5
                ))
            hierarchy_list = HIERARCHY_UNI

        # --- 高校 (HighSchool) ---
        elif category == "HighSchool":
            for grade in range(1, 4):
                for pos in positions:
                    for _ in range(2):
                        base_ca = 25 + (grade * 10) + random.uniform(-10, 10)
                        ca = min(80, max(20, base_ca))
                        pa = min(150, ca + random.uniform(15, 40))
                        teammates.append(NPC(
                            TeamGenerator.generate_random_name(),
                            "チームメイト",
                            0,
                            "",
                            ca,
                            pos,
                            0,
                            15 + grade,
                            pa
                        ))
            for i, pos in enumerate(positions):
                if i == 0:
                    continue
                ca = random.uniform(15, 25)
                grade = random.randint(1, 3)
                teammates.append(NPC(
                    TeamGenerator.generate_random_name(),
                    "チームメイト",
                    0,
                    "",
                    ca,
                    pos,
                    0,
                    15 + grade,
                    ca + 10
                ))
            hierarchy_list = HIERARCHY_HS

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
                    teammates.append(NPC(
                        TeamGenerator.generate_random_name(),
                        "チームメイト",
                        0,
                        "架空",
                        ca,
                        pos,
                        0,
                        age,
                        ca + 10,
                        0
                    ))

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
            val = safe_int_parse(m.get("value", 0), 0)
            age = safe_int_parse(m.get("age", 20))
            pos_str = m.get("position", "MF")
            current_ca = safe_int_parse(m.get("ca", 0))
            ca = current_ca
            pa = safe_int_parse(m.get("pa", 0))

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

            npc = NPC(
                m.get("name", "Unknown"),
                "チームメイト",
                0,
                "Member",
                ca,
                pos_str,
                safe_int_parse(m.get("number", 0)),
                age,
                pa,
                val,
                m.get("foot", "右"),
                safe_int_parse(m.get("height", 175))
            )
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
    ):
        self.name = name
        self.position = position
        self.age = age
        self.current_date = start_date if start_date else datetime.date(2024, 4, 1)
        self.hp = 100
        self.mp = 100
        self.funds = funds
        self.salary = salary
        self.contract_years = 1 if salary > 0 else 4
        self.team_name = team_name
        self.team_rank = "D"
        self.offers = []
        self.team_category = "Professional"
        self.schedule = []
        self.team_members = []
        self.formation = "4-4-2"
        self.hierarchy = ""
        self.attributes = {}
        for key in WEIGHTS.keys():
            if attributes and key in attributes:
                self.attributes[key] = attributes[key]
            else:
                self.attributes[key] = 10.0
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
        mental_keys = [
            "Decisions", "Anticipation", "Composure", "WorkRate",
            "Teamwork", "Positioning", "OffTheBall", "Vision"
        ]
        # Versatility はとりあえず10固定（後でhidden属性を実装しても良い）
        pap_raw = 10.0
        for k in mental_keys:
            pap_raw += self.attributes.get(k, 10.0)

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
            return True
        return False

    def _factor_age(self):
        a = self.age
        # 15〜17歳
        if 15 <= a <= 17:
            return 1.15
        # 18〜20歳
        if 18 <= a <= 20:
            return 1.10
        # 21〜23歳
        if 21 <= a <= 23:
            return 1.00
        # 24〜27歳
        if 24 <= a <= 27:
            return 0.90
        # 28〜31歳
        if 28 <= a <= 31:
            return 0.80
        # 32歳以降（ひとまず固定値で運用）
        if a >= 32:
            return 0.70
        # 想定外（15歳未満など）はとりあえず1.0
        return 1.0


    def _factor_hp(self):
        return 0.10 + 0.90 * (self.hp / 100.0)

    def _factor_risk(self):
        risk = max(0.0, min(100.0, getattr(self, "injury_risk", 0.0)))
        return 1.0 - 0.30 * (risk / 100.0)

    def _factor_env(self):
        if not self.team_members:
            return 1.0
        avg_ca = sum(m.ca for m in self.team_members) / len(self.team_members)
        diff = avg_ca - self.ca
        diff = max(-40.0, min(40.0, diff))
        return 1.0 + 0.4 * (diff / 80.0)

    def _factor_gap(self):
        if self.pa <= 0:
            return 0.0
        gap = (self.pa - self.ca) / self.pa
        if gap <= 0:
            return 0.0
        return max(0.0, min(1.5, 0.5 + gap))

    def _factor_mental(self):
        keys = ["Determination", "WorkRate", "Teamwork", "Decisions", "Composure"]
        vals = [self.attributes.get(k, 10.0) for k in keys]
        avg = sum(vals) / len(vals)
        return 0.9 + (avg - 10.0) * (0.4 / 10.0)

    def compute_daily_growth_ca(self, base_intensity, performance):
        """
        1日の期待CA成長量を計算する。
        base_intensity: Base_total (0.0〜0.5程度)
        performance: 0.6〜1.5
        """
        f_age = self._factor_age()
        f_hp = self._factor_hp()
        f_risk = self._factor_risk()
        f_env = self._factor_env()
        f_gap = self._factor_gap()
        f_mental = self._factor_mental()

        multiplier = f_age * f_hp * f_risk * f_env * f_gap * f_mental
        actual = base_intensity * multiplier * performance
        return actual

    # ===== ポジション適性成長 =====
    def train_new_position(self, pos: str, intensity: float):
        """
        新ポジション練習時に呼ぶ想定。
        pos: 練習ポジション
        intensity: 0.0〜1.0
        """
        if pos not in self.position_apt:
            return
        current = self.position_apt[pos]
        if current >= 20.0:
            return
        if self.pap_remaining <= 0:
            return

        use = min(self.pap_remaining, 2.0 * intensity)
        self.pap_remaining -= use
        gain = use * 0.1
        self.position_apt[pos] = min(20.0, current + gain)

    # =========================
    # 時間進行・お金
    # =========================
    def advance_day(self, days=1):
        old_month = self.current_date.month
        old_weekday = self.current_date.weekday()
        self.current_date += datetime.timedelta(days=days)
        new_month = self.current_date.month
        new_weekday = self.current_date.weekday()

        logs = []
        if old_month != new_month:
            if self.salary > 0:
                pay = int(self.salary / 12)
                self.funds += pay
                logs.append(f"💰 給料日 +¥{pay:,}")
            else:
                self.funds += 50000
                logs.append("📩 仕送り +¥50,000")

        # 週次バッチ（月曜）でNPC成長
        if old_weekday != 0 and new_weekday == 0:
            self._advance_npcs_weekly()

        self.hp = min(100, self.hp + 5)
        return "\n".join(logs) if logs else None

    def _advance_npcs_weekly(self):
        """
        NPCのCAをPAへ向けて週次で少しずつ成長させる処理。
        成長後は CA・年齢・ポジションに応じて市場価値も再計算する。
        """
        for m in self.team_members:
            if m.name == self.name:
                continue
            if m.pa <= 0:
                continue
            gap = m.pa - m.ca
            if gap <= 0:
                continue

            if m.age <= 23:
                k = 0.05
            elif m.age <= 27:
                k = 0.03
            elif m.age <= 30:
                k = 0.02
            else:
                k = 0.01

            delta = max(0.01, gap * k)
            m.ca = min(m.pa, m.ca + delta)

            # ★ 成長後に市場価値を再計算
            pos_type = TeamGenerator.get_position_type(m.position)
            m.value = TeamGenerator.estimate_market_value(m.ca, m.age, pos_type)


    # =========================
    # チームまわり
    # =========================
    def transfer_to(self, offer):
        self.team_name = offer["team_name"]
        self.team_rank = offer["rank"]
        self.salary = offer["salary"]
        self.contract_years = offer["contract_years"]
        self.offers = []
        self.npcs = []
        self.schedule = []
        self.team_members = []
        return True

    def add_npc(self, npc):
        self.npcs.append(npc)

    def get_npc_by_role(self, role):
        for npc in self.npcs:
            if npc.role == role:
                return npc
        return None

    def update_hierarchy(self):
        me_in_list = next((m for m in self.team_members if m.name == self.name), None)
        if not me_in_list:
            # ★自分用NPCにも現在の市場価値を反映しておく
            me = NPC(
                self.name,
                "自分",
                0,
                "主人公",
                self.ca,
                self.position,
                99,
                self.age,
                self.pa,
                self.value
            )
            self.team_members.append(me)
        else:
            me_in_list.ca = self.ca
            me_in_list.pa = self.pa
            me_in_list.position = self.position
            me_in_list.value = self.value  # ★CA更新に合わせて市場価値も同期

        if self.team_category in ["University", "HighSchool"]:
            self._calc_school_hierarchy()
        else:
            self._calc_pro_hierarchy()

        me_final = next((m for m in self.team_members if m.name == self.name), None)
        if me_final:
            self.hierarchy = me_final.hierarchy


    def _calc_school_hierarchy(self):
        if self.formation not in FORMATIONS:
            return
        positions = FORMATIONS[self.formation]
        h_list = HIERARCHY_UNI if self.team_category == "University" else HIERARCHY_HS
        for m in self.team_members:
            if hasattr(m, "temp_assigned"):
                del m.temp_assigned
        pos_map = {p: [] for p in positions}
        for m in self.team_members:
            if m.position in pos_map:
                pos_map[m.position].append(m)
            else:
                found = False
                for p in positions:
                    if p in m.position or m.position in p:
                        if p not in pos_map:
                            pos_map[p] = []
                        pos_map[p].append(m)
                        found = True
                        break
        for p in pos_map:
            pos_map[p].sort(key=lambda x: x.ca, reverse=True)

        for h_idx, h_name in enumerate(h_list):
            start_num = (h_idx * 11) + 1
            for p_idx, pos_name in enumerate(positions):
                candidates = pos_map.get(pos_name, [])
                target = None
                for c in candidates:
                    if not getattr(c, "temp_assigned", False):
                        target = c
                        break
                if target:
                    target.hierarchy = h_name
                    target.number = start_num + p_idx
                    target.temp_assigned = True
        for m in self.team_members:
            if not getattr(m, "temp_assigned", False):
                m.hierarchy = h_list[-1]
                m.number = 99
            if hasattr(m, "temp_assigned"):
                del m.temp_assigned

    def _calc_pro_hierarchy(self):
        self.team_members.sort(key=lambda x: x.ca, reverse=True)
        ca_stamen = self.team_members[8].ca if len(self.team_members) > 8 else 0
        ca_bench = self.team_members[13].ca if len(self.team_members) > 13 else 0
        for i, m in enumerate(self.team_members):
            rank = i + 1
            if rank <= 2:
                m.hierarchy = "スター選手"
            elif rank <= 5:
                m.hierarchy = "重要な選手"
            elif rank <= 9:
                m.hierarchy = "スタメン"
            elif rank <= 14:
                m.hierarchy = "スタメン争い"
            elif rank <= 20:
                m.hierarchy = "ローテーション要員"
            else:
                if m.age <= 23:
                    if m.pa >= ca_stamen:
                        m.hierarchy = "有望な若手"
                    elif m.pa <= ca_bench:
                        m.hierarchy = "放出前提の若手"
                    else:
                        m.hierarchy = "控え"
                else:
                    m.hierarchy = "戦力外" if rank > 25 else "控え"

    def get_squad_status(self):
        return self.hierarchy, f"CA:{self.ca:.1f}"

    # =========================
    # セーブ／ロード用
    # =========================
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
            "offers": self.offers,
            "team_category": self.team_category,
            "schedule": self.schedule,
            "team_members": [t.to_dict() for t in self.team_members],
            "formation": self.formation,
            "hierarchy": self.hierarchy,
            "value": self.value,
            "injury_risk": self.injury_risk,
            "position_apt": self.position_apt,
            "pap_max": self.pap_max,
            "pap_remaining": self.pap_remaining
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
        p.salary = data.get("salary", 0)
        p.contract_years = data.get("contract_years", 1)
        p.team_name = data.get("team_name", "無所属")
        p.team_rank = data.get("team_rank", "D")
        p.offers = data.get("offers", [])
        p.team_category = data.get("team_category", "Professional")
        p.schedule = data.get("schedule", [])
        if "team_members" in data:
            p.team_members = [NPC.from_dict(n) for n in data["team_members"]]
        p.formation = data.get("formation", "4-4-2")
        p.hierarchy = data.get("hierarchy", "")
        if "npcs" in data:
            p.npcs = [NPC.from_dict(n) for n in data["npcs"]]

        p.value = data.get("value", 0)
        p.injury_risk = data.get("injury_risk", 0.0)

        # ポジション適性・PAP
        default_apt = {pos: 0.0 for pos in POSSIBLE_POSITIONS}
        saved_apt = data.get("position_apt", {})
        default_apt.update(saved_apt)
        p.position_apt = default_apt
        p.pap_max = data.get("pap_max", 0.0)
        p.pap_remaining = data.get("pap_remaining", p.pap_max)

        # CAから市場価値/PAPを一応再計算
        p.update_ca()
        return p


class MatchState:
    def __init__(self, player_name, player_position):
        self.score_ally = 0
        self.score_enemy = 0
        self.rows = [1, 2, 3, 4, 5, 6]
        self.cols = ["A", "B", "C", "D", "E"]
        self.player_pos = [3, "C"]
        self.ball_pos = self.player_pos.copy()

    def get_grid_df(self):
        data = [["　" for _ in self.cols] for _ in self.rows]
        return pd.DataFrame(data, columns=self.cols)


def save_game(player, filename="save_data.json"):
    service = get_drive_service()
    if not service:
        return
    query = f"name = '{filename}' and '{FOLDER_ID}' in parents"
    res = service.files().list(q=query, fields="files(id)").execute()
    files = res.get('files', [])
    data_str = json.dumps(player.to_dict(), ensure_ascii=False, indent=4)
    media = MediaIoBaseUpload(io.BytesIO(data_str.encode('utf-8')), mimetype='application/json')
    if files:
        service.files().update(fileId=files[0]['id'], media_body=media).execute()


def load_game(filename="save_data.json"):
    service = get_drive_service()
    if not service:
        return None
    query = f"name = '{filename}' and '{FOLDER_ID}' in parents"
    res = service.files().list(q=query, fields="files(id)").execute()
    files = res.get('files', [])
    if not files:
        return None
    file_id = files[0]['id']
    req = service.files().get_media(fileId=file_id)
    return Player.from_dict(json.loads(req.execute().decode('utf-8')))
