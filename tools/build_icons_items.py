# D:\DEV\Hypixel\App\Sky_Track\V3\Sky_Track\tools\build_icons_items.py
from __future__ import annotations

import argparse
import base64
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from PIL import Image


# ============================================================
# Project paths / IO
# ============================================================

def _default_cache_dir() -> Path:
    """
    Try to import common.CACHE_DIR from the project.
    Fallback: ../cache relative to this file.
    """
    try:
        from common import CACHE_DIR  # type: ignore
        return Path(CACHE_DIR)
    except Exception:
        return (Path(__file__).resolve().parents[1] / "cache").resolve()


CACHE_DIR = _default_cache_dir()

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Sky_Track/1.0"
SKINS_DIR = CACHE_DIR / "MCASSET" / "skins"
SKINS_CACHE_JSON = SKINS_DIR / "_skins_cache.json"


def load_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def safe_filename(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"[^\w\-.]+", "_", s, flags=re.UNICODE)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "unknown"


def strip_mc_codes(s: str) -> str:
    # "§fAcacia Slab" -> "Acacia Slab"
    return re.sub(r"§.", "", s or "")


def clean_model_name(s: str) -> str:
    """
    "minecraft:acacia_fence" -> "acacia_fence"
    "acacia_fence" -> "acacia_fence"
    """
    if not s:
        return ""
    s = s.strip()
    if ":" in s:
        s = s.split(":", 1)[1]
    return s.strip().lower()


def fmt_time(seconds: float) -> str:
    if seconds < 0:
        return "--"
    s = int(seconds + 0.5)
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    if h > 0:
        return f"{h}h{m:02d}m{sec:02d}s"
    if m > 0:
        return f"{m}m{sec:02d}s"
    return f"{sec}s"


# ============================================================
# Progress + ETA (global)
# ============================================================

class Progress:
    def __init__(self, total: int):
        self.total = max(1, int(total))
        self.start = time.time()
        self.lock = threading.Lock()
        self.done = 0
        self.label = ""
        self.stats = {
            "built": 0,
            "skipped": 0,
            "failed": 0,
            "skulls": 0,
            "models": 0,
            "vanilla_itemid": 0,
            "fallback_itemid": 0,
            "downloaded": 0,
            "cached": 0,
            "skip_fail_cache": 0,
        }

    def inc_done(self, n: int = 1) -> None:
        with self.lock:
            self.done += n

    def set_label(self, s: str) -> None:
        with self.lock:
            self.label = (s or "")[:70]

    def inc_stat(self, key: str, n: int = 1) -> None:
        with self.lock:
            self.stats[key] = self.stats.get(key, 0) + n

    def snapshot(self) -> Tuple[int, int, Dict[str, int], str, float]:
        with self.lock:
            return self.done, self.total, dict(self.stats), self.label, self.start

    def render(self, final: bool = False) -> None:
        done, total, stats, label, start = self.snapshot()
        width = 34
        ratio = min(1.0, max(0.0, done / total))
        filled = int(width * ratio)
        bar = "█" * filled + "░" * (width - filled)
        pct = int(ratio * 100)

        elapsed = time.time() - start
        rate = done / elapsed if elapsed > 0 else 0.0
        eta = (total - done) / rate if rate > 1e-9 else -1.0

        tail = (
            f"{done:>5}/{total:<5} {pct:>3}%  "
            f"ETA {fmt_time(eta)}  "
            f"built={stats['built']} skip={stats['skipped']} fail={stats['failed']}  "
            f"skull={stats['skulls']} model={stats['models']} vanilla={stats['vanilla_itemid']} fb={stats['fallback_itemid']}  "
            f"dl={stats['downloaded']} cache={stats['cached']} badcache={stats['skip_fail_cache']}"
        )
        if label:
            tail += f"  {label}"

        print(f"\r[{bar}] {tail}", end="", flush=True)
        if final:
            print()


# ============================================================
# Image helpers
# ============================================================

@dataclass
class IconBuildResult:
    ok: bool
    out_path: Optional[Path]
    source_texture: Optional[str]
    method: str
    reason: str


def _ensure_rgba(img: Image.Image) -> Image.Image:
    return img.convert("RGBA") if img.mode != "RGBA" else img


