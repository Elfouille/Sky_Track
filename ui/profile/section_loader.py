from pathlib import Path
import json


CACHE_ROOT = Path("cache/UI/profile/sections")


def load_player_index(pseudo: str):
    path = CACHE_ROOT / pseudo / "index.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_section(pseudo: str, section: str):
    path = CACHE_ROOT / pseudo / f"{section}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
