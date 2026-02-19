from pathlib import Path

from PySide6.QtWidgets import QMainWindow, QTabWidget

from icon_resolver import IconResolver
from .profile.profile_tab import ProfileTab


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Sky Track")
        self.resize(1200, 800)

        # ✅ Singleton IconResolver
        self.icon_resolver = IconResolver(
            cache_dir=Path("cache"),
            icons_dir=Path("cache/icones"),
            neu_repo=Path("cache/NEU/repo"),
        )

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # ✅ on passe le resolver au ProfileTab
        self.tabs.addTab(ProfileTab(icon_resolver=self.icon_resolver), "Profils")
