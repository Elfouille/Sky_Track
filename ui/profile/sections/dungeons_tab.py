from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from ..section_loader import load_section


class DungeonsTab(QWidget):
    def __init__(self, pseudo: str):
        super().__init__()

        layout = QVBoxLayout(self)

        data = load_section(pseudo, "dungeons")
        dungeons = data.get("dungeons", {}) if data else {}

        cata = (
            dungeons.get("dungeon_types", {})
            .get("catacombs", {})
            .get("experience", 0)
        )

        layout.addWidget(QLabel(f"Catacombs XP: {cata:,}"))
