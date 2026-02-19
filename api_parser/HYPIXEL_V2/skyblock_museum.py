# api_parser/HYPIXEL_V2/skyblock_museum.py
from __future__ import annotations

from .client import (
    HypixelV2Client,
    project_root_from_here,
    load_api_key,
    load_profile_id,
)

def main(ttl_s: int = 900):
    root = project_root_from_here(__file__)
    cache = root / "cache"
    out = cache / "HYPIXEL_V2" / "skyblock_museum.json"

    profile_id = load_profile_id(cache)
    if not profile_id:
        raise SystemExit("Missing cache/profile_id.json (expected profile_id).")

    client = HypixelV2Client(load_api_key(cache), cache / "HYPIXEL_V2")
    client.get_json(
        "/skyblock/museum",
        out_file=out,
        params={"profile": profile_id},
        ttl_s=ttl_s,
    )
    print(f"[OK] {out}")

if __name__ == "__main__":
    main()
