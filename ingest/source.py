from __future__ import annotations

import subprocess
from pathlib import Path

CSV_REPO = "https://github.com/PokeAPI/pokeapi.git"
SPRITES_REPO = "https://github.com/PokeAPI/sprites.git"
CSV_PATH_IN_REPO = "data/v2/csv"


def sparse_clone(repo_url: str, paths: list[str], dest: Path) -> Path:
    """Blobless sparse clone of `paths` from `repo_url` into `dest`.

    Skips the clone if `dest` already holds a git checkout, so reruns are cheap.
    """
    if (dest / ".git").exists():
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--filter=blob:none", "--sparse", "--depth", "1", repo_url, str(dest)],
        check=True,
    )
    subprocess.run(["git", "sparse-checkout", "set", *paths], cwd=dest, check=True)
    return dest
