"""飞书回调的安全处理：签名校验 + AES 解密。

飞书加密模式（应用后台配置 Encrypt Key 后必开）：
  - 请求体形如 {"encrypt": "<base64>"}
  - key = sha256(encrypt_key)，AES-256-CBC
  - 密文前 16 字节是 IV，其余为 PKCS#7 填充的明文
  - 请求头 X-Lark-Signature = sha256(timestamp + nonce + encrypt_key + body)

不做"没配 key 就跳过校验"的降级：跳过校验等于允许任何人伪造事件往库里塞数据。
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from typing import Any, Dict


class FeishuSecurityError(RuntimeError):
    """签名或解密失败。"""


def compute_signature(timestamp: str, nonce: str, encrypt_key: str, body: bytes) -> str:
    seed = f"{timestamp}{nonce}{encrypt_key}".encode("utf-8")
    return hashlib.sha256(seed + body).hexdigest()


def verify_signature(
    timestamp: str, nonce: str, encrypt_key: str, body: bytes, signature: str,
) -> bool:
    if not (timestamp and nonce and encrypt_key and signature):
        return False
    expected = compute_signature(timestamp, nonce, encrypt_key, body)
    return hmac.compare_digest(expected, signature)


def _unpad(data: bytes) -> bytes:
    if not data:
        raise FeishuSecurityError("解密结果为空")
    pad = data[-1]
    if pad < 1 or pad > 16:
        raise FeishuSecurityError(f"PKCS#7 填充非法: {pad}")
    return data[:-pad]


def decrypt_payload(encrypt_key: str, encrypted: str) -> Dict[str, Any]:
    """解密飞书加密事件体。"""
    if not encrypt_key:
        raise FeishuSecurityError("未配置 FEISHU_ENCRYPT_KEY，无法解密事件")

    try:
        raw = base64.b64decode(encrypted)
    except (binascii.Error, ValueError) as exc:
        raise FeishuSecurityError(f"encrypt 字段不是合法 base64: {exc}") from exc

    if len(raw) <= 16:
        raise FeishuSecurityError("密文长度不足（缺少 IV）")

    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
    iv, cipher_text = raw[:16], raw[16:]
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    plain = decryptor.update(cipher_text) + decryptor.finalize()

    try:
        return json.loads(_unpad(plain).decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise FeishuSecurityError(f"解密后不是合法 JSON: {exc}") from exc
