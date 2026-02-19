from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from PySide6.QtGui import QIcon
except Exception:  # permet d'utiliser le resolver sans UI
    QIcon = None  # type: ignore


# -----------------------------------------------------------------------------
# Defaults
# -----------------------------------------------------------------------------
DEFAULT_ROOT = Path(__file__).resolve().parent
DEFAULT_CACHE_DIR = DEFAULT_ROOT / "cache"
DEFAULT_ICONS_DIR = DEFAULT_CACHE_DIR / "icones"
DEFAULT_NEU_REPO = DEFAULT_CACHE_DIR / "NEU" / "repo"

# Vanilla textures source
MCASSET_ITEM_BASE = "https://mcasset.cloud/latest/assets/minecraft/textures/item"
MCASSET_BLOCK_BASE = "https://mcasset.cloud/latest/assets/minecraft/textures/block"

# Retry HTTP
RETRY_TOTAL = 4
RETRY_BACKOFF = 0.4
RETRY_STATUS = (429, 500, 502, 503, 504)

# minimal PNG sanity
MIN_PNG_BYTES = 250


# -----------------------------------------------------------------------------
# HTTP helper
# -----------------------------------------------------------------------------
def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=RETRY_TOTAL,
        connect=RETRY_TOTAL,
        read=RETRY_TOTAL,
        status=RETRY_TOTAL,
        backoff_factor=RETRY_BACKOFF,
        status_forcelist=list(RETRY_STATUS),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=16, pool_maxsize=16)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    s.headers.update(
        {
            "User-Agent": "Sky_Track/1.0 (icons) Python requests",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        }
    )
    return s


def is_probably_png(data: bytes) -> bool:
    return len(data) > MIN_PNG_BYTES and data[:8] == b"\x89PNG\r\n\x1a\n"


def download_png(session: requests.Session, url: str) -> Optional[bytes]:
    try:
        r = session.get(url, timeout=(10, 20))
        if r.status_code != 200:
            return None
        b = r.content
        return b if is_probably_png(b) else None
    except Exception:
        return None


def save_png_atomic(dest: Path, content: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    tmp.write_bytes(content)
    tmp.replace(dest)


# -----------------------------------------------------------------------------
# Hypixel skull decoding
# -----------------------------------------------------------------------------
def extract_skull_texture_url(base64_value: str) -> Optional[str]:
    try:
        decoded = base64.b64decode(base64_value).decode("utf-8", errors="replace")
        obj = json.loads(decoded)
        url = obj.get("textures", {}).get("SKIN", {}).get("url")
        if isinstance(url, str) and url.startswith("http"):
            return url
    except Exception:
        pass
    return None


# -----------------------------------------------------------------------------
# Vanilla mapping (inclut support legacy "WOOL:4", etc.)
# -----------------------------------------------------------------------------
WOOL_COLORS = {
    0: "white", 1: "orange", 2: "magenta", 3: "light_blue",
    4: "yellow", 5: "lime", 6: "pink", 7: "gray",
    8: "light_gray", 9: "cyan", 10: "purple", 11: "blue",
    12: "brown", 13: "green", 14: "red", 15: "black",
}

DYE_FROM_INK_SACK = {
    0: "ink_sac",
    1: "red_dye",
    2: "green_dye",
    3: "cocoa_beans",
    4: "lapis_lazuli",
    5: "purple_dye",
    6: "cyan_dye",
    7: "light_gray_dye",
    8: "gray_dye",
    9: "pink_dye",
    10: "lime_dye",
    11: "dandelion_yellow",
    12: "light_blue_dye",
    13: "magenta_dye",
    14: "orange_dye",
    15: "bone_meal",
}

_slug_rx = re.compile(r"[^a-z0-9_]+")


def split_material_meta(material: str) -> Tuple[str, Optional[int]]:
    # accepte "WOOL:4" ou "STAINED_GLASS:15"
    if not material:
        return "", None
    s = material.strip()
    if ":" in s:
        a, b = s.split(":", 1)
        try:
            return a, int(b)
        except Exception:
            return a, None
    return s, None


def vanilla_candidates(material: str, durability: Any) -> List[Tuple[str, str]]:
    """
    Return list of (kind, name) where kind in {"item","block"} and name is png basename.
    """
    base, meta = split_material_meta(material)
    m = base.strip().lower().replace(" ", "_")
    m = _slug_rx.sub("_", m).strip("_")

    # override meta if durability present
    if meta is None and isinstance(durability, (int, float)):
        meta = int(durability)

    out: List[Tuple[str, str]] = []

    if m == "wool" and meta is not None and meta in WOOL_COLORS:
        return [("block", f"{WOOL_COLORS[meta]}_wool")]

    if m == "stained_glass" and meta is not None and meta in WOOL_COLORS:
        return [("block", f"{WOOL_COLORS[meta]}_stained_glass")]

    if m == "stained_glass_pane" and meta is not None and meta in WOOL_COLORS:
        return [
            ("item", f"{WOOL_COLORS[meta]}_stained_glass_pane"),
            ("block", f"{WOOL_COLORS[meta]}_stained_glass_pane"),
        ]

    if m == "carpet" and meta is not None and meta in WOOL_COLORS:
        return [("block", f"{WOOL_COLORS[meta]}_carpet")]

    if m in ("ink_sack", "dye") and meta is not None:
        name = DYE_FROM_INK_SACK.get(meta)
        if name:
            return [("item", name)]

    # generic attempts
    out.append(("item", m))
    out.append(("block", m))

    # renames
    if m == "gold_sword":
        out.append(("item", "golden_sword"))
    if m.startswith("gold_"):
        out.append(("item", "golden_" + m[5:]))

    # dedup
    seen = set()
    final: List[Tuple[str, str]] = []
    for k, n in out:
        if (k, n) not in seen:
            seen.add((k, n))
            final.append((k, n))
    return final


def vanilla_urls(material: str, durability: Any) -> List[str]:
    urls: List[str] = []
    for kind, name in vanilla_candidates(material, durability):
        base = MCASSET_ITEM_BASE if kind == "item" else MCASSET_BLOCK_BASE
        urls.append(f"{base}/{name}.png")
    return urls


# -----------------------------------------------------------------------------
# NEU lookup (rapide + safe)
# -----------------------------------------------------------------------------
def neu_assets_roots(neu_repo: Path) -> List[Path]:
    roots: List[Path] = []
    if not neu_repo.exists():
        return roots

    for rel in [
        "assets/neu/textures",
        "assets/minecraft/textures",
        "assets/NotEnoughUpdates/textures",
        "textures",
    ]:
        p = neu_repo / rel
        if p.exists():
            roots.append(p)
    return roots


def find_neu_png_for_item_id(neu_repo: Path, item_id: str) -> Optional[Path]:
    """
    Fast paths only: no expensive global rglob for each resolve.
    """
    item_id = (item_id or "").strip()
    if not item_id:
        return None

    roots = neu_assets_roots(neu_repo)
    if not roots:
        return None

    fast_rel = [
        f"item/{item_id}.png",
        f"items/{item_id}.png",
        f"{item_id}.png",
    ]

    for root in roots:
        for rel in fast_rel:
            p = root / rel
            if p.exists():
                return p

    # limited subdirs
    for root in roots:
        for sub in ("item", "items", "gui", "block"):
            d = root / sub
            if d.exists() and d.is_dir():
                p = d / f"{item_id}.png"
                if p.exists():
                    return p

    return None


def copy_neu_png_to_cache(neu_png: Path, dest: Path) -> bool:
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(neu_png.read_bytes())
        return True
    except Exception:
        return False


# -----------------------------------------------------------------------------
# Missing placeholder (optional)
# -----------------------------------------------------------------------------
def ensure_missing_png(path: Path) -> None:
    """
    Create a tiny transparent PNG if possible.
    If Pillow isn't installed, we just do nothing (user can add their own file).
    """
    if path.exists():
        return
    try:
        from PIL import Image  # pillow
        img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(path), format="PNG")
    except Exception:
        # no pillow or cannot write; user can provide _missing.png manually
        return


