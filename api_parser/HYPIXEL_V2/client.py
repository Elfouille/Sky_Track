# api_parser/HYPIXEL_V2/client.py
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests

BASE_URL = "https://api.hypixel.net/v2"
UA = "Sky_Track/0.1 (cache-first; HypixelV2)"


def project_root_from_here(file_path: str | Path) -> Path:
    """
    file_path = __file__ from a module inside api_parser/HYPIXEL_V2/
    We want the project root = .../Sky_Track (the folder that contains cache/, api_parser/, core/, ui/)
    """
    p = Path(file_path).resolve()
    # .../Sky_Track/api_parser/HYPIXEL_V2/client.py -> parents[2] = .../Sky_Track
    return p.parents[2]


def read_json(path: Path, default: Any = None) -> Any:
    try:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_api_key(cache_dir: Path) -> str:
    """
    Reads cache/hypixel_key.json
    Accepts {"key":"..."} or {"api_key":"..."}
    """
    raw = read_json(cache_dir / "hypixel_key.json", default={}) or {}
    key = (raw.get("key") or raw.get("api_key") or "").strip()
    return key


def load_profile_id(cache_dir: Path) -> str:
    """
    Reads cache/profile_id.json
    Accepts {"profile_id":"..."} or {"profile":"..."}
    """
    raw = read_json(cache_dir / "profile_id.json", default={}) or {}
    pid = (raw.get("profile_id") or raw.get("profile") or "").strip()
    return pid


class HypixelV2Client:
    def __init__(self, api_key: str, cache_dir: Path):
        api_key = (api_key or "").strip()
        if not api_key:
            raise ValueError("Missing Hypixel API key (cache/hypixel_key.json).")
        self.api_key = api_key
        self.cache_dir = cache_dir

    def _is_cache_valid(self, out_file: Path, ttl_s: int) -> bool:
        if ttl_s <= 0:
            return False
        if not out_file.exists():
            return False
        age = time.time() - out_file.stat().st_mtime
        return age < ttl_s

    def get_json(
        self,
        endpoint: str,
        out_file: Path,
        params: Optional[Dict[str, Any]] = None,
        ttl_s: int = 60,
    ) -> Dict[str, Any]:
        """
        Fetch JSON from Hypixel V2 endpoint and cache it to out_file.
        Cache is used if TTL is valid.
        """
        out_file.parent.mkdir(parents=True, exist_ok=True)

        if self._is_cache_valid(out_file, ttl_s):
            return read_json(out_file, default={}) or {}

        url = f"{BASE_URL}{endpoint}"
        headers = {
            "API-Key": self.api_key,
            "User-Agent": UA,
        }

        t0 = time.time()
        r = requests.get(url, headers=headers, params=params, timeout=25)
        dt_ms = int((time.time() - t0) * 1000)

        try:
            data = r.json()
        except Exception:
            data = {"success": False, "cause": f"Non-JSON response (HTTP {r.status_code})"}

        payload = {
            "_meta": {
                "url": url,
                "endpoint": endpoint,
                "params": params or {},
                "cached_at_unix": int(time.time()),
                "http_status": r.status_code,
                "elapsed_ms": dt_ms,
            },
            "data": data,
        }

        out_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return payload
