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
    # core/normalize/normalize_profile.py -> parents[2] = project root
    return Path(file_path).resolve().parents[2]


# ----------------------------
# Helpers
# ----------------------------
def safe_slug(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return "unknown"
    # keep readable pseudo, remove forbidden chars for Windows filenames
    s = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", s)  # Windows forbidden
    s = re.sub(r"\s+", "_", s)
    s = s.strip("._ ")
    return s or "unknown"


def norm_uuid(u: str) -> str:
    u = (u or "").strip().lower().replace("-", "")
    u = re.sub(r"[^0-9a-f]", "", u)
    return u


def get_profile_obj(skyblock_profile_payload: dict) -> dict:
    """
    Supports:
      - wrapper format: {"_meta":..., "data": {"profile": {...}}}
      - raw format: {"profile": {...}}
      - already profile-like: {"members": {...}, "banking": {...}}
    """
    if not isinstance(skyblock_profile_payload, dict):
        return {}

    data = skyblock_profile_payload.get("data")
    if isinstance(data, dict):
        prof = data.get("profile")
        if isinstance(prof, dict):
            return prof
        if "members" in data and isinstance(data.get("members"), dict):
            return data

    prof = skyblock_profile_payload.get("profile")
    if isinstance(prof, dict):
        return prof

    if "members" in skyblock_profile_payload and isinstance(skyblock_profile_payload.get("members"), dict):
        return skyblock_profile_payload

    return {}


def load_players(cache_dir: Path) -> List[Dict[str, str]]:
    """
    Expected format (your case):
    [
      {"name":"jejar_","uuid":"..."},
      ...
    ]
    """
    raw = load_json(cache_dir / "players.json", default=None)
    if not isinstance(raw, list):
        raise SystemExit("cache/players.json must be a list of {name, uuid}")

    players: List[Dict[str, str]] = []
    for it in raw:
        if not isinstance(it, dict):
            continue
        name = (it.get("name") or "").strip()
        uuid = norm_uuid(it.get("uuid") or it.get("id") or "")
        if uuid:
            players.append({"name": name, "uuid": uuid})

    if not players:
        raise SystemExit("No valid players found in cache/players.json")

    return players


# ----------------------------
# Main
# ----------------------------
def main():
    root = project_root_from_here(__file__)
    cache = root / "cache"

    src_path = cache / "HYPIXEL_V2" / "skyblock_profile.json"
    payload = load_json(src_path, default={}) or {}
    profile = get_profile_obj(payload)

    if not profile:
        raise SystemExit(f"Invalid or missing profile object in {src_path}")

    members = profile.get("members")
    if not isinstance(members, dict):
        raise SystemExit("Missing 'members' dict in profile")

    # Create cache/UI/profile/
    out_root = cache / "UI" / "profile"
    out_members = out_root / "members"
    out_members.mkdir(parents=True, exist_ok=True)

    # Banking
    banking = profile.get("banking") if isinstance(profile.get("banking"), dict) else {}
    banking_path = out_root / "banking.json"
    save_json(banking_path, {
        "_meta": {
            "generated_at_unix": now_unix(),
            "source": str(src_path),
        },
        "banking": banking,
    })

    # Members split by players.json (named by pseudo)
    players = load_players(cache)

    written: List[dict] = []
    missing: List[dict] = []

    for p in players:
        name = p["name"] or p["uuid"]
        uuid = p["uuid"]

        member_obj = members.get(uuid)
        if not isinstance(member_obj, dict):
            missing.append({"name": name, "uuid": uuid})
            continue

        filename = safe_slug(name) + ".json"
        out_path = out_members / filename

        save_json(out_path, {
            "_meta": {
                "generated_at_unix": now_unix(),
                "source": str(src_path),
                "member_uuid": uuid,
                "member_name": name,
            },
            "member": member_obj,
        })

        written.append({
            "name": name,
            "uuid": uuid,
            "path": str(out_path),
        })

    # Index
    index_path = out_root / "index.json"
    save_json(index_path, {
        "_meta": {
            "generated_at_unix": now_unix(),
            "source": str(src_path),
        },
        "banking_path": str(banking_path),
        "members_written": written,
        "members_missing": missing,
    })

    print(f"[OK] created: {out_root}")
    print(f"[OK] banking -> {banking_path}")
    print(f"[OK] members written: {len(written)} | missing: {len(missing)}")
    print(f"[OK] index -> {index_path}")


if __name__ == "__main__":
    main()
