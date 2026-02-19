# D:\DEV\Hypixel\App\Sky_Track\V3\Sky_Track\tools\build_icons_mobs.py
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from PIL import Image


# ----------------------------
# Helpers / project paths
# ----------------------------

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


def load_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def camel_to_snake(name: str) -> str:
    # "ZombieVillager" -> "zombie_villager"
    s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
    s2 = re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1)
    return s2.replace("__", "_").lower()


# ----------------------------
# Entity name normalization (NEU -> vanilla-ish)
# ----------------------------

ENTITY_ALIASES = {
    # NEU / custom / typos -> vanilla-ish entity name (used for texture lookup)
    "eisengolem": "IronGolem",
    "sinelverfish": "Silverfish",
    "pigman": "ZombifiedPiglin",  # maps to piglin/zombified_piglin.png in your MCASSET
}


def normalize_entity_name(entity_name: str) -> str:
    key = (entity_name or "").strip().lower()
    return ENTITY_ALIASES.get(key, entity_name)


# ----------------------------
# Icon building
# ----------------------------

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
    Minecraft player skin head icon:
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

        # Hat/overlay only if present
        if w >= 48 and h >= 16:
            hat = img.crop((40, 8, 48, 16))
            head.alpha_composite(hat)

        head = head.resize((size, size), resample=Image.NEAREST)

        out_png.parent.mkdir(parents=True, exist_ok=True)
        head.save(out_png, format="PNG")
        return IconBuildResult(True, out_png, str(skin_png), "player_head", "ok")
    except Exception as e:
        return IconBuildResult(False, None, str(skin_png), "player_head", f"error: {e}")


def build_entity_head_icon(texture_png: Path, out_png: Path, size: int = 64) -> IconBuildResult:
    """
    Heuristic head extraction for entity textures.

    - If texture seems biped-ish (>=64x32): try player-like head region
    - Else fallback to centered square crop
    """
    if not texture_png.exists():
        return IconBuildResult(False, None, str(texture_png), "entity_head", "missing texture png")

    try:
        img = _ensure_rgba(Image.open(texture_png))
        w, h = img.size

        method = "entity_head_biped"
        if w >= 64 and h >= 32:
            face = img.crop((8, 8, 16, 16))
            head = face.copy()
            if w >= 48 and h >= 16:
                hat = img.crop((40, 8, 48, 16))
                head.alpha_composite(hat)
        else:
            method = "entity_head_center_crop"
            side = min(w, h)
            left = (w - side) // 2
            top = (h - side) // 2
            head = img.crop((left, top, left + side, top + side))

        head = head.resize((size, size), resample=Image.NEAREST)

        out_png.parent.mkdir(parents=True, exist_ok=True)
        head.save(out_png, format="PNG")
        return IconBuildResult(True, out_png, str(texture_png), method, "ok")
    except Exception as e:
        return IconBuildResult(False, None, str(texture_png), "entity_head", f"error: {e}")


def build_icon_from_existing_png(src_png: Path, out_png: Path, size: int = 64) -> IconBuildResult:
    """
    Load an existing png (item icon or barrier), ensure RGBA, resize to NxN, save as mob icon.
    """
    if not src_png.exists():
        return IconBuildResult(False, None, str(src_png), "existing_png", "missing source png")
    try:
        img = _ensure_rgba(Image.open(src_png))
        img = img.resize((size, size), resample=Image.NEAREST)
        out_png.parent.mkdir(parents=True, exist_ok=True)
        img.save(out_png, format="PNG")
        return IconBuildResult(True, out_png, str(src_png), "existing_png", "ok")
    except Exception as e:
        return IconBuildResult(False, None, str(src_png), "existing_png", f"error: {e}")


# ----------------------------
# Texture resolution (MCASSET)
# ----------------------------

def load_entity_manifest(manifest_path: Path) -> Optional[Dict[str, dict]]:
    """
    Expected structure:
      { "_meta": {...}, "items": { "zombie/zombie.png": {"local_path": "...", ...}, ... } }
    """
    raw = load_json(manifest_path)
    if not isinstance(raw, dict):
        return None
    items = raw.get("items")
    if not isinstance(items, dict):
        return None
    return items


