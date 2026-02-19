from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QProgressBar,
    QGroupBox,
    QFormLayout,
)

from icon_resolver import IconResolver
from ..section_loader import load_section


# --------------------------------------------------------------------------------------
# Slayer XP tables (local, simple, stable)
# --------------------------------------------------------------------------------------
XP_TABLES: Dict[str, List[int]] = {
    "zombie":   [5, 15, 200, 1000, 5000, 20000, 100000, 400000, 1000000],
    "spider":   [5, 25, 200, 1000, 5000, 20000, 100000, 400000, 1000000],
    "wolf":     [10, 30, 250, 1500, 5000, 20000, 100000, 400000, 1000000],
    "enderman": [10, 30, 250, 1500, 5000, 20000, 100000, 400000, 1000000],
    "blaze":    [10, 30, 250, 1500, 5000, 20000, 100000, 400000, 1000000],
    "vampire":  [20, 75, 240, 840, 2400],
}

BOSS_LABELS = {
    "zombie": "Zombie",
    "spider": "Spider",
    "wolf": "Wolf",
    "enderman": "Enderman",
    "blaze": "Blaze",
    "vampire": "Vampire",
}

BOSS_ORDER = ["zombie", "spider", "wolf", "enderman", "blaze", "vampire"]

QUEST_STATE = {
    0: "Unknown",
    1: "Active",
    2: "Completed",
    3: "Failed",
}

# Boss -> an item_id-like key for the IconResolver (best-effort)
# You can replace these with real SkyBlock item IDs later if you want perfect icons.
BOSS_ICON_IDS = {
    "zombie": "ROTTEN_FLESH",
    "spider": "SPIDER_EYE",
    "wolf": "BONE",
    "enderman": "ENDER_PEARL",
    "blaze": "BLAZE_ROD",
    "vampire": "GHAST_TEAR",  # placeholder
}


# --------------------------------------------------------------------------------------

def fmt_int(n: int) -> str:
    return f"{int(n):,}".replace(",", " ")


def ms_to_dt_str(ts_ms: Optional[int]) -> str:
    if not ts_ms:
        return "—"
    return datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class SlayerLevelProgress:
    level: int
    level_max: int
    xp: int
    curr_req: int
    next_req: Optional[int]
    pct_to_next: int
    xp_to_next: Optional[int]


def compute_level_progress(boss_type: str, xp: int) -> SlayerLevelProgress:
    table = XP_TABLES.get(boss_type, [])
    if not table:
        return SlayerLevelProgress(0, 0, xp, 0, None, 0, None)

    lvl = 0
    for i, req in enumerate(table, start=1):
        if xp >= req:
            lvl = i
        else:
            break

    lvl_max = len(table)

    if lvl == 0:
        next_req = table[0]
        pct = int((xp / next_req) * 100) if next_req else 0
        return SlayerLevelProgress(0, lvl_max, xp, 0, next_req, pct, next_req - xp)

    if lvl >= lvl_max:
        return SlayerLevelProgress(lvl_max, lvl_max, xp, table[-1], None, 100, None)

    curr_req = table[lvl - 1]
    next_req = table[lvl]
    span = max(1, next_req - curr_req)
    pct = int(((xp - curr_req) / span) * 100)
    return SlayerLevelProgress(lvl, lvl_max, xp, curr_req, next_req, pct, next_req - xp)


def extract_tier_stats(info: Dict[str, Any]) -> Tuple[List[int], List[int]]:
    kills = [0] * 6
    attempts = [0] * 6
    for t in range(6):
        kills[t] = int(info.get(f"boss_kills_tier_{t}", 0) or 0)
        attempts[t] = int(info.get(f"boss_attempts_tier_{t}", 0) or 0)
    return kills, attempts


def compact_tier_line(kills: List[int], attempts: List[int]) -> str:
    parts = []
    for t in range(len(kills)):
        if kills[t] or attempts[t]:
            parts.append(f"T{t} {kills[t]}/{attempts[t]}")
    return " | ".join(parts) if parts else "—"


# --------------------------------------------------------------------------------------

