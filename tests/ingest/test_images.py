from __future__ import annotations

from ingest.images import _SOURCES, SPRITE_PATHS, download_images


def test_download_images_copies_into_expected_layout(tmp_path):
    checkout = tmp_path / "sprites"
    artwork = checkout / "sprites" / "pokemon" / "other" / "official-artwork"
    small = checkout / "sprites" / "pokemon"
    artwork.mkdir(parents=True)
    (artwork / "25.png").write_bytes(b"art")
    (small / "25.png").write_bytes(b"sprite")
    (small / "25-female.png").write_bytes(b"variant")

    images_dir = tmp_path / "images"
    result = download_images(checkout, images_dir)

    assert (images_dir / "official-artwork" / "25.png").read_bytes() == b"art"
    assert (images_dir / "front-default" / "25.png").read_bytes() == b"sprite"
    assert not (images_dir / "front-default" / "25-female.png").exists()
    assert result.copied == 2
    assert result.skipped == 0


def test_download_images_is_idempotent(tmp_path):
    checkout = tmp_path / "sprites"
    small = checkout / "sprites" / "pokemon"
    small.mkdir(parents=True)
    (small / "1.png").write_bytes(b"sprite")

    images_dir = tmp_path / "images"
    result1 = download_images(checkout, images_dir)
    assert result1.copied == 1
    assert result1.skipped == 0

    result2 = download_images(checkout, images_dir)
    assert result2.copied == 0
    assert result2.skipped == 1


def test_download_images_recovers_truncated_files(tmp_path):
    checkout = tmp_path / "sprites"
    small = checkout / "sprites" / "pokemon"
    small.mkdir(parents=True)
    (small / "1.png").write_bytes(b"complete sprite data")

    images_dir = tmp_path / "images"
    # First run copies the file
    result1 = download_images(checkout, images_dir)
    assert result1.copied == 1
    assert result1.skipped == 0

    # Simulate an interrupted copy by truncating the destination
    dest = images_dir / "front-default" / "1.png"
    dest.write_bytes(b"trunc")

    # Second run should detect size mismatch and re-copy
    result2 = download_images(checkout, images_dir)
    assert result2.copied == 1
    assert result2.skipped == 0
    assert dest.read_bytes() == b"complete sprite data"


def test_sprite_paths_derived_from_sources(tmp_path):
    """SPRITE_PATHS and _SOURCES stay in sync (SPRITE_PATHS = list(_SOURCES.values()))."""
    assert SPRITE_PATHS == list(_SOURCES.values())
