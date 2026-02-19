from __future__ import annotations

import shutil
import zipfile
import requests
from pathlib import Path


REPO_ZIP_URL = "https://github.com/NotEnoughUpdates/NotEnoughUpdates-REPO/archive/refs/heads/master.zip"


def project_root_from_here(file):
    return Path(file).resolve().parents[2]


def main():
    root = project_root_from_here(__file__)
    cache_neu = root / "cache" / "NEU"
    repo_dir = cache_neu / "repo"
    tmp_zip = cache_neu / "repo_tmp.zip"
    tmp_extract = cache_neu / "repo_extract"

    cache_neu.mkdir(parents=True, exist_ok=True)

    print("[INFO] Downloading NEU repo...")
    r = requests.get(REPO_ZIP_URL, timeout=60)
    r.raise_for_status()
    tmp_zip.write_bytes(r.content)

    print("[INFO] Extracting...")
    with zipfile.ZipFile(tmp_zip, "r") as z:
        z.extractall(tmp_extract)

    # Remove old repo if exists
    if repo_dir.exists():
        shutil.rmtree(repo_dir)

    # The zip extracts into NotEnoughUpdates-REPO-master/
    extracted_root = next(tmp_extract.iterdir())
    shutil.move(str(extracted_root), repo_dir)

    # Cleanup
    tmp_zip.unlink(missing_ok=True)
    shutil.rmtree(tmp_extract, ignore_errors=True)

    print(f"[OK] NEU repo updated -> {repo_dir}")


if __name__ == "__main__":
    main()
