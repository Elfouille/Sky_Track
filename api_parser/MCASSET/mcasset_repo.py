from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
import zipfile
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

import requests


UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Sky_Track/MCASSET"

REPO_URL = "https://github.com/InventivetalentDev/minecraft-assets.git"
REPO_OWNER = "InventivetalentDev"
REPO_NAME = "minecraft-assets"

DEFAULT_VERSION = "1.21.11"

ENTITY_PATH = Path("assets/minecraft/textures/entity")
ITEM_PATH = Path("assets/minecraft/textures/item")
BLOCK_PATH = Path("assets/minecraft/textures/block")  # ✅ NEW


# ----------------------------
# Utils
# ----------------------------
def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def safe_mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def norm_rel(p: Path) -> str:
    return str(p).replace("\\", "/")


def resolve_project_root() -> Path:
    # api_parser/MCASSET/mcasset_repo.py -> root = Sky_Track (parents[2])
    here = Path(__file__).resolve()
    if len(here.parents) >= 3:
        return here.parents[2]
    return Path.cwd()


def run(cmd, cwd: Optional[Path] = None) -> Tuple[int, str]:
    p = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        shell=False,
    )
    return p.returncode, p.stdout


def has_git() -> bool:
    try:
        code, _ = run(["git", "--version"])
        return code == 0
    except Exception:
        return False


def iter_png_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*.png"):
        if p.is_file():
            yield p


def file_sig(path: Path) -> Dict[str, object]:
    st = path.stat()
    return {"size": st.st_size, "mtime": int(st.st_mtime)}


# ----------------------------
# Repo acquisition (GIT sparse)
# ----------------------------
def ensure_repo_git_sparse(repo_dir: Path, version: str) -> Path:
    """
    Clone/pull shallow + sparse checkout UNIQUEMENT:
      - assets/minecraft/textures/entity
      - assets/minecraft/textures/item
      - assets/minecraft/textures/block
    """
    safe_mkdir(repo_dir.parent)

    sparse_paths = [
        "assets/minecraft/textures/entity",
        "assets/minecraft/textures/item",
        "assets/minecraft/textures/block",  # ✅ NEW
    ]

    if not repo_dir.exists():
        print(f"[{_now()}] git clone (partial + no-checkout) -> {repo_dir}")
        code, out = run(
            [
                "git",
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                "--depth",
                "1",
                REPO_URL,
                str(repo_dir),
            ]
        )
        if code != 0:
            raise RuntimeError(f"git clone failed:\n{out}")

    # sparse checkout init (cone mode)
    print(f"[{_now()}] git sparse-checkout init --cone")
    code, out = run(["git", "sparse-checkout", "init", "--cone"], cwd=repo_dir)
    if code != 0 and "already" not in out.lower():
        print(f"[{_now()}] WARN: sparse-checkout init: {out.strip()}")

    # set sparse paths
    print(f"[{_now()}] git sparse-checkout set {', '.join(sparse_paths)}")
    code, out = run(["git", "sparse-checkout", "set", *sparse_paths], cwd=repo_dir)
    if code != 0:
        raise RuntimeError(f"git sparse-checkout set failed:\n{out}")

    # fetch shallow the requested ref
    print(f"[{_now()}] git fetch origin {version} (shallow)")
    code, out = run(["git", "fetch", "--depth", "1", "origin", version], cwd=repo_dir)
    if code != 0:
        print(f"[{_now()}] WARN: fetch ref failed, trying shallow fetch --all")
        code2, out2 = run(["git", "fetch", "--depth", "1", "--all"], cwd=repo_dir)
        if code2 != 0:
            raise RuntimeError(f"git fetch failed:\n{out}\n---\n{out2}")

    # checkout the ref
    print(f"[{_now()}] git checkout {version}")
    code, out = run(["git", "checkout", "--force", version], cwd=repo_dir)
    if code != 0:
        print(f"[{_now()}] WARN: checkout {version} failed, trying FETCH_HEAD")
        code2, out2 = run(["git", "checkout", "--force", "FETCH_HEAD"], cwd=repo_dir)
        if code2 != 0:
            raise RuntimeError(f"git checkout failed:\n{out}\n---\n{out2}")

    run(["git", "gc", "--prune=now"], cwd=repo_dir)
    return repo_dir


