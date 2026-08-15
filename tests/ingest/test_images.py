from __future__ import annotations

from ingest.images import download_images


def test_download_images_copies_into_expected_layout(tmp_path):
    checkout = tmp_path / "sprites"
    artwork = checkout / "sprites" / "pokemon" / "other" / "official-artwork"
    small = checkout / "sprites" / "pokemon"
    artwork.mkdir(parents=True)
    (artwork / "25.png").write_bytes(b"art")
    (small / "25.png").write_bytes(b"sprite")
    (small / "25-female.png").write_bytes(b"variant")

    images_dir = tmp_path / "images"
    copied = download_images(checkout, images_dir)

    assert (images_dir / "official-artwork" / "25.png").read_bytes() == b"art"
    assert (images_dir / "front-default" / "25.png").read_bytes() == b"sprite"
    assert not (images_dir / "front-default" / "25-female.png").exists()
    assert copied == 2


def test_download_images_is_idempotent(tmp_path):
    checkout = tmp_path / "sprites"
    small = checkout / "sprites" / "pokemon"
    small.mkdir(parents=True)
    (small / "1.png").write_bytes(b"sprite")

    images_dir = tmp_path / "images"
    assert download_images(checkout, images_dir) == 1
    assert download_images(checkout, images_dir) == 1
