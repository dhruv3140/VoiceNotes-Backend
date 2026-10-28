import pytest
from fastapi.testclient import TestClient

import main
import utils.database as dbm
import utils.ai
import utils.audio
from auth import rate_limit
from auth.database import Base, engine, SessionLocal
from auth.models import User
from auth.security import create_access_token
from conftest import FAKE_INDEX


async def fake_tags(text):
    return ["t"]

main.generate_tags = fake_tags


@pytest.fixture(autouse=True)
def clean():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    FAKE_INDEX.store.clear()
    rate_limit.reset_all()
    sent = []

    async def fake_email(to, otp): sent.append(("email", to, otp))
    async def fake_sms(mobile, otp, name="User"): sent.append(("sms", mobile, otp))
    import auth.routes as r
    r.send_email_otp = fake_email
    r.send_sms_otp = fake_sms
    yield sent


def make_user(email):
    db = SessionLocal()
    u = User(name=email, email=email, is_email_verified="true", auth_provider="email_otp")
    db.add(u); db.commit(); db.refresh(u)
    uid = u.id
    db.close()
    return uid, {"Authorization": "Bearer " + create_access_token({"user_id": uid, "email": email, "mobile": None})}


client = TestClient(main.app)


def test_cross_user_update_delete_blocked_and_owner_allowed():
    a_id, a = make_user("a@test.dev")
    b_id, b = make_user("b@test.dev")
    r = client.post("/notes/text", json={"text": "alice secret note"}, headers=a)
    nid = r.json()["id"]
    before = dict(FAKE_INDEX.store[nid])

    assert client.put(f"/notes/{nid}", json={"text": "hacked"}, headers=b).status_code == 404
    assert client.delete(f"/notes/{nid}", headers=b).status_code == 404
    assert FAKE_INDEX.store[nid] == before  # untouched

    assert client.put(f"/notes/{nid}", json={"text": "alice edited"}, headers=a).status_code == 200
    assert FAKE_INDEX.store[nid]["transcript"] == "alice edited"
    assert FAKE_INDEX.store[nid]["created_at"] == before["created_at"]
    assert FAKE_INDEX.store[nid]["user_id"] == float(a_id)
    assert client.put("/notes/missing-id", json={"text": "x"}, headers=a).status_code == 404
    assert client.delete(f"/notes/{nid}", headers=a).status_code == 200
    assert nid not in FAKE_INDEX.store


def test_search_is_scoped_and_uses_query():
    _, a = make_user("a@test.dev")
    _, b = make_user("b@test.dev")
    client.post("/notes/text", json={"text": "buy milk and eggs"}, headers=a)
    client.post("/notes/text", json={"text": "call the dentist tomorrow"}, headers=a)
    client.post("/notes/text", json={"text": "milk secret of bob"}, headers=b)
    res = client.post("/notes/search", json={"query": "milk"}, headers=a).json()["results"]
    assert len(res) == 1 and "eggs" in res[0]["metadata"]["transcript"]
    assert client.post("/notes/search", json={"query": "zebra"}, headers=a).json()["results"] == []
    assert client.post("/notes/search", json={"query": "  "}, headers=a).json()["results"] == []


def test_more_than_100_notes_listed():
    _, a = make_user("a@test.dev")
    for i in range(130):
        client.post("/notes/text", json={"text": f"note {i}"}, headers=a)
    assert len(client.get("/notes", headers=a).json()["notes"]) == 130


def test_failed_transcription_not_saved(monkeypatch):
    _, a = make_user("a@test.dev")

    def boom(_):
        raise utils.audio.TranscriptionError("Transcription failed. Please retry.")
    monkeypatch.setattr(main, "transcribe_audio", boom)
    r = client.post("/notes/audio", files={"file": ("a.webm", b"123", "audio/webm")}, headers=a)
    assert r.status_code == 502
    assert FAKE_INDEX.store == {}

    monkeypatch.setattr(main, "transcribe_audio", lambda b: "hello world")
    r = client.post("/notes/audio", files={"file": ("a.webm", b"123", "audio/webm")}, headers=a)
    assert r.status_code == 200 and r.json()["transcript"] == "hello world"
    assert len(FAKE_INDEX.store) == 1


def test_otp_lockout_after_failures(clean):
    uid, _ = make_user("v@test.dev")
    assert client.post("/auth/login/send-otp", json={"identifier": "v@test.dev"}).status_code == 200
    otp = clean[-1][2]
    wrong = "000000" if otp != "000000" else "111111"
    for _ in range(5):
        assert client.post("/auth/login/verify-otp", json={"identifier": "v@test.dev", "otp": wrong}).status_code == 400
    # correct OTP no longer works after lockout
    r = client.post("/auth/login/verify-otp", json={"identifier": "v@test.dev", "otp": otp})
    assert r.status_code == 429
    # and the stored OTP was cleared
    db = SessionLocal(); u = db.get(User, uid); assert u.otp_code is None; db.close()


def test_otp_correct_works_and_send_throttled(clean):
    make_user("v@test.dev")
    assert client.post("/auth/login/send-otp", json={"identifier": "v@test.dev"}).status_code == 200
    assert client.post("/auth/login/send-otp", json={"identifier": "v@test.dev"}).status_code == 429
    otp = clean[-1][2]
    assert len(otp) == 6 and otp.isdigit()
    r = client.post("/auth/login/verify-otp", json={"identifier": "v@test.dev", "otp": otp})
    assert r.status_code == 200 and "access_token" in r.json()


