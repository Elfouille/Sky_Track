# api_parser/HYPIXEL_V2/skyblock_news.py
from __future__ import annotations
from pathlib import Path

from .client import HypixelV2Client, project_root_from_here, load_api_key

def main(ttl_s: int = 300):
    root = project_root_from_here(__file__)
    cache = root / "cache"
    out = cache / "HYPIXEL_V2" / "skyblock_news.json"

    client = HypixelV2Client(load_api_key(cache), cache / "HYPIXEL_V2")
    client.get_json("/skyblock/news", out_file=out, ttl_s=ttl_s)
    print(f"[OK] {out}")

if __name__ == "__main__":
    main()