class SlayerTab(QWidget):
    def __init__(self, pseudo: str, icon_resolver: Optional[IconResolver] = None):
        super().__init__()

        self.icon_resolver = icon_resolver

        root = QVBoxLayout(self)

        data = load_section(pseudo, "slayer") or {}
        slayer = data.get("slayer", {}) if isinstance(data, dict) else {}
        bosses = slayer.get("slayer_bosses", {}) if isinstance(slayer, dict) else {}
        quest = slayer.get("slayer_quest", {}) if isinstance(slayer, dict) else {}

        # HEADER
        header = QHBoxLayout()
        title = QLabel(f"Slayer — {pseudo}")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        header.addWidget(title)
        header.addStretch()

        total_xp = 0
        if isinstance(bosses, dict):
            total_xp = sum(int((b or {}).get("xp", 0) or 0) for b in bosses.values() if isinstance(b, dict))

        header.addWidget(QLabel(f"Total Slayer XP: {fmt_int(total_xp)}"))
        root.addLayout(header)

        # ACTIVE QUEST
        root.addWidget(self._build_active_quest_card(quest if isinstance(quest, dict) else {}))

        # TABLE
        root.addWidget(self._build_boss_table(bosses if isinstance(bosses, dict) else {}))

        root.addStretch()

    # ----------------------------------------------------------------------------------

    def _build_active_quest_card(self, quest: Dict[str, Any]) -> QWidget:
        box = QGroupBox("Active Quest")
        form = QFormLayout(box)

        if not quest:
            form.addRow("Status:", QLabel("No active quest"))
            return box

        form.addRow("Boss:", QLabel(str(quest.get("type", "—"))))
        form.addRow("Tier:", QLabel(str(quest.get("tier", "—"))))
        form.addRow("State:", QLabel(QUEST_STATE.get(int(quest.get("completion_state", 0) or 0), "Unknown")))
        form.addRow("Combat XP:", QLabel(fmt_int(int(quest.get("combat_xp", 0) or 0))))
        form.addRow("Solo:", QLabel("Yes" if quest.get("solo") else "No"))

        # (optionnel) timestamps si dispo
        if "start_timestamp" in quest:
            form.addRow("Start:", QLabel(ms_to_dt_str(quest.get("start_timestamp"))))
        if "spawn_timestamp" in quest:
            form.addRow("Spawn:", QLabel(ms_to_dt_str(quest.get("spawn_timestamp"))))
        if "kill_timestamp" in quest:
            form.addRow("Kill:", QLabel(ms_to_dt_str(quest.get("kill_timestamp"))))

        return box

    # ----------------------------------------------------------------------------------

    def _build_boss_table(self, bosses: Dict[str, Any]) -> QWidget:
        box = QGroupBox("Bosses")
        layout = QVBoxLayout(box)

        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels([
            "Boss",
            "Level",
            "XP",
            "Progress",
            "Tiers",
            "Success",
        ])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)

        keys = [b for b in BOSS_ORDER if b in bosses] + [b for b in bosses.keys() if b not in BOSS_ORDER]
        table.setRowCount(len(keys))

        for r, boss_key in enumerate(keys):
            info = bosses.get(boss_key, {})
            if not isinstance(info, dict):
                info = {}

            xp = int(info.get("xp", 0) or 0)
            prog = compute_level_progress(boss_key, xp)
            kills, attempts = extract_tier_stats(info)

            total_kills = sum(kills)
            total_attempts = sum(attempts)
            success = (total_kills / total_attempts * 100.0) if total_attempts else 0.0

            boss_name = BOSS_LABELS.get(boss_key, boss_key)
            item = QTableWidgetItem(boss_name)

            # ✅ icône best-effort
            if self.icon_resolver:
                icon_id = BOSS_ICON_IDS.get(boss_key, boss_key.upper())
                icon = self.icon_resolver.resolve_icon(icon_id, None)
                item.setIcon(icon)

            table.setItem(r, 0, item)
            table.setItem(r, 1, QTableWidgetItem(f"{prog.level}/{prog.level_max}"))
            table.setItem(r, 2, QTableWidgetItem(fmt_int(xp)))

            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(prog.pct_to_next)
            bar.setFormat(f"{prog.pct_to_next}%")
            table.setCellWidget(r, 3, bar)

            table.setItem(r, 4, QTableWidgetItem(compact_tier_line(kills, attempts)))
            table.setItem(r, 5, QTableWidgetItem(f"{success:.1f}%"))

        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(table)

        return box
