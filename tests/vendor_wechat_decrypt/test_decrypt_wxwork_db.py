from __future__ import annotations

from pathlib import Path


def test_sync_plain_sqlite_sidecars_copies_live_wal_and_shm(tmp_path):
    import decrypt_wxwork_db as decrypt

    src = tmp_path / "src"
    out = tmp_path / "out"
    src.mkdir()
    out.mkdir()

    src_db = src / "message.db"
    out_db = out / "message.db"
    src_db.write_bytes(b"db")
    out_db.write_bytes(b"db")
    (src / "message.db-wal").write_bytes(b"wal-live")
    (src / "message.db-shm").write_bytes(b"shm-live")

    decrypt._sync_plain_sqlite_sidecars(str(src_db), str(out_db))

    assert (out / "message.db-wal").read_bytes() == b"wal-live"
    assert (out / "message.db-shm").read_bytes() == b"shm-live"


def test_sync_plain_sqlite_sidecars_removes_stale_outputs_when_source_sidecars_absent(tmp_path):
    import decrypt_wxwork_db as decrypt

    src = tmp_path / "src"
    out = tmp_path / "out"
    src.mkdir()
    out.mkdir()

    src_db = src / "message.db"
    out_db = out / "message.db"
    src_db.write_bytes(b"db")
    out_db.write_bytes(b"db")
    (out / "message.db-wal").write_bytes(b"stale-wal")
    (out / "message.db-shm").write_bytes(b"stale-shm")

    decrypt._sync_plain_sqlite_sidecars(str(src_db), str(out_db))

    assert not (out / "message.db-wal").exists()
    assert not (out / "message.db-shm").exists()