# ----------------------------
# Repo acquisition (ZIP selective extract)
# ----------------------------
def download_repo_zip_selective(tmp_dir: Path, version: str) -> Path:
    """
    Download ZIP and extract ONLY:
      - assets/minecraft/textures/entity
      - assets/minecraft/textures/item
      - assets/minecraft/textures/block
    Returns extracted root folder.
    """
    safe_mkdir(tmp_dir)
    zip_path = tmp_dir / f"{REPO_NAME}-{version}.zip"

    urls = [
        f"https://codeload.github.com/{REPO_OWNER}/{REPO_NAME}/zip/refs/heads/{version}",
        f"https://codeload.github.com/{REPO_OWNER}/{REPO_NAME}/zip/refs/tags/{version}",
    ]

    ok = False
    last_err = None
    for zip_url in urls:
        try:
            print(f"[{_now()}] Download ZIP: {zip_url}")
            with requests.get(zip_url, stream=True, timeout=180, headers={"User-Agent": UA}) as r:
                if r.status_code == 404:
                    last_err = f"404: {zip_url}"
                    continue
                r.raise_for_status()
                with open(zip_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            f.write(chunk)
            ok = True
            break
        except Exception as e:
            last_err = repr(e)

    if not ok:
        raise RuntimeError(f"ZIP download failed: {last_err}")

    extract_dir = tmp_dir / f"extract_{version}"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    safe_mkdir(extract_dir)

    want1 = norm_rel(ENTITY_PATH)
    want2 = norm_rel(ITEM_PATH)
    want3 = norm_rel(BLOCK_PATH)  # ✅ NEW

    with zipfile.ZipFile(zip_path, "r") as z:
        names = z.namelist()

        wanted = []
        for n in names:
            nn = n.replace("\\", "/")
            if f"/{want1}/" in nn or nn.endswith(f"/{want1}"):
                wanted.append(n)
            elif f"/{want2}/" in nn or nn.endswith(f"/{want2}"):
                wanted.append(n)
            elif f"/{want3}/" in nn or nn.endswith(f"/{want3}"):  # ✅ NEW
                wanted.append(n)

        if not wanted:
            raise RuntimeError("ZIP selective extract: no matching paths found for entity/item/block.")

        for n in wanted:
            z.extract(n, extract_dir)

    roots = [p for p in extract_dir.iterdir() if p.is_dir()]
    if not roots:
        raise RuntimeError("ZIP extract failed: no root dir found")
    return roots[0]


# ----------------------------
# Copy & manifest
# ----------------------------
def sync_from_local_tree(
    *,
    src_base: Path,
    dst_base: Path,
    manifest_path: Path,
    refresh: bool,
    limit: Optional[int],
) -> Dict:
    old = load_json(manifest_path, default={})
    old_items: Dict[str, dict] = old.get("items", {})

    safe_mkdir(dst_base)

    copied = 0
    skipped = 0
    failed = 0
    seen = 0

    t0 = time.time()

    for src in iter_png_files(src_base):
        rel = src.relative_to(src_base)
        key = norm_rel(rel)

        seen += 1
        if limit is not None and seen > limit:
            break

        dst = dst_base / rel
        prev = old_items.get(key)
        sig = file_sig(src)

        already_ok = (
            (not refresh)
            and prev is not None
            and prev.get("size") == sig["size"]
            and prev.get("mtime") == sig["mtime"]
            and Path(prev.get("local_path", "")).exists()
        )

        if already_ok:
            skipped += 1
            continue

        try:
            safe_mkdir(dst.parent)
            shutil.copy2(src, dst)
            copied += 1
            old_items[key] = {
                "size": sig["size"],
                "mtime": sig["mtime"],
                "local_path": str(dst),
                "src_path": str(src),
            }
            if copied % 500 == 0:
                print(f"  ... copied={copied} skipped={skipped} failed={failed}")
        except Exception as e:
            failed += 1
            old_items[key] = {
                "size": sig["size"],
                "mtime": sig["mtime"],
                "local_path": str(dst),
                "src_path": str(src),
                "error": repr(e),
            }
            print(f"[WARN] copy failed: {src} -> {dst} ({e})")

    dt = time.time() - t0

    out = {
        "_meta": {
            "generated_at": _now(),
            "src_base": str(src_base),
            "dst_base": str(dst_base),
            "stats": {
                "seen_png": seen,
                "copied": copied,
                "skipped": skipped,
                "failed": failed,
                "seconds": round(dt, 3),
            },
        },
        "items": old_items,
    }
    save_json(manifest_path, out)
    return out


# ----------------------------
# Main
# ----------------------------
def main() -> int:
    ap = argparse.ArgumentParser(
        description="Sync MCASSET textures (entity+item+block) into cache/MCASSET using git sparse-checkout (no rate limits)."
    )
    ap.add_argument("--version", default=DEFAULT_VERSION, help="Repo ref (branch/tag), default: 1.21.11")
    ap.add_argument("--refresh", action="store_true", help="Force recopy even if unchanged")
    ap.add_argument("--limit", type=int, default=None, help="Limit number of PNG per category (debug)")
    ap.add_argument("--force-zip", action="store_true", help="Force ZIP mode (ignore git)")
    args = ap.parse_args()

    project_root = resolve_project_root()
    cache_root = project_root / "cache" / "MCASSET"
    repo_dir = cache_root / "_repo_sparse"
    tmp_dir = cache_root / "_tmp_zip"

    mobs_out = cache_root / "mobs"
    item_out = cache_root / "item"
    block_out = cache_root / "block"  # ✅ NEW
    safe_mkdir(mobs_out)
    safe_mkdir(item_out)
    safe_mkdir(block_out)

    print(f"[{_now()}] Project root: {project_root}")
    print(f"[{_now()}] Cache root:   {cache_root}")
    print(f"[{_now()}] Version:      {args.version}")

    # Acquire local source tree
    if (not args.force_zip) and has_git():
        print(f"[{_now()}] Mode: git sparse-checkout (entity+item+block)")
        source_root = ensure_repo_git_sparse(repo_dir, args.version)
    else:
        if args.force_zip:
            print(f"[{_now()}] Mode: zip (forced)")
        else:
            print(f"[{_now()}] Mode: zip (git not found)")
        source_root = download_repo_zip_selective(tmp_dir, args.version)

    entity_src = source_root / ENTITY_PATH
    item_src = source_root / ITEM_PATH
    block_src = source_root / BLOCK_PATH  # ✅ NEW

    if not entity_src.exists():
        raise RuntimeError(f"Entity path not found: {entity_src}")
    if not item_src.exists():
        raise RuntimeError(f"Item path not found: {item_src}")
    if not block_src.exists():
        raise RuntimeError(f"Block path not found: {block_src}")

    entity_manifest = cache_root / "mcasset_entity_manifest.json"
    item_manifest = cache_root / "mcasset_item_manifest.json"
    block_manifest = cache_root / "mcasset_block_manifest.json"  # ✅ NEW

    print(f"[{_now()}] Sync entity -> {mobs_out}")
    ent = sync_from_local_tree(
        src_base=entity_src,
        dst_base=mobs_out,
        manifest_path=entity_manifest,
        refresh=args.refresh,
        limit=args.limit,
    )

    print(f"[{_now()}] Sync item -> {item_out}")
    it = sync_from_local_tree(
        src_base=item_src,
        dst_base=item_out,
        manifest_path=item_manifest,
        refresh=args.refresh,
        limit=args.limit,
    )

    print(f"[{_now()}] Sync block -> {block_out}")
    bl = sync_from_local_tree(
        src_base=block_src,
        dst_base=block_out,
        manifest_path=block_manifest,
        refresh=args.refresh,
        limit=args.limit,
    )

    print(f"\n[{_now()}] DONE")
    print("  Entity manifest:", entity_manifest)
    print("  Item   manifest:", item_manifest)
    print("  Block  manifest:", block_manifest)
    print("  Entity stats:", ent["_meta"]["stats"])
    print("  Item   stats:", it["_meta"]["stats"])
    print("  Block  stats:", bl["_meta"]["stats"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
