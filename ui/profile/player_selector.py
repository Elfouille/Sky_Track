from PySide6.QtWidgets import QComboBox
from pathlib import Path


def get_players():
    root = Path("cache/UI/profile/sections")
    if not root.exists():
        return []
    return sorted([p.name for p in root.iterdir() if p.is_dir()])


class PlayerSelector(QComboBox):
    def __init__(self):
        super().__init__()
        self.refresh()

    def refresh(self):
        self.clear()
        players = get_players()
        self.addItems(players)
