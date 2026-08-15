from __future__ import annotations

import shutil
from pathlib import Path

SPRITE_PATHS = [
    "sprites/pokemon/other/official-artwork",
    "sprites/pokemon",
]

_SOURCES = {
    "official-artwork": "sprites/pokemon/other/official-artwork",
    "front-default": "sprites/pokemon",
}


def download_images(checkout: Path, images_dir: Path) -> int:
    """Copy numeric-id PNGs out of a PokeAPI/sprites checkout into `images_dir`.

    Only `<id>.png` files are taken. Variant sprites such as `25-female.png` and
    the shiny/back subdirectories are skipped, which is what keeps this to a few
    hundred megabytes rather than the full 1.6GB repo.
    """
    copied = 0
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
            if not destination.exists():
                shutil.copyfile(png, destination)
            copied += 1
    return copied
