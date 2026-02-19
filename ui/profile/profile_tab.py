from PySide6.QtWidgets import QWidget, QVBoxLayout, QTabWidget, QLabel
from typing import Optional

from icon_resolver import IconResolver
from .player_selector import PlayerSelector
from .section_loader import load_player_index
from .sections.slayer_tab import SlayerTab
from .sections.dungeons_tab import DungeonsTab


class ProfileTab(QWidget):
    def __init__(self, icon_resolver: Optional[IconResolver] = None):
        super().__init__()

        self.icon_resolver = icon_resolver

        self.layout = QVBoxLayout(self)

        self.selector = PlayerSelector()
        self.selector.currentTextChanged.connect(self.reload_sections)

        self.tabs = QTabWidget()

        self.layout.addWidget(self.selector)
        self.layout.addWidget(self.tabs)

        if self.selector.count() > 0:
            self.reload_sections(self.selector.currentText())

    def reload_sections(self, pseudo: str):
        self.tabs.clear()

        index = load_player_index(pseudo)
        if not index:
            self.tabs.addTab(QLabel("No data"), "Error")
            return

        sections = index.get("written_sections", [])

        if "slayer.json" in sections:
            self.tabs.addTab(
                SlayerTab(pseudo, icon_resolver=self.icon_resolver),
                "Slayer"
            )

        if "dungeons.json" in sections:
            self.tabs.addTab(
                DungeonsTab(pseudo),  # tu pourras aussi lui injecter le resolver plus tard
                "Dungeons"
            )
