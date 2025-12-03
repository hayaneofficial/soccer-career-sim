"""Core data models and helpers for the football career simulator.

This module focuses on stable, lightweight data structures that the
Streamlit UI in ``app.py`` relies on. The previous version accidentally
duplicated UI code and missed key constants/classes such as ``WEIGHTS``
and ``Player``; this rewrite restores those foundations so the app can
run without undefined references.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# --- Ability weights (FM-like attributes) ---------------------------------
# The weights are intentionally modest and balanced; they are only used for
# CA/PA preview calculations inside the UI.
WEIGHTS: Dict[str, float] = {
    "Decisions": 1.2,
    "Anticipation": 1.1,
    "Composure": 1.0,
    "WorkRate": 1.0,
    "Teamwork": 1.0,
    "Positioning": 1.0,
    "OffTheBall": 1.0,
    "Vision": 1.0,
    "Versatility": 0.9,
    "Flair": 0.8,
    "Dribbling": 1.0,
    "Finishing": 1.0,
    "FirstTouch": 1.0,
    "Passing": 1.0,
    "Tackling": 1.0,
    "Marking": 1.0,
    "Heading": 0.9,
    "Pace": 1.0,
    "Acceleration": 1.0,
    "Stamina": 1.0,
    "Strength": 1.0,
    "Balance": 0.8,
    "JumpingReach": 0.8,
    "Agility": 0.8,
    "Concentration": 0.9,
    "Determination": 0.9,
    "Leadership": 0.8,
    "Bravery": 0.8,
    "Aggression": 0.6,
    "WeakFoot": 0.6,
    # Mental/hidden style attributes often requested by the prompt
    "Adaptability": 0.5,
    "Ambition": 0.5,
    "Controversy": 0.3,
    "Loyalty": 0.5,
    "Pressure": 0.5,
    "Professionalism": 0.7,
    "Sportsmanship": 0.4,
    "Temperament": 0.4,
    "InjuryProneness": 0.3,
    "ImportantMatches": 0.5,
    "Dirtiness": 0.3,
}

THEORETICAL_MAX_SCORE = sum(20 * w for w in WEIGHTS.values())


# --- Data classes ---------------------------------------------------------
@dataclasses.dataclass
class NPC:
    name: str
    role: str
    relation: float = 0.0
    description: str = ""

    def to_dict(self) -> Dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class TeamMember:
    name: str
    position: str
    number: int = 0
    age: int = 20
    ca: float = 90.0
    pa: float = 120.0
    height_cm: int = 175
    value: int = 0
    grade: str = ""
    transfer_flag: bool = False
    hierarchy: int = 0

    def to_dict(self) -> Dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class Player:
    name: str
    position: str
    age: int
    attributes: Dict[str, float]
    funds: int = 0
    salary: int = 0
    team_name: str = ""
    team_category: str = "Professional"
    start_date: Optional[datetime.date] = None
    birthday: Optional[datetime.date] = None
    grade: str = ""
    pa: float = 150.0
    hp: int = 100
    mp: int = 100
    schedule: List[Dict] = dataclasses.field(default_factory=list)
    team_members: List[TeamMember] = dataclasses.field(default_factory=list)
    npcs: List[NPC] = dataclasses.field(default_factory=list)
    team_weekly_plan: List[Dict] = dataclasses.field(default_factory=list)
    position_apt: Dict[str, float] = dataclasses.field(default_factory=dict)
    formation: str = ""
    agent_type: str = ""
    competitions: List[Dict] = dataclasses.field(default_factory=list)
    living_standard: str = "標準"
    school_timetable: List[Dict] = dataclasses.field(default_factory=list)
    transfer_offers: List[Dict] = dataclasses.field(default_factory=list)

    def __post_init__(self):
        self.current_date = self.start_date or datetime.date.today()
        if self.birthday is None and self.start_date:
            # 初期値として開始日を誕生日扱いにする（後で編集可能）
            self.birthday = self.start_date
        if not self.grade:
            self.grade = TeamGenerator._grade_label(self.team_category, self.age)
        self.attributes = self._fill_missing_attributes(self.attributes)
        self.ca = self._compute_ca()

    # --- Core helpers --------------------------------------------------
    def _fill_missing_attributes(self, attrs: Dict[str, float]) -> Dict[str, float]:
        merged = {k: 10.0 for k in WEIGHTS.keys()}
        for k, v in (attrs or {}).items():
            if k in merged and v is not None:
                try:
                    merged[k] = float(v)
                except Exception:
                    merged[k] = 10.0
        return merged

    def _compute_ca(self) -> float:
        total = sum(self.attributes[k] * WEIGHTS[k] for k in WEIGHTS.keys())
        return (total / THEORETICAL_MAX_SCORE) * 200

    def compute_pap(self) -> float:
        """Return PAP (汎用性) score based on vision/decision-making attributes."""
        keys = [
            "Decisions",
            "Anticipation",
            "Composure",
            "WorkRate",
            "Teamwork",
            "Positioning",
            "OffTheBall",
            "Vision",
            "Versatility",
        ]
        pap_raw = sum(self.attributes.get(k, 10.0) for k in keys)
        pap = 20 + (pap_raw - 9) * (240 / 171)
        return max(0.0, pap)

    def add_npc(self, npc: NPC) -> None:
        self.npcs.append(npc)

    def grow_attribute(self, key: str, amount: float) -> None:
        if key not in self.attributes:
            return
        self.attributes[key] = max(1.0, min(20.0, self.attributes[key] + amount))
        self.ca = self._compute_ca()

    def compute_daily_growth_ca(self, base_intensity: float, performance: float) -> float:
        # A simple heuristic: base intensity (0-1) scaled by performance (0-1.5)
        return max(0.0, base_intensity * performance * 5)

    def advance_day(self, days: int = 1) -> None:
        self.apply_daily_upkeep(days)
        prev_date = self.current_date
        self.current_date += datetime.timedelta(days=days)
        self._handle_age_and_grade_rollover(prev_date, self.current_date)

    def apply_daily_upkeep(self, days: int = 1) -> None:
        """Reduce HP/MP and funds based on stamina/adaptability and living standard."""
        level_cost = {"節約": 1000, "標準": 3000, "充実": 8000}
        cost_per_day = level_cost.get(self.living_standard, 3000)
        if hasattr(self, "funds"):
            self.funds = max(0, self.funds - cost_per_day * max(1, days))

        stamina = self.attributes.get("Stamina", 10.0)
        adapt = self.attributes.get("Adaptability", 10.0)
        base_drain = 8.0
        base_drain -= stamina / 3.0
        base_drain -= adapt / 4.0
        if self.living_standard == "節約":
            base_drain += 2.0
        elif self.living_standard == "充実":
            base_drain -= 1.0
        per_day = max(1.0, base_drain)
        total = int(per_day * max(1, days))
        self.hp = max(0, self.hp - total)

    def update_hierarchy(self) -> None:
        def score(member: TeamMember) -> float:
            base = float(getattr(member, "ca", 0))
            # 微小な変動を付けることで、CA差が小さい場合に序列が揺らぐ
            jitter = random.uniform(-2.0, 2.0)
            return base + jitter

        self.team_members.sort(key=score, reverse=True)

        # CA差5以内はコンディション（仮にHP/MPを参照）でイーブンに揺らす
        for i in range(len(self.team_members) - 1):
            a = self.team_members[i]
            b = self.team_members[i + 1]
            diff = abs(float(getattr(a, "ca", 0)) - float(getattr(b, "ca", 0)))
            if diff <= 5:
                form_factor = (self.hp + self.mp) / 200 if hasattr(self, "hp") else 0.5
                if diff <= 1 or random.random() < form_factor:
                    self.team_members[i], self.team_members[i + 1] = b, a
        # イーブン競争後に序列を付与
        for idx, member in enumerate(self.team_members, start=1):
            member.hierarchy = idx

        # プレイヤー自身の序列を保存（UI表示用）
        my_member = next((m for m in self.team_members if m.name == self.name), None)
        self.hierarchy = my_member.hierarchy if my_member else None

    def _handle_age_and_grade_rollover(self, old_date: datetime.date, new_date: datetime.date) -> None:
        """Advance age on birthday and promote school grades at fiscal year end."""
        # 誕生日: old_date < birthday <= new_date なら年齢を加算
        if self.birthday:
            for year in range(old_date.year, new_date.year + 1):
                bday = self.birthday.replace(year=year)
                if old_date < bday <= new_date:
                    self.age += 1

        # 学年進級: 3/31を跨いだら昇級（高校3→卒業、大学4→卒業で据え置き）
        if self.team_category in ("HighSchool", "University"):
            for year in range(old_date.year, new_date.year + 1):
                cutoff = datetime.date(year, 3, 31)
                if old_date < cutoff <= new_date:
                    self._promote_grade()
                    for m in self.team_members:
                        m.grade = self._promote_grade_label(m.grade)
                        m.age = max(m.age, 0) + 1

    def _promote_grade(self) -> None:
        self.grade = self._promote_grade_label(self.grade)

    @staticmethod
    def _promote_grade_label(grade: str) -> str:
        match = None
        if grade:
            match = grade[0]
        year_num = None
        if match and match.isdigit():
            year_num = int(match)
        if year_num is None:
            return grade or ""
        if year_num >= 4:
            return "卒業"
        next_year = year_num + 1
        if next_year >= 4:
            return "卒業"
        return f"{next_year}年"

    # --- Persistence ---------------------------------------------------
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "position": self.position,
            "age": self.age,
            "attributes": self.attributes,
            "funds": self.funds,
            "salary": self.salary,
            "team_name": self.team_name,
            "team_category": self.team_category,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "birthday": self.birthday.isoformat() if self.birthday else None,
            "grade": self.grade,
            "pa": self.pa,
            "hp": self.hp,
            "mp": self.mp,
            "current_date": self.current_date.isoformat(),
            "schedule": self.schedule,
            "team_members": [m.to_dict() for m in self.team_members],
            "npcs": [n.to_dict() for n in self.npcs],
            "team_weekly_plan": self.team_weekly_plan,
            "position_apt": self.position_apt,
            "formation": self.formation,
            "agent_type": self.agent_type,
            "competitions": self.competitions,
            "living_standard": self.living_standard,
            "school_timetable": self.school_timetable,
            "transfer_offers": self.transfer_offers,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Player":
        start_date = (
            datetime.date.fromisoformat(data.get("start_date"))
            if data.get("start_date")
            else None
        )
        player = cls(
            name=data.get("name", ""),
            position=data.get("position", ""),
            age=int(data.get("age", 18)),
            attributes=data.get("attributes", {}),
            funds=int(data.get("funds", 0)),
            salary=int(data.get("salary", 0)),
            team_name=data.get("team_name", ""),
            team_category=data.get("team_category", "Professional"),
            start_date=start_date,
            birthday=(
                datetime.date.fromisoformat(data.get("birthday"))
                if data.get("birthday")
                else None
            ),
            grade=data.get("grade", ""),
            pa=float(data.get("pa", 150.0)),
            hp=int(data.get("hp", 100)),
            mp=int(data.get("mp", 100)),
        )
        player.current_date = datetime.date.fromisoformat(
            data.get("current_date", datetime.date.today().isoformat())
        )
        player.schedule = data.get("schedule", [])
        player.team_members = [TeamMember(**m) for m in data.get("team_members", [])]
        player.npcs = [NPC(**n) for n in data.get("npcs", [])]
        player.team_weekly_plan = data.get("team_weekly_plan", [])
        player.position_apt = data.get("position_apt", {})
        player.formation = data.get("formation", "")
        player.agent_type = data.get("agent_type", "")
        player.competitions = data.get("competitions", [])
        player.living_standard = data.get("living_standard", "標準")
        player.school_timetable = data.get("school_timetable", [])
        player.transfer_offers = data.get("transfer_offers", [])
        player.update_hierarchy()
        return player


# --- Team generation utilities -------------------------------------------
class TeamGenerator:
    DEFAULT_FORMATIONS: Dict[str, str] = {
        "Professional": "4-3-3",
        "University": "4-4-2",
        "HighSchool": "4-4-2",
        "Youth": "4-3-3",
    }

    LAST_NAMES = [
        "佐藤", "鈴木", "高橋", "田中", "伊藤", "渡辺", "山本", "中村", "小林", "加藤",
        "吉田", "山田", "佐々木", "山口", "松本", "井上", "木村", "林", "斎藤", "清水",
        "阿部", "森", "池田", "橋本", "山崎", "石川", "石井", "松田", "野口", "村上",
        "岡本", "酒井", "長谷川", "藤田", "西村", "原田", "福田", "岡田", "中島", "藤井",
        "青木", "上田", "柴田", "宮崎", "前田", "秋山", "北川", "久保", "堂安", "南野",
        "安部", "鎌田", "冨安", "遠藤", "田畑", "大森", "大谷", "川崎", "島田", "榊原",
        "石原", "杉本", "川口", "吉岡", "前川", "栗原", "福島", "黒田", "永田", "近藤",
    ]
    FIRST_NAMES = [
        "太一", "翔太", "大輔", "悠斗", "颯太", "陽向", "健太", "蓮", "大和", "隼人",
        "蒼", "拓海", "悠真", "陽翔", "結衣", "陽菜", "美咲", "さくら", "真央", "愛",
        "結愛", "心春", "凜", "紗季", "美月", "琴音", "瑛斗", "蒼空", "海斗", "涼介",
        "悠生", "瑠偉", "航太", "勇人", "隼人", "大智", "聡太", "玲央", "陽大", "恭介",
        "結菜", "美波", "愛莉", "心乃", "莉子", "心愛", "陽葵", "美羽", "七海", "杏奈",
    ]

    POSITIONS_POOL = [
        "GK", "RSB", "CB", "LSB", "DMF", "CMF", "OMF", "RWG", "LWG", "CF"
    ]

    @classmethod
    def _random_name(cls) -> str:
        return f"{random.choice(cls.LAST_NAMES)} {random.choice(cls.FIRST_NAMES)}"

    @staticmethod
    def _sample_ca(category: str) -> float:
        roll = random.random()
        if category == "HighSchool":
            # 0.5% for 80+, smooth tapering above 60
            if roll > 0.995:
                return random.uniform(80, 90)
            if roll > 0.97:
                return random.uniform(70, 80)
            if roll > 0.9:
                return random.uniform(60, 70)
            if roll > 0.7:
                return random.uniform(50, 60)
            if roll > 0.45:
                return random.uniform(40, 50)
            if roll > 0.15:
                return random.uniform(30, 40)
            return random.uniform(20, 30)
        if category == "University":
            if roll > 0.995:
                return random.uniform(100, 110)
            if roll > 0.97:
                return random.uniform(90, 100)
            if roll > 0.9:
                return random.uniform(80, 90)
            if roll > 0.75:
                return random.uniform(70, 80)
            if roll > 0.55:
                return random.uniform(60, 70)
            if roll > 0.35:
                return random.uniform(50, 60)
            if roll > 0.15:
                return random.uniform(40, 50)
            return random.uniform(30, 40)
        # professional / youth fallback
        return random.uniform(70, 130)

    @staticmethod
    def _sample_pa() -> float:
        roll = random.random()
        if roll > 0.999:
            return random.uniform(150, 170)
        if roll > 0.995:
            return random.uniform(140, 150)
        if roll > 0.98:
            return random.uniform(130, 140)
        if roll > 0.96:
            return random.uniform(120, 130)
        if roll > 0.9:
            return random.uniform(110, 120)
        if roll > 0.7:
            return random.uniform(90, 110)
        if roll > 0.5:
            return random.uniform(80, 90)
        if roll > 0.3:
            return random.uniform(70, 80)
        return random.uniform(50, 70)

    @staticmethod
    def _sample_height(position: str) -> int:
        pos_upper = position.upper()
        roll = random.random()
        is_center_forward = any(tag in pos_upper for tag in ["CF", "RCF", "LCF"])
        is_center_back = any(tag in pos_upper for tag in ["CB", "RCB", "LCB"])
        if pos_upper == "GK":
            if roll > 0.8:
                return random.randint(190, 197)
            if roll > 0.1:
                return random.randint(180, 189)
            if roll > 0.0:
                return random.randint(170, 179)
        if is_center_back or is_center_forward:
            if roll > 0.95:
                return random.randint(190, 195)
            if roll > 0.35:
                return random.randint(180, 189)
            if roll > 0.15:
                return random.randint(170, 179)
            return random.randint(165, 169)
        # fullbacks/wingers/others
        if roll > 0.85:
            return random.randint(185, 192)
        if roll > 0.2:
            return random.randint(175, 184)
        return random.randint(165, 174)

    @classmethod
    def _grade_label(cls, category: str, age: int) -> str:
        if category == "HighSchool":
            if age <= 15:
                return "1年"
            if age == 16:
                return "2年"
            return "3年"
        if category == "University":
            if age <= 18:
                return "1年"
            if age == 19:
                return "2年"
            if age == 20:
                return "3年"
            return "4年"
        return ""

    @classmethod
    def generate_teammates(
        cls, category: str, formation: str, real_players: List[Dict]
    ) -> Tuple[List[TeamMember], str]:
        formation = formation or cls.DEFAULT_FORMATIONS.get(category, "4-4-2")
        members: List[TeamMember] = []

        for p in real_players:
            age = int(p.get("age", 22))
            members.append(
                TeamMember(
                    name=p.get("name", cls._random_name()),
                    position=p.get("position", random.choice(cls.POSITIONS_POOL)),
                    number=int(p.get("number", len(members) + 1)),
                    age=age,
                    ca=float(p.get("ca", cls._sample_ca(category))),
                    pa=float(p.get("pa", cls._sample_pa())),
                    height_cm=int(p.get("height_cm", cls._sample_height(p.get("position", "")))),
                    value=int(p.get("value", random.randint(50_000, 500_000))),
                    grade=cls._grade_label(category, age),
                )
            )

        while len(members) < 25:
            age = random.randint(17, 34)
            members.append(
                TeamMember(
                    name=cls._random_name(),
                    position=random.choice(cls.POSITIONS_POOL),
                    number=len(members) + 1,
                    age=age,
                    ca=cls._sample_ca(category),
                    pa=cls._sample_pa(),
                    height_cm=cls._sample_height(random.choice(cls.POSITIONS_POOL)),
                    value=random.randint(10_000, 200_000),
                    grade=cls._grade_label(category, age),
                )
            )

        return members, formation

    @classmethod
    def finalize_team(
        cls, category: str, formation: str, raw_members: List[Dict]
    ) -> List[TeamMember]:
        finalized: List[TeamMember] = []
        for m in raw_members:
            age = int(m.get("age", 20))
            finalized.append(
                TeamMember(
                    name=m.get("name", cls._random_name()),
                    position=m.get("position", random.choice(cls.POSITIONS_POOL)),
                    number=int(m.get("number", m.get("No", len(finalized) + 1))),
                    age=age,
                    ca=float(m.get("ca", m.get("CA", 80.0))),
                    pa=float(m.get("pa", m.get("PA", 120.0))),
                    height_cm=int(m.get("height_cm", cls._sample_height(m.get("position", "")))),
                    value=int(m.get("value", m.get("Value", 0))),
                    grade=m.get("grade") or cls._grade_label(category, age),
                )
            )
        return finalized


# --- Persistence helpers --------------------------------------------------
SAVE_PATH = Path("save.json")


def save_game(player: Player, path: Path = SAVE_PATH) -> None:
    path.write_text(json.dumps(player.to_dict(), ensure_ascii=False, indent=2))


def load_game(path: Path = SAVE_PATH) -> Optional[Player]:
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    try:
        return Player.from_dict(data)
    except Exception:
        return None
