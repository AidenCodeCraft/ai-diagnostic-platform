"""飞书回调 S1 测试：握手、验签、解密、幂等、图片落库。"""

import base64
import hashlib
import json
import os

import pytest

from app.core.config import settings
from app.models import FeishuAttachment, FeishuEvent
from app.services.integrations.feishu.events import parse_event
from app.services.integrations.feishu.security import compute_signature

ENCRYPT_KEY = "test-encrypt-key"


def encrypt_body(payload: dict, key: str = ENCRYPT_KEY) -> bytes:
    """按飞书规则加密：key=sha256(encrypt_key)，AES-256-CBC，前 16 字节 IV，PKCS#7。"""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    pad = 16 - len(raw) % 16
    padded = raw + bytes([pad]) * pad
    iv = os.urandom(16)
    aes_key = hashlib.sha256(key.encode()).digest()
    encryptor = Cipher(algorithms.AES(aes_key), modes.CBC(iv)).encryptor()
    cipher_text = encryptor.update(padded) + encryptor.finalize()
    return json.dumps({"encrypt": base64.b64encode(iv + cipher_text).decode()}).encode()


def image_event(event_id="evt-1", message_id="om-1", image_keys=("img_v3_aaa",)):
    content = json.dumps({"image_key": image_keys[0]}) if len(image_keys) == 1 else json.dumps(
        {"content": [[{"tag": "img", "image_key": k}] for k in image_keys]}
    )
    return {
        "schema": "2.0",
        "header": {"event_id": event_id, "event_type": "im.message.receive_v1", "tenant_key": "t-1"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou-1"}},
            "message": {
                "message_id": message_id,
                "chat_id": "oc-1",
                "message_type": "image" if len(image_keys) == 1 else "post",
                "content": content,
            },
        },
    }


@pytest.fixture
def feishu_settings(monkeypatch):
    monkeypatch.setattr(settings, "FEISHU_ENABLED", True)
    monkeypatch.setattr(settings, "FEISHU_VERIFICATION_TOKEN", "vt-123")
    monkeypatch.setattr(settings, "FEISHU_ENCRYPT_KEY", "")
    return settings


def post(client, body: bytes, headers=None):
    return client.post("/api/v1/integrations/feishu/events", content=body, headers=headers or {})


def test_disabled_integration_returns_404(client):
    resp = post(client, b"{}")
    assert resp.status_code == 404


def test_url_verification_returns_challenge(client, feishu_settings):
    body = json.dumps({"type": "url_verification", "token": "vt-123", "challenge": "abc"}).encode()
    resp = post(client, body)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"challenge": "abc"}


def test_rejects_when_no_credentials_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "FEISHU_ENABLED", True)
    monkeypatch.setattr(settings, "FEISHU_VERIFICATION_TOKEN", "")
    monkeypatch.setattr(settings, "FEISHU_ENCRYPT_KEY", "")
    resp = post(client, b"{}")
    assert resp.status_code == 503


def test_rejects_wrong_verification_token(client, feishu_settings):
    body = json.dumps({"token": "wrong", **image_event()}).encode()
    resp = post(client, body)
    assert resp.status_code == 403


def test_image_event_creates_pending_attachment(client, feishu_settings, db_session):
    body = json.dumps({"token": "vt-123", **image_event()}).encode()
    resp = post(client, body)

    assert resp.status_code == 200, resp.text
    body_json = resp.json()
    assert body_json["status"] == "accepted"
    assert len(body_json["attachment_ids"]) == 1

    attachment = db_session.query(FeishuAttachment).one()
    assert attachment.image_key == "img_v3_aaa"
    assert attachment.message_id == "om-1"
    assert attachment.status == "pending"
    assert db_session.query(FeishuEvent).one().status == "processed"


def test_non_image_message_is_ignored(client, feishu_settings, db_session):
    event = image_event()
    event["event"]["message"]["message_type"] = "text"
    event["event"]["message"]["content"] = json.dumps({"text": "你好"})
    resp = post(client, json.dumps({"token": "vt-123", **event}).encode())

    assert resp.json()["status"] == "ignored"
    assert db_session.query(FeishuAttachment).count() == 0
    assert db_session.query(FeishuEvent).one().status == "ignored"


def test_duplicate_event_is_idempotent(client, feishu_settings, db_session):
    body = json.dumps({"token": "vt-123", **image_event()}).encode()
    first = post(client, body)
    second = post(client, body)

    assert first.json()["status"] == "accepted"
    assert second.json()["status"] == "duplicate"
    assert db_session.query(FeishuEvent).count() == 1
    assert db_session.query(FeishuAttachment).count() == 1


def test_encrypted_event_with_valid_signature(client, monkeypatch, db_session):
    monkeypatch.setattr(settings, "FEISHU_ENABLED", True)
    monkeypatch.setattr(settings, "FEISHU_VERIFICATION_TOKEN", "")
    monkeypatch.setattr(settings, "FEISHU_ENCRYPT_KEY", ENCRYPT_KEY)

    body = encrypt_body(image_event(event_id="evt-enc"))
    timestamp, nonce = "1700000000", "nonce-1"
    signature = compute_signature(timestamp, nonce, ENCRYPT_KEY, body)
    resp = post(client, body, headers={
        "X-Lark-Request-Timestamp": timestamp,
        "X-Lark-Request-Nonce": nonce,
        "X-Lark-Signature": signature,
    })

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "accepted"
    assert db_session.query(FeishuAttachment).one().image_key == "img_v3_aaa"


def test_encrypted_event_with_bad_signature_rejected(client, monkeypatch, db_session):
    monkeypatch.setattr(settings, "FEISHU_ENABLED", True)
    monkeypatch.setattr(settings, "FEISHU_VERIFICATION_TOKEN", "")
    monkeypatch.setattr(settings, "FEISHU_ENCRYPT_KEY", ENCRYPT_KEY)

    body = encrypt_body(image_event())
    resp = post(client, body, headers={
        "X-Lark-Request-Timestamp": "1700000000",
        "X-Lark-Request-Nonce": "nonce-1",
        "X-Lark-Signature": "deadbeef",
    })

    assert resp.status_code == 403
    assert db_session.query(FeishuAttachment).count() == 0


def test_post_message_extracts_all_image_keys():
    message = parse_event(image_event(image_keys=("img_a", "img_b")))
    assert message is not None
    assert message.image_keys == ["img_a", "img_b"]


def test_attachment_endpoint_requires_auth(anon_client, feishu_settings):
    # 注意：`client` fixture 默认已带登录态（conftest 会注入 Authorization），
    # 断言未登录必须用 anon_client，否则测出来的是"附件不存在"的 404。
    resp = anon_client.get("/api/v1/integrations/feishu/attachments/1")
    assert resp.status_code in (401, 403)


def test_attachment_endpoint_returns_status(client, feishu_settings, admin_headers, db_session):
    post(client, json.dumps({"token": "vt-123", **image_event()}).encode())
    attachment = db_session.query(FeishuAttachment).one()

    resp = client.get(
        f"/api/v1/integrations/feishu/attachments/{attachment.id}", headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["image_key"] == "img_v3_aaa"
    assert body["status"] == "pending"
