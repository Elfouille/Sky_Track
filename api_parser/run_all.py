# api_parser/run_all.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import sys

from HYPIXEL_V2.resources_election import main as election_main
from HYPIXEL_V2.resources_items import main as items_main
from HYPIXEL_V2.resources_skills import main as skills_main
from HYPIXEL_V2.resources_collections import main as collections_main

from HYPIXEL_V2.skyblock_garden import main as garden_main
from HYPIXEL_V2.skyblock_museum import main as museum_main
from HYPIXEL_V2.skyblock_bazaar import main as bazaar_main
from HYPIXEL_V2.skyblock_news import main as news_main
from HYPIXEL_V2.skyblock_profile import main as profile_main


def run_one(name: str, fn, ttl_s: int):
    try:
        fn(ttl_s=ttl_s)
        return True
    except Exception as e:
        print(f"[ERR] {name}: {e}")
        return False


def main():
    """
    Suggested TTL:
      - bazaar: 15s
      - profile: 60s
      - museum/garden: 900s
      - news/election: 300s
      - resources_*: 86400s
    """

    ok = True

    ok &= run_one("resources_items", items_main, 86400)
    ok &= run_one("resources_skills", skills_main, 86400)
    ok &= run_one("resources_collections", collections_main, 86400)

    ok &= run_one("resources_election", election_main, 300)
    ok &= run_one("skyblock_news", news_main, 300)

    ok &= run_one("skyblock_garden", garden_main, 900)
    ok &= run_one("skyblock_museum", museum_main, 900)

    ok &= run_one("skyblock_profile", profile_main, 60)
    ok &= run_one("skyblock_bazaar", bazaar_main, 15)

    if not ok:
        sys.exit(1)

    print("[OK] run_all finished")


if __name__ == "__main__":
    main()
