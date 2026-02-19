from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


# ----------------------------
# IO
# ----------------------------
def load_json(path: Path, default: Any = None) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def now_unix() -> int:
    return int(time.time())


def project_root_from_here(file_path: str | Path) -> Path:
    # core/normalize/... -> parents[2] == project root
    return Path(file_path).resolve().parents[2]


def safe_slug(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return "unknown"
    s = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", s)  # Windows forbidden
    s = re.sub(r"\s+", "_", s)
    s = s.strip("._ ")
    return s or "unknown"


# ----------------------------
# Config: sections to extract
# ----------------------------
SECTIONS = [
    "rift",
    "player_data",
    "events",
    "garden_player_data",
    "accessory_bag_storage",
    "leveling",
    "jacobs_contest",
    "currencies",
    "dungeons",
    "profile",
    "pets_data",
    "nether_island_player_data",
    "experimentation",
    "mining_core",
    "bestiary",
    "quests",
    "player_stats",
    "forge",
    "fairy_soul",
    "slayer",
    "trophy_fish",
    "objectives",
    "inventory",
    "shared_inventory",
    "collection",
]

# aliases for common user typos / variants
ALIASES = {
    "jacobs_contest": ["jacobs_contest", "jacob_contest", "jacobsContest", "jacobs"],
    "player_data": ["player_data", "playerData"],
    "garden_player_data": ["garden_player_data", "gardenPlayerData"],
    "pets_data": ["pets_data", "petsData"],
    "nether_island_player_data": ["nether_island_player_data", "netherIslandPlayerData"],
    "accessory_bag_storage": ["accessory_bag_storage", "accessoryBagStorage"],
    "shared_inventory": ["shared_inventory", "sharedInventory"],
    "trophy_fish": ["trophy_fish", "trophyFish"],
    "fairy_soul": ["fairy_soul", "fairySoul"],
    "player_stats": ["player_stats", "playerStats"],
    "mining_core": ["mining_core", "miningCore"],
}


def pick_section(member: dict, section_name: str) -> Optional[Any]:
    """
    Returns the value of a section in member using aliases if needed.
    """
    keys = ALIASES.get(section_name, [section_name])
    for k in keys:
        if k in member:
            return member.get(k)
    return None


def get_member_obj(member_file_payload: dict) -> dict:
    """
    Accepts:
      - {"member": {...}} (our previous format)
      - raw member dict (if someone saved it directly)
    """
    if not isinstance(member_file_payload, dict):
        return {}
    m = member_file_payload.get("member")
    if isinstance(m, dict):
        return m
    # fallback: maybe it's already the member dict
    if "player_data" in member_file_payload or "dungeons" in member_file_payload or "slayer" in member_file_payload:
        return member_file_payload
    return {}


def normalize_one_member_file(member_path: Path, out_root: Path) -> Dict[str, Any]:
    raw = load_json(member_path, default=None)
    if raw is None:
        return {"ok": False, "error": "cannot_read_json", "path": str(member_path)}

    member = get_member_obj(raw)
    if not member:
        return {"ok": False, "error": "missing_member_object", "path": str(member_path)}

    # try read name + uuid from _meta if present
    meta = raw.get("_meta") if isinstance(raw, dict) else None
    if not isinstance(meta, dict):
        meta = {}

    name = (meta.get("member_name") or member.get("name") or member.get("display_name") or "").strip()
    uuid = (meta.get("member_uuid") or "").strip()

    pseudo = safe_slug(member_path.stem)  # filename without .json -> already pseudo
    player_dir = out_root / pseudo
    player_dir.mkdir(parents=True, exist_ok=True)

    written: List[str] = []
    missing: List[str] = []

    for sec in SECTIONS:
        val = pick_section(member, sec)
        if val is None:
            missing.append(sec)
            continue

        out_path = player_dir / f"{sec}.json"
        save_json(out_path, {
            "_meta": {
                "generated_at_unix": now_unix(),
                "source_member_file": str(member_path),
                "player": {
                    "pseudo": pseudo,
                    "name_meta": name,
                    "uuid_meta": uuid,
                },
                "section": sec,
            },
            sec: val,
        })
        written.append(str(out_path))

    # also write an index.json for this player
    index_path = player_dir / "index.json"
    save_json(index_path, {
        "_meta": {
            "generated_at_unix": now_unix(),
            "source_member_file": str(member_path),
            "player": {
                "pseudo": pseudo,
                "name_meta": name,
                "uuid_meta": uuid,
            },
        },
        "written_sections": [Path(p).name for p in written],
        "missing_sections": missing,
        "output_dir": str(player_dir),
    })

    return {
        "ok": True,
        "player": pseudo,
        "index": str(index_path),
        "written": len(written),
        "missing": len(missing),
    }


def main():
    root = project_root_from_here(__file__)
    cache = root / "cache"

    members_dir = cache / "UI" / "profile" / "members"
    if not members_dir.exists():
        raise SystemExit(f"Missing folder: {members_dir}")

    # note: you said jejar.json, but earlier it was jejar_.json
    # we will process ALL .json in members/ to avoid mismatch issues.
    member_files = sorted(members_dir.glob("*.json"))
    if not member_files:
        raise SystemExit(f"No member json found in {members_dir}")

    out_root = cache / "UI" / "profile" / "sections"
    out_root.mkdir(parents=True, exist_ok=True)

    results = []
    for f in member_files:
        results.append(normalize_one_member_file(f, out_root))

    # global index
    global_index = out_root / "index.json"
    save_json(global_index, {
        "_meta": {
            "generated_at_unix": now_unix(),
            "source_members_dir": str(members_dir),
        },
        "results": results,
        "sections": SECTIONS,
        "output_root": str(out_root),
    })

    ok_count = sum(1 for r in results if r.get("ok"))
    print(f"[OK] processed {len(results)} files | ok={ok_count}")
    print(f"[OK] global index -> {global_index}")


if __name__ == "__main__":
    main()
