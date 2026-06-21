import uuid
from pathlib import Path

from kernel.storage import save_raw


def test_save_raw_writes_under_user_and_source(tmp_path):
    uid, sid = uuid.uuid4(), uuid.uuid4()
    p = save_raw(tmp_path, uid, sid, "notes.md", b"hello")
    written = Path(p)
    assert written.read_bytes() == b"hello"
    assert str(uid) in p and str(sid) in p
    assert written.name == "notes.md"


def test_save_raw_strips_path_traversal(tmp_path):
    uid, sid = uuid.uuid4(), uuid.uuid4()
    p = save_raw(tmp_path, uid, sid, "../../etc/passwd", b"x")
    assert Path(p).name == "passwd"
    assert "/etc/passwd" not in p
    assert Path(p).resolve().is_relative_to(tmp_path.resolve())