def resolve_mcasset_texture(
    entity_name: str,
    mcasset_mobs_dir: Path,
    manifest_items: Optional[Dict[str, dict]] = None,
) -> Optional[Path]:
    ent_snake = camel_to_snake(entity_name)
    ent_lower = entity_name.lower()

    # Manifest-first (best)
    if manifest_items:
        keys = list(manifest_items.keys())

        candidates = [
            f"{ent_snake}/{ent_snake}.png",
            f"{ent_lower}/{ent_lower}.png",
            f"{ent_snake}.png",
            f"{ent_lower}.png",
        ]
        for c in candidates:
            if c in manifest_items:
                lp = manifest_items[c].get("local_path")
                if lp:
                    p = Path(lp)
                    if p.exists():
                        return p

        # Heuristic best match
        want = f"/{ent_snake}.png"
        hits = [k for k in keys if k.replace("\\", "/").endswith(want)]
        if not hits:
            want2 = f"/{ent_lower}.png"
            hits = [k for k in keys if k.replace("\\", "/").endswith(want2)]
        if not hits:
            token = ent_snake
            hits = [k for k in keys if token in k.lower() and k.lower().endswith(".png")]

        if hits:
            hits.sort(key=lambda s: (len(s), s))
            best = hits[0]
            lp = manifest_items[best].get("local_path")
            if lp:
                p = Path(lp)
                if p.exists():
                    return p

    # Disk guesses if no manifest / no hit
    direct_candidates = [
        mcasset_mobs_dir / ent_snake / f"{ent_snake}.png",
        mcasset_mobs_dir / ent_lower / f"{ent_lower}.png",
        mcasset_mobs_dir / f"{ent_snake}.png",
        mcasset_mobs_dir / f"{ent_lower}.png",
    ]
    for p in direct_candidates:
        if p.exists():
            return p

    return None


# ----------------------------
# NEU mob json parsing
# ----------------------------

def extract_player_skin_ref(mob_json: dict) -> Optional[str]:
    mods = mob_json.get("modifiers")
    if not isinstance(mods, list):
        return None
    for m in mods:
        if not isinstance(m, dict):
            continue
        if (m.get("type") or "").lower() == "playerdata":
            skin = m.get("skin")
            if isinstance(skin, str) and skin:
                return skin
    return None


def resolve_neurepo_skin(skin_ref: str, neu_mobs_dir: Path) -> Optional[Path]:
    """
    skin_ref example: "neurepo:mobs/angry_archeologist.png"
    Accept also "mobs/xxx.png" or "xxx.png"
    """
    s = skin_ref.strip()
    if ":" in s:
        _, tail = s.split(":", 1)
    else:
        tail = s

    tail = tail.lstrip("/").replace("\\", "/")
    if tail.startswith("mobs/"):
        tail = tail[len("mobs/"):]
    p = neu_mobs_dir / tail
    return p if p.exists() else None


def extract_armorstand_helmet(mob_json: dict) -> Optional[str]:
    """
    NEU mobs ArmorStand often encode their visual as an equipment helmet item id.
    Example:
      modifiers: [{type:"equipment", helmet:"BUTTERFLY_MONSTER"}]
    """
    mods = mob_json.get("modifiers")
    if not isinstance(mods, list):
        return None
    for m in mods:
        if not isinstance(m, dict):
            continue
        if (m.get("type") or "").lower() == "equipment":
            helmet = m.get("helmet")
            if isinstance(helmet, str) and helmet.strip():
                return helmet.strip()
    return None


