from __future__ import annotations

import shutil
from pathlib import Path
from typing import NamedTuple

_SOURCES = {
    "official-artwork": "sprites/pokemon/other/official-artwork",
    "front-default": "sprites/pokemon",
}

SPRITE_PATHS = list(_SOURCES.values())


class CopyResult(NamedTuple):
    """Result of copying images: number copied and skipped."""

    copied: int
    skipped: int


def download_images(checkout: Path, images_dir: Path) -> CopyResult:
    """Copy numeric-id PNGs out of a PokeAPI/sprites checkout into `images_dir`.

    Only `<id>.png` files are taken. Variant sprites such as `25-female.png` and
    the shiny/back subdirectories are skipped, which is what keeps this to a few
    hundred megabytes rather than the full 1.6GB repo.
    """
    copied = 0
    skipped = 0
    for target_name, source_rel in _SOURCES.items():
        source = checkout / source_rel
        if not source.is_dir():
            continue
        target = images_dir / target_name
        target.mkdir(parents=True, exist_ok=True)
        for png in source.glob("*.png"):
            if not png.stem.isdigit():
                continue
            destination = target / png.name
            source_size = png.stat().st_size
            destination_complete = (
                destination.exists() and destination.stat().st_size == source_size
            )
            if destination_complete:
                skipped += 1
            else:
                shutil.copy2(png, destination)
                copied += 1
    return CopyResult(copied=copied, skipped=skipped)