def build_player_head_icon(skin_png: Path, out_png: Path, size: int = 64) -> IconBuildResult:
    """
    Player skin head icon:
      - face: (8,8)-(16,16)
      - hat:  (40,8)-(48,16) overlay
    """
    if not skin_png.exists():
        return IconBuildResult(False, None, str(skin_png), "player_head", "missing skin png")

    try:
        img = _ensure_rgba(Image.open(skin_png))
        w, h = img.size
        if w < 16 or h < 16:
            return IconBuildResult(False, None, str(skin_png), "player_head", f"skin too small: {w}x{h}")

        face = img.crop((8, 8, 16, 16))
        head = face.copy()

        if w >= 48 and h >= 16:
            hat = img.crop((40, 8, 48, 16))
            head.alpha_composite(hat)

        head = head.resize((size, size), resample=Image.NEAREST)
        out_png.parent.mkdir(parents=True, exist_ok=True)
        head.save(out_png, format="PNG")
        return IconBuildResult(True, out_png, str(skin_png), "player_head", "ok")
    except Exception as e:
        return IconBuildResult(False, None, str(skin_png), "player_head", f"error: {e}")


def build_icon_from_texture(texture_png: Path, out_png: Path, size: int = 64) -> IconBuildResult:
    """
    For MC textures (item or block):
    - If not square: center-crop
    - Resize to NxN nearest
    """
    if not texture_png.exists():
        return IconBuildResult(False, None, str(texture_png), "texture", "missing texture png")

    try:
        img = _ensure_rgba(Image.open(texture_png))
        w, h = img.size
        if w != h:
            side = min(w, h)
            left = (w - side) // 2
            top = (h - side) // 2
            img = img.crop((left, top, left + side, top + side))

        img = img.resize((size, size), resample=Image.NEAREST)
        out_png.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_png, format="PNG")
        return IconBuildResult(True, out_png, str(texture_png), "texture", "ok")
    except Exception as e:
        return IconBuildResult(False, None, str(texture_png), "texture", f"error: {e}")


# ============================================================
# NEU parsing (SkullOwner + ItemModel)
# ============================================================

# ItemModel:"minecraft:spruce_slab"
_ITEMMODEL_RE = re.compile(r'ItemModel\s*:\s*"minecraft:([a-z0-9_]+)"', re.IGNORECASE)

# NEU skulls: textures:[0:{...,Value:"<B64>"}]
# We'll find the first Value:"..." after SkullOwner.
_SKULL_VALUE_RE = re.compile(r'Value\s*:\s*"([^"]+)"', re.IGNORECASE)


def extract_skull_value_b64(nbttag: str) -> Optional[str]:
    if not nbttag or "SkullOwner" not in nbttag:
        return None
    idx = nbttag.find("SkullOwner")
    sub = nbttag[idx:] if idx >= 0 else nbttag
    m = _SKULL_VALUE_RE.search(sub)
    return m.group(1) if m else None


def decode_skin_url_from_value(value_b64: str) -> Optional[str]:
    """
    Value is base64(json) with: textures -> SKIN -> url
    """
    try:
        raw = base64.b64decode(value_b64.encode("utf-8"), validate=False)
        txt = raw.decode("utf-8", errors="replace")
        j = json.loads(txt)
        url = j.get("textures", {}).get("SKIN", {}).get("url")
        if isinstance(url, str) and url.startswith("http"):
            # normalize to https
            if url.startswith("http://textures.minecraft.net/"):
                url = "https://textures.minecraft.net/" + url.split("http://textures.minecraft.net/", 1)[1]
            return url
        return None
    except Exception:
        return None


def extract_itemmodel(nbttag: str) -> Optional[str]:
    if not nbttag:
        return None
    m = _ITEMMODEL_RE.search(nbttag)
    return m.group(1) if m else None


# ============================================================
# Dyes special handling (damage -> modern texture name)
# ============================================================

# Legacy dye meta mapping (commonly used in older formats)
# 0 black(ink_sac), 1 red, 2 green, 3 cocoa, 4 lapis, 5 purple, 6 cyan, 7 light_gray,
# 8 gray, 9 pink, 10 lime, 11 yellow, 12 light_blue, 13 magenta, 14 orange, 15 bone_meal
DYE_DAMAGE_TO_TEXTURE = {
    0: "black_dye",
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
    11: "yellow_dye",
    12: "light_blue_dye",
    13: "magenta_dye",
    14: "orange_dye",
    15: "bone_meal",
}