# -----------------------------------------------------------------------------
# Resolver (main)
# -----------------------------------------------------------------------------
@dataclass
class IconResolver:
    cache_dir: Path = DEFAULT_CACHE_DIR
    icons_dir: Path = DEFAULT_ICONS_DIR
    neu_repo: Path = DEFAULT_NEU_REPO

    def __post_init__(self) -> None:
        self.icons_dir.mkdir(parents=True, exist_ok=True)
        self._session = make_session()
        self._missing = self.icons_dir / "_missing.png"
        ensure_missing_png(self._missing)

    def icon_path(self, item_id: str) -> Path:
        return self.icons_dir / f"{item_id}.png"

    def resolve_path(self, item_id: str, hypixel_item_obj: Optional[Dict[str, Any]] = None) -> Path:
        """
        Returns a local PNG Path.
        Creates it if missing:
          1) cache
          2) NEU
          3) Hypixel skull URL
          4) vanilla (mcasset)
          5) _missing.png
        """
        item_id = (item_id or "").strip()
        dest = self.icon_path(item_id)

        # 0) already cached
        if dest.exists():
            return dest

        # 1) NEU
        neu_png = find_neu_png_for_item_id(self.neu_repo, item_id)
        if neu_png and copy_neu_png_to_cache(neu_png, dest):
            return dest

        # 2) Hypixel skull
        if isinstance(hypixel_item_obj, dict):
            skin = hypixel_item_obj.get("skin")
            if isinstance(skin, dict):
                v = skin.get("value")
                if isinstance(v, str) and v:
                    url = extract_skull_texture_url(v)
                    if url:
                        b = download_png(self._session, url)
                        if b:
                            save_png_atomic(dest, b)
                            return dest

        # 3) Vanilla
        if isinstance(hypixel_item_obj, dict):
            material = hypixel_item_obj.get("material") or ""
            durability = hypixel_item_obj.get("durability")
            for url in vanilla_urls(str(material), durability):
                b = download_png(self._session, url)
                if b:
                    save_png_atomic(dest, b)
                    return dest

        # 4) missing
        return self._missing if self._missing.exists() else dest

    def resolve_icon(self, item_id: str, hypixel_item_obj: Optional[Dict[str, Any]] = None):
        """
        Convenience for PySide6: returns QIcon if available, else returns Path.
        """
        p = self.resolve_path(item_id, hypixel_item_obj)
        if QIcon is None:
            return p
        return QIcon(str(p))