def test_reset_password_requires_valid_otp_and_locks(clean):
    make_user("v@test.dev")
    assert client.post("/auth/forgot-password", json={"email": "v@test.dev"}).status_code == 200
    otp = clean[-1][2]
    wrong = "000000" if otp != "000000" else "111111"
    for _ in range(5):
        assert client.post("/auth/reset-password", json={"email": "v@test.dev", "otp": wrong, "new_password": "Newpass123"}).status_code == 400
    assert client.post("/auth/reset-password", json={"email": "v@test.dev", "otp": otp, "new_password": "Newpass123"}).status_code == 429


CONCEPTS = {
    0: {"milk", "eggs", "groceries", "shopping", "bread", "kirana"},
    1: {"dentist", "doctor", "appointment", "clinic", "checkup"},
    2: {"startup", "idea", "business", "product"},
}


def fake_embed(texts, input_type):
    out = []
    for t in texts:
        words = set(dbm._tokens(t))
        v = [0.0] * dbm.EMBED_DIM
        for axis, ws in CONCEPTS.items():
            v[axis] = float(len(words & ws))
        v[100] = 0.05  # keep vectors non-zero
        out.append(v)
    return out


def test_semantic_search_finds_meaning_scoped_and_backfills(monkeypatch):
    _, a = make_user("a@test.dev")
    _, b = make_user("b@test.dev")
    # legacy notes: saved without embeddings (embedding service down)
    monkeypatch.setattr(dbm, "SEMANTIC_ENABLED", True)
    monkeypatch.setattr(dbm, "embed_texts", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    n1 = client.post("/notes/text", json={"text": "pick up bread and eggs"}, headers=a).json()["id"]
    n2 = client.post("/notes/text", json={"text": "visit clinic for checkup"}, headers=a).json()["id"]
    client.post("/notes/text", json={"text": "groceries list of bob"}, headers=b)
    assert "embedding" not in FAKE_INDEX.store[n1]

    # embeddings available now: search by meaning, not by shared words
    monkeypatch.setattr(dbm, "embed_texts", fake_embed)
    monkeypatch.setattr(dbm, "SEMANTIC_ENABLED", True)
    res = client.post("/notes/search", json={"query": "shopping"}, headers=a).json()["results"]
    assert [r["id"] for r in res] == [n1]  # meaning match, no shared word, not bob's, not the clinic note
    # backfill stored vector + tag, metadata kept
    assert FAKE_INDEX.store[n1]["embedding"] == dbm.EMBED_TAG
    assert FAKE_INDEX.store[n1]["transcript"] == "pick up bread and eggs"
    assert FAKE_INDEX.store[n1]["user_id"] == FAKE_INDEX.store[n2]["user_id"]
    res = client.post("/notes/search", json={"query": "doctor"}, headers=a).json()["results"]
    assert [r["id"] for r in res] == [n2]
    assert client.post("/notes/search", json={"query": "startup"}, headers=a).json()["results"] == []


def test_search_falls_back_to_keywords_when_embedding_down(monkeypatch):
    _, a = make_user("a@test.dev")
    monkeypatch.setattr(dbm, "embed_texts", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    client.post("/notes/text", json={"text": "call the dentist tomorrow"}, headers=a)
    res = client.post("/notes/search", json={"query": "dentist"}, headers=a)
    assert res.status_code == 200 and len(res.json()["results"]) == 1


def test_new_and_edited_notes_get_embeddings(monkeypatch):
    _, a = make_user("a@test.dev")
    monkeypatch.setattr(dbm, "embed_texts", fake_embed)
    monkeypatch.setattr(dbm, "SEMANTIC_ENABLED", True)
    nid = client.post("/notes/text", json={"text": "bread"}, headers=a).json()["id"]
    assert FAKE_INDEX.store[nid]["embedding"] == dbm.EMBED_TAG
    assert len(FAKE_INDEX.values[nid]) == dbm.EMBED_DIM and FAKE_INDEX.values[nid][0] == 1.0
    client.put(f"/notes/{nid}", json={"text": "dentist"}, headers=a)
    assert FAKE_INDEX.values[nid][1] == 1.0


def test_semantic_off_by_default_never_calls_embedding(monkeypatch):
    _, a = make_user("a@test.dev")
    calls = []
    monkeypatch.setattr(dbm, "embed_texts", lambda *a, **k: calls.append(1) or [[0.0] * dbm.EMBED_DIM])
    assert dbm.SEMANTIC_ENABLED is False
    nid = client.post("/notes/text", json={"text": "bread and milk"}, headers=a).json()["id"]
    r = client.post("/notes/search", json={"query": "milk"}, headers=a).json()
    assert r["search_mode"] == "keyword" and len(r["results"]) == 1
    assert calls == [] and "embedding" not in FAKE_INDEX.store[nid]


def test_search_mode_and_truncation_flags(monkeypatch):
    _, a = make_user("a@test.dev")
    monkeypatch.setattr(dbm, "SEMANTIC_ENABLED", True)
    monkeypatch.setattr(dbm, "embed_texts", fake_embed)
    client.post("/notes/text", json={"text": "bread"}, headers=a)
    assert client.post("/notes/search", json={"query": "shopping"}, headers=a).json()["search_mode"] == "semantic"
    monkeypatch.setattr(dbm, "embed_texts", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    assert client.post("/notes/search", json={"query": "bread"}, headers=a).json()["search_mode"] == "keyword"
    monkeypatch.setattr(main, "MAX_NOTES", 1)
    assert client.get("/notes", headers=a).json()["truncated"] is True