# ----------------------------
# Main
# ----------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Build mob icons (heads) from NEU mobs + MCASSET mobs textures.")
    parser.add_argument(
        "--neu-mobs",
        default=str(CACHE_DIR / "NEU" / "repo" / "mobs"),
        help="Path to NEU repo mobs folder (contains *.json and player skins png).",
    )
    parser.add_argument(
        "--mcasset-mobs",
        default=str(CACHE_DIR / "MCASSET" / "mobs"),
        help="Path to MCASSET mobs textures folder (copied entity textures).",
    )
    parser.add_argument(
        "--mcasset-entity-manifest",
        default=str(CACHE_DIR / "MCASSET" / "mcasset_entity_manifest.json"),
        help="Optional manifest mapping relative keys -> local_path for MCASSET mobs.",
    )
    parser.add_argument(
        "--item-icons",
        default=str(CACHE_DIR / "icone" / "items"),
        help="Path to item icons folder (used for ArmorStand helmet icons).",
    )
    parser.add_argument(
        "--armorstand-fallback",
        default=str(CACHE_DIR / "MCASSET" / "item" / "barrier.png"),
        help="Fallback png used when ArmorStand helmet icon is missing.",
    )
    parser.add_argument(
        "--out",
        default=str(CACHE_DIR / "icone" / "mobs"),
        help="Output folder for generated icons.",
    )
    parser.add_argument("--size", type=int, default=64, help="Icon size (NxN). Default 64.")
    parser.add_argument("--force", action="store_true", help="Rebuild icons even if already exist.")
    args = parser.parse_args()

    neu_mobs_dir = Path(args.neu_mobs)
    mcasset_mobs_dir = Path(args.mcasset_mobs)
    item_icons_dir = Path(args.item_icons)
    armorstand_fallback_png = Path(args.armorstand_fallback)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = Path(args.mcasset_entity_manifest)
    manifest_items = load_entity_manifest(manifest_path) if manifest_path.exists() else None

    json_files = sorted(neu_mobs_dir.glob("*.json"))
    if not json_files:
        print(f"[ERR] Aucun mob json trouvé dans: {neu_mobs_dir}")
        return 2

    report: Dict[str, dict] = {
        "_meta": {
            "neu_mobs_dir": str(neu_mobs_dir),
            "mcasset_mobs_dir": str(mcasset_mobs_dir),
            "item_icons_dir": str(item_icons_dir),
            "armorstand_fallback": str(armorstand_fallback_png),
            "out_dir": str(out_dir),
            "manifest_used": bool(manifest_items),
            "size": args.size,
        },
        "stats": {"seen": 0, "built": 0, "skipped": 0, "failed": 0},
        "icons": {},
    }

    fails: Dict[str, dict] = {
        "_meta": report["_meta"],
        "failed": {},
    }

    for jf in json_files:
        mob_id = jf.stem
        report["stats"]["seen"] += 1

        raw = load_json(jf)
        if not isinstance(raw, dict):
            report["stats"]["failed"] += 1
            entry = {"ok": False, "reason": "invalid json", "json": str(jf)}
            report["icons"][mob_id] = entry
            fails["failed"][mob_id] = entry
            continue

        entity = raw.get("entity")
        if not isinstance(entity, str) or not entity:
            report["stats"]["failed"] += 1
            entry = {"ok": False, "reason": "missing entity", "json": str(jf)}
            report["icons"][mob_id] = entry
            fails["failed"][mob_id] = entry
            continue

        out_png = out_dir / f"{mob_id}.png"
        if out_png.exists() and not args.force:
            report["stats"]["skipped"] += 1
            report["icons"][mob_id] = {
                "ok": True,
                "reason": "exists",
                "entity": entity,
                "out": str(out_png),
                "method": "skip",
            }
            continue

        # Build icon depending on entity
        if entity.lower() == "player":
            skin_ref = extract_player_skin_ref(raw)
            if not skin_ref:
                report["stats"]["failed"] += 1
                entry = {
                    "ok": False,
                    "reason": "player entity but no playerdata.skin",
                    "entity": entity,
                    "json": str(jf),
                }
                report["icons"][mob_id] = entry
                fails["failed"][mob_id] = entry
                continue

            skin_png = resolve_neurepo_skin(skin_ref, neu_mobs_dir)
            if not skin_png:
                report["stats"]["failed"] += 1
                entry = {
                    "ok": False,
                    "reason": "skin ref not found in NEU mobs",
                    "entity": entity,
                    "skin_ref": skin_ref,
                    "json": str(jf),
                }
                report["icons"][mob_id] = entry
                fails["failed"][mob_id] = entry
                continue

            res = build_player_head_icon(skin_png, out_png, size=args.size)

            if res.ok:
                report["stats"]["built"] += 1
                report["icons"][mob_id] = {
                    "ok": True,
                    "entity": entity,
                    "out": str(res.out_path) if res.out_path else None,
                    "source": res.source_texture,
                    "method": res.method,
                    "reason": res.reason,
                }
            else:
                report["stats"]["failed"] += 1
                entry = {
                    "ok": False,
                    "entity": entity,
                    "out": str(out_png),
                    "source": res.source_texture,
                    "method": res.method,
                    "reason": res.reason,
                }
                report["icons"][mob_id] = entry
                fails["failed"][mob_id] = entry

        elif entity.lower() == "armorstand":
            helmet = extract_armorstand_helmet(raw)
            if not helmet:
                report["stats"]["failed"] += 1
                entry = {
                    "ok": False,
                    "reason": "armorstand but no equipment.helmet",
                    "entity": entity,
                    "json": str(jf),
                }
                report["icons"][mob_id] = entry
                fails["failed"][mob_id] = entry
                continue

            helmet_png = item_icons_dir / f"{helmet}.png"
            helmet_source = "items_icon" if helmet_png.exists() else "barrier_fallback"
            src_png = helmet_png if helmet_png.exists() else armorstand_fallback_png

            if not src_png.exists():
                report["stats"]["failed"] += 1
                entry = {
                    "ok": False,
                    "reason": "helmet icon missing and barrier fallback missing",
                    "entity": entity,
                    "helmet": helmet,
                    "helmet_source": helmet_source,
                    "tried_item_icon": str(helmet_png),
                    "fallback": str(armorstand_fallback_png),
                    "json": str(jf),
                }
                report["icons"][mob_id] = entry
                fails["failed"][mob_id] = entry
                continue

            res = build_icon_from_existing_png(src_png, out_png, size=args.size)

            if res.ok:
                report["stats"]["built"] += 1
                report["icons"][mob_id] = {
                    "ok": True,
                    "entity": entity,
                    "helmet": helmet,                 # micro-amélioration
                    "helmet_source": helmet_source,   # items_icon | barrier_fallback
                    "out": str(res.out_path) if res.out_path else None,
                    "source": res.source_texture,
                    "method": res.method,
                    "reason": res.reason,
                }
            else:
                report["stats"]["failed"] += 1
                entry = {
                    "ok": False,
                    "entity": entity,
                    "helmet": helmet,                 # micro-amélioration
                    "helmet_source": helmet_source,   # items_icon | barrier_fallback
                    "out": str(out_png),
                    "source": res.source_texture,
                    "method": res.method,
                    "reason": res.reason,
                }
                report["icons"][mob_id] = entry
                fails["failed"][mob_id] = entry

        else:
            entity_norm = normalize_entity_name(entity)
            tex = resolve_mcasset_texture(entity_norm, mcasset_mobs_dir, manifest_items=manifest_items)
            if not tex:
                report["stats"]["failed"] += 1
                entry = {
                    "ok": False,
                    "reason": "no mcasset texture match",
                    "entity": entity,
                    "entity_resolved": entity_norm,  # helpful debug
                    "json": str(jf),
                }
                report["icons"][mob_id] = entry
                fails["failed"][mob_id] = entry
                continue

            res = build_entity_head_icon(tex, out_png, size=args.size)

            if res.ok:
                report["stats"]["built"] += 1
                report["icons"][mob_id] = {
                    "ok": True,
                    "entity": entity,
                    "entity_resolved": entity_norm,  # helpful debug
                    "out": str(res.out_path) if res.out_path else None,
                    "source": res.source_texture,
                    "method": res.method,
                    "reason": res.reason,
                }
            else:
                report["stats"]["failed"] += 1
                entry = {
                    "ok": False,
                    "entity": entity,
                    "entity_resolved": entity_norm,  # helpful debug
                    "out": str(out_png),
                    "source": res.source_texture,
                    "method": res.method,
                    "reason": res.reason,
                }
                report["icons"][mob_id] = entry
                fails["failed"][mob_id] = entry

    # Write manifests
    manifest_out = out_dir / "_build_manifest.json"
    fails_out = out_dir / "_fails.json"
    save_json(manifest_out, report)
    save_json(fails_out, fails)

    print(
        f"[OK] mobs icons: seen={report['stats']['seen']} built={report['stats']['built']} "
        f"skipped={report['stats']['skipped']} failed={report['stats']['failed']}"
    )
    print(f" -> manifest: {manifest_out}")
    print(f" -> fails:    {fails_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