# Sometimes older id is "ink_sack"
INK_SACK_DAMAGE_TO_TEXTURE = DYE_DAMAGE_TO_TEXTURE.copy()


def dye_candidates(itemid_clean: str, damage: Optional[int]) -> List[str]:
    """
    If item is dye-like, return candidates in best order.
    """
    if itemid_clean in ("dye", "ink_sack"):
        if isinstance(damage, int):
            if itemid_clean == "dye":
                t = DYE_DAMAGE_TO_TEXTURE.get(damage)
            else:
                t = INK_SACK_DAMAGE_TO_TEXTURE.get(damage)
            if t:
                return [t, itemid_clean]
        return [itemid_clean]
    return []


# ============================================================
# MCASSET texture resolution
# ============================================================

def try_texture(name: str, item_dir: Path, block_dir: Path) -> Tuple[Optional[Path], Optional[str]]:
    """
    Return (path, source) where source is "item" or "block"
    """
    if not name:
        return None, None

    for ext in (".png", ".webp"):
        p = item_dir / f"{name}{ext}"
        if p.exists():
            return p, "item"
    for ext in (".png", ".webp"):
        p = block_dir / f"{name}{ext}"
        if p.exists():
            return p, "block"

    # common variants for blocks
    variants = [f"{name}_top", f"{name}_side", f"{name}_front", f"{name}_0"]
    for v in variants:
        for ext in (".png", ".webp"):
            p = item_dir / f"{v}{ext}"
            if p.exists():
                return p, "item"
        for ext in (".png", ".webp"):
            p = block_dir / f"{v}{ext}"
            if p.exists():
                return p, "block"

    return None, None


def resolve_texture_from_item(
    item: dict,
    mcasset_item_dir: Path,
    mcasset_block_dir: Path,
    progress: Progress,
) -> Tuple[Optional[Path], str, Dict[str, Any]]:
    """
    Order:
      - if vanilla True -> use itemid
      - else if ItemModel -> use itemmodel
      - else fallback itemid
    Includes special dyes handling based on damage.
    Returns (texture_path, method, extra_dict)
    """
    itemid_raw = item.get("itemid") or ""
    itemid_clean = clean_model_name(itemid_raw)  # e.g. acacia_fence
    nbttag = item.get("nbttag") or ""
    vanilla = bool(item.get("vanilla", False))
    damage = item.get("damage")
    if not isinstance(damage, int):
        damage = None

    extra: Dict[str, Any] = {
        "itemid": itemid_raw,
        "itemid_clean": itemid_clean,
        "damage": damage,
        "vanilla": vanilla,
    }

    # 1) Vanilla -> itemid (with dye special)
    if vanilla and itemid_clean:
        progress.inc_stat("vanilla_itemid", 1)

        # dye special
        for cand in dye_candidates(itemid_clean, damage) or [itemid_clean]:
            tex, src = try_texture(cand, mcasset_item_dir, mcasset_block_dir)
            if tex:
                extra.update({"resolved": cand, "source": src})
                return tex, "vanilla_itemid", extra

        return None, "vanilla_itemid_not_found", extra

    # 2) ItemModel
    if isinstance(nbttag, str) and nbttag:
        model = extract_itemmodel(nbttag)
        if model:
            progress.inc_stat("models", 1)
            tex, src = try_texture(model, mcasset_item_dir, mcasset_block_dir)
            if tex:
                extra.update({"itemmodel": model, "resolved": model, "source": src})
                return tex, "itemmodel", extra
            extra.update({"itemmodel": model})
            # continue to fallback itemid

    # 3) Fallback -> itemid (with dye special)
    if itemid_clean:
        progress.inc_stat("fallback_itemid", 1)

        for cand in dye_candidates(itemid_clean, damage) or [itemid_clean]:
            tex, src = try_texture(cand, mcasset_item_dir, mcasset_block_dir)
            if tex:
                extra.update({"resolved": cand, "source": src})
                return tex, "fallback_itemid", extra

    return None, "no_texture", extra


