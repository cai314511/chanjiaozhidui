"""按授权会话签发短期TURN REST凭证，服务端密钥不发送给浏览器。"""
import base64
import hashlib
import hmac
import os
import re
import time

from fastapi import HTTPException
from dotenv import dotenv_values
from pathlib import Path


def connectivity(actor_id):
    local = dotenv_values(Path(__file__).resolve().parents[1] / '.env')

    def setting(key, default=''):
        return os.environ.get(key, local.get(key) or default)

    def urls(key, schemes):
        values = [v.strip() for v in setting(key).split(',') if v.strip()]
        if len(values) > 8 or any(not re.fullmatch(
                rf'(?:{schemes}):[A-Za-z0-9.\-\[\]:]+(?:\?transport=(?:udp|tcp))?', v) for v in values):
            raise HTTPException(503, '面试网络服务配置无效，请联系管理员检查STUN/TURN地址')
        return values

    stun = urls('INTERVIEW_STUN_URLS', 'stun|stuns')
    turn = urls('INTERVIEW_TURN_URLS', 'turn|turns')
    servers = [{'urls': stun}] if stun else []
    ttl = 600
    if turn:
        secret = setting('INTERVIEW_TURN_SECRET')
        if len(secret) < 16:
            raise HTTPException(503, '面试中继凭证尚未配置，请联系管理员')
        try:
            ttl = int(setting('INTERVIEW_TURN_TTL', '600'))
        except ValueError:
            raise HTTPException(503, '面试中继凭证有效期配置无效') from None
        if not 60 <= ttl <= 3600:
            raise HTTPException(503, '面试中继凭证有效期需为60至3600秒')
        username = f'{int(time.time()) + ttl}:{actor_id}'
        credential = base64.b64encode(hmac.new(secret.encode(), username.encode(), hashlib.sha1).digest()).decode()
        servers.append({'urls': turn, 'username': username, 'credential': credential})
    return {'iceServers': servers, 'relay_configured': bool(turn), 'expires_in': ttl if turn else None,
            'message': '已配置中继；实际连接仍需网络验收。' if turn else '未配置中继，当前仅尝试直连，跨网可能无法接通。'}