# ============================================================
# Skins download cache (skip intelligent)
# ============================================================

def load_skins_cache(path: Path) -> Dict[str, Any]:
    raw = load_json(path)
    if not isinstance(raw, dict):
        return {"_meta": {"created_unix": int(time.time())}, "textures": {}}
    if not isinstance(raw.get("textures"), dict):
        raw["textures"] = {}
    if "_meta" not in raw:
        raw["_meta"] = {"created_unix": int(time.time())}
    return raw


_thread_local = threading.local()


def get_session() -> requests.Session:
    s = getattr(_thread_local, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update({"User-Agent": UA})
        _thread_local.session = s
    return s


def mcskin_hash_from_url(url: str) -> str:
    u = (url or "").strip().replace("\\", "/")
    if "/texture/" in u:
        return u.split("/texture/", 1)[1].split("?", 1)[0]
    return safe_filename(u)


def download_mojang_texture(url: str, out_png: Path) -> Tuple[bool, str]:
    out_png.parent.mkdir(parents=True, exist_ok=True)

    if out_png.exists() and out_png.stat().st_size > 0:
        return True, "cached"

    tmp = out_png.with_suffix(".tmp")
    last_err = "unknown"

    sess = get_session()

    for attempt in range(1, 4):
        try:
            r = sess.get(url, timeout=25)
            status = r.status_code
            if status in (429, 500, 502, 503, 504):
                time.sleep(0.6 * attempt)
                last_err = f"http_{status}"
                continue
            if status != 200 or not r.content:
                return False, f"http_{status}"

            tmp.write_bytes(r.content)
            tmp.replace(out_png)
            return True, "downloaded"
        except Exception as e:
            last_err = str(e)
            time.sleep(0.5 * attempt)

    return False, f"download_error:{last_err}"


def get_or_download_skin_png(
    skin_url: str,
    skins_cache: Dict[str, Any],
    skins_cache_lock: threading.Lock,
    progress: Progress,
) -> Tuple[Optional[Path], str, str]:
    """
    Returns (skin_png_path_or_none, reason, hash)
      reason: cached | downloaded | skip_fail_cache | fail:...
    """
    url = skin_url.strip()
    h = mcskin_hash_from_url(url)
    out_png = SKINS_DIR / f"{h}.png"

    # disk fast path
    if out_png.exists() and out_png.stat().st_size > 0:
        progress.inc_stat("cached", 1)
        with skins_cache_lock:
            skins_cache["textures"][h] = {
                "url": url,
                "path": str(out_png),
                "status": "ok",
                "reason": "disk_cached",
                "ts": int(time.time()),
            }
        return out_png, "cached", h

    # intelligent fail cache (12h cooldown)
    with skins_cache_lock:
        entry = skins_cache["textures"].get(h)

    if isinstance(entry, dict) and entry.get("status") == "fail":
        ts = int(entry.get("ts") or 0)
        if (time.time() - ts) < 12 * 3600:
            progress.inc_stat("skip_fail_cache", 1)
            return None, "skip_fail_cache", h

    ok, dl_reason = download_mojang_texture(url, out_png)
    if ok:
        if dl_reason == "downloaded":
            progress.inc_stat("downloaded", 1)
        else:
            progress.inc_stat("cached", 1)

        with skins_cache_lock:
            skins_cache["textures"][h] = {
                "url": url,
                "path": str(out_png),
                "status": "ok",
                "reason": dl_reason,
                "ts": int(time.time()),
            }
        return out_png, dl_reason, h

    with skins_cache_lock:
        skins_cache["textures"][h] = {
            "url": url,
            "path": str(out_png),
            "status": "fail",
            "reason": dl_reason,
            "ts": int(time.time()),
        }
    return None, "fail:" + dl_reason, h


# ============================================================
# Worker: process one NEU item json
# ============================================================

def process_one_neu_file(
    jf: Path,
    out_dir: Path,
    size: int,
    force: bool,
    mcasset_item_dir: Path,
    mcasset_block_dir: Path,
    no_skin_download: bool,
    skins_cache: Dict[str, Any],
    skins_cache_lock: threading.Lock,
    progress: Progress,
) -> Tuple[str, Dict[str, Any], Optional[Dict[str, Any]]]:
    raw = load_json(jf)
    if not isinstance(raw, dict):
        progress.inc_stat("failed", 1)
        entry = {"ok": False, "reason": "invalid json", "file": str(jf)}
        return jf.stem, entry, entry

    internal = raw.get("internalname") or jf.stem
    if not isinstance(internal, str) or not internal.strip():
        internal = jf.stem
    internal = internal.strip()

    displayname = raw.get("displayname") if isinstance(raw.get("displayname"), str) else ""
    display_clean = strip_mc_codes(displayname).strip()

    nbttag = raw.get("nbttag") if isinstance(raw.get("nbttag"), str) else ""
    itemid = raw.get("itemid") if isinstance(raw.get("itemid"), str) else ""

    out_png = out_dir / f"{safe_filename(internal)}.png"
    if out_png.exists() and not force:
        progress.inc_stat("skipped", 1)
        return internal, {
            "ok": True,
            "reason": "exists",
            "internalname": internal,
            "displayname": displayname,
            "displayname_clean": display_clean,
            "out": str(out_png),
            "method": "skip",
        }, None

    # ---- Skull path
    value_b64 = extract_skull_value_b64(nbttag)
    if value_b64:
        progress.inc_stat("skulls", 1)

        skin_url = decode_skin_url_from_value(value_b64)
        if not skin_url:
            progress.inc_stat("failed", 1)
            entry = {
                "ok": False,
                "reason": "skull but cannot decode skin_url",
                "internalname": internal,
                "itemid": itemid,
                "file": str(jf),
            }
            return internal, entry, entry

        if no_skin_download:
            progress.inc_stat("failed", 1)
            entry = {
                "ok": False,
                "reason": "skin download disabled",
                "internalname": internal,
                "skin_url": skin_url,
                "file": str(jf),
            }
            return internal, entry, entry

        skin_png, dl_reason, h = get_or_download_skin_png(
            skin_url=skin_url,
            skins_cache=skins_cache,
            skins_cache_lock=skins_cache_lock,
            progress=progress,
        )
        if not skin_png:
            progress.inc_stat("failed", 1)
            entry = {
                "ok": False,
                "reason": "failed to get skin png",
                "internalname": internal,
                "skin_url": skin_url,
                "download": dl_reason,
                "skin_hash": h,
                "file": str(jf),
            }
            return internal, entry, entry

        res = build_player_head_icon(skin_png, out_png, size=size)
        if res.ok:
            progress.inc_stat("built", 1)
            return internal, {
                "ok": True,
                "internalname": internal,
                "displayname": displayname,
                "displayname_clean": display_clean,
                "out": str(res.out_path) if res.out_path else None,
                "method": f"skull+{dl_reason}",
                "skin_url": skin_url,
                "skin_hash": h,
                "source": res.source_texture,
            }, None

        progress.inc_stat("failed", 1)
        entry = {
            "ok": False,
            "reason": res.reason,
            "internalname": internal,
            "file": str(jf),
            "source": res.source_texture,
        }
        return internal, entry, entry

    # ---- Normal path (vanilla/itemmodel/fallback itemid + dyes)
    tex, method, extra = resolve_texture_from_item(raw, mcasset_item_dir, mcasset_block_dir, progress)
    if not tex:
        progress.inc_stat("failed", 1)
        entry = {
            "ok": False,
            "reason": method,
            "internalname": internal,
            "displayname": displayname,
            "displayname_clean": display_clean,
            "file": str(jf),
            **extra,
        }
        return internal, entry, entry

    res = build_icon_from_texture(tex, out_png, size=size)
    if res.ok:
        progress.inc_stat("built", 1)
        return internal, {
            "ok": True,
            "internalname": internal,
            "displayname": displayname,
            "displayname_clean": display_clean,
            "out": str(res.out_path) if res.out_path else None,
            "method": method,
            "source": res.source_texture,
            **extra,
        }, None

    progress.inc_stat("failed", 1)
    entry = {
        "ok": False,
        "reason": res.reason,
        "internalname": internal,
        "file": str(jf),
        "source": res.source_texture,
        "method": method,
        **extra,
    }
    return internal, entry, entry


# ============================================================
# Main
# ============================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build items icons from NEU repo items. Skulls download from textures.minecraft.net (multi-thread), others from MCASSET item/block. Includes manifest + fails + dyes handling."
    )
    parser.add_argument("--neu-items", default=str(CACHE_DIR / "NEU" / "repo" / "items"))
    parser.add_argument("--mcasset-item", default=str(CACHE_DIR / "MCASSET" / "item"))
    parser.add_argument("--mcasset-block", default=str(CACHE_DIR / "MCASSET" / "block"))
    parser.add_argument("--out", default=str(CACHE_DIR / "icone" / "items"))
    parser.add_argument("--size", type=int, default=64)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-skin-download", action="store_true")
    parser.add_argument("--workers", type=int, default=8, help="Total workers (icons + downloads). Default 8.")
    parser.add_argument("--save-cache-every", type=int, default=120, help="Save _skins_cache.json every N completed items.")
    args = parser.parse_args()

    neu_items_dir = Path(args.neu_items)
    mcasset_item_dir = Path(args.mcasset_item)
    mcasset_block_dir = Path(args.mcasset_block)
    out_dir = Path(args.out)

    out_dir.mkdir(parents=True, exist_ok=True)
    SKINS_DIR.mkdir(parents=True, exist_ok=True)

    json_files = sorted(neu_items_dir.glob("*.json"))
    if not json_files:
        print(f"[ERR] Aucun json trouvé dans: {neu_items_dir}")
        return 2

    skins_cache = load_skins_cache(SKINS_CACHE_JSON)
    skins_cache_lock = threading.Lock()

    total = len(json_files)
    progress = Progress(total)

    report: Dict[str, Any] = {
        "_meta": {
            "neu_items_dir": str(neu_items_dir),
            "mcasset_item_dir": str(mcasset_item_dir),
            "mcasset_block_dir": str(mcasset_block_dir),
            "skins_dir": str(SKINS_DIR),
            "skins_cache_json": str(SKINS_CACHE_JSON),
            "out_dir": str(out_dir),
            "size": args.size,
            "workers": args.workers,
            "skin_download": (not args.no_skin_download),
            "generated_unix": int(time.time()),
        },
        "stats": {"seen": total, "built": 0, "skipped": 0, "failed": 0},
        "icons": {},
    }
    fails: Dict[str, Any] = {"_meta": report["_meta"], "failed": {}}

    save_every = max(1, int(args.save_cache_every))
    completed = 0

    with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as ex:
        futures = []
        for jf in json_files:
            futures.append(ex.submit(
                process_one_neu_file,
                jf,
                out_dir,
                args.size,
                args.force,
                mcasset_item_dir,
                mcasset_block_dir,
                args.no_skin_download,
                skins_cache,
                skins_cache_lock,
                progress,
            ))

        for fut in as_completed(futures):
            internal, entry, fail_entry = fut.result()
            report["icons"][internal] = entry
            if fail_entry is not None:
                fails["failed"][internal] = fail_entry

            completed += 1
            progress.inc_done(1)
            progress.set_label(internal)
            progress.render()

            if completed % save_every == 0:
                with skins_cache_lock:
                    save_json_atomic(SKINS_CACHE_JSON, skins_cache)

    with skins_cache_lock:
        save_json_atomic(SKINS_CACHE_JSON, skins_cache)

    # final stats
    done, _, stats, _, _ = progress.snapshot()
    report["stats"]["built"] = stats.get("built", 0)
    report["stats"]["skipped"] = stats.get("skipped", 0)
    report["stats"]["failed"] = stats.get("failed", 0)
    report["stats"]["seen"] = done

    manifest_out = out_dir / "_build_manifest.json"
    fails_out = out_dir / "_fails.json"
    save_json(manifest_out, report)
    save_json(fails_out, fails)

    progress.render(final=True)
    print(
        f"[OK] icons: seen={report['stats']['seen']} built={report['stats']['built']} "
        f"skipped={report['stats']['skipped']} failed={report['stats']['failed']}"
    )
    print(f" -> manifest: {manifest_out}")
    print(f" -> fails:    {fails_out}")
    print(f" -> skins cache: {SKINS_CACHE_JSON}")
    print(f" -> out dir:  {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
