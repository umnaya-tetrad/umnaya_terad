"""Browser-origin checks and bounded, best-effort throttles; not bot authentication."""
from collections import OrderedDict
import hashlib
import hmac
from ipaddress import ip_address
import time

from fastapi import HTTPException, Request


def write_origin_allowed(request: Request, settings) -> bool:
    if request.method not in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        return True
    if request.headers.get('sec-fetch-site', '').lower() == 'cross-site':
        return False
    if request.headers.get('sec-fetch-mode', '').lower() == 'navigate':
        return False
    origin = request.headers.get('origin')
    if origin is None:
        # Pilot writes require the exact browser origin, including login/logout.
        return False
    allowed = {item.strip() for item in settings.allowed_browser_origins.split(',') if item.strip()}
    return origin in allowed


def network_hash(request: Request, settings) -> str:
    address = request.client.host if request.client else 'unknown'
    # Enable only behind an edge which OVERWRITES X-Real-IP and a private backend.
    if settings.trust_forwarded_client_ip:
        try:
            address = str(ip_address(request.headers.get('x-real-ip', '')))
        except ValueError:
            pass
    return hmac.new(settings.visitor_cookie_secret.encode('utf-8'), ('network:' + address).encode('utf-8'), hashlib.sha256).hexdigest()


class InteractionThrottle:
    """Single-process safety net for cheap-write spam; LLM limits live in PostgreSQL."""
    def __init__(self):
        self._buckets = OrderedDict()
        self._last_prune = 0.0

    def admit(self, visitor: str, network: str, purpose: str):
        now = time.monotonic()
        if now - self._last_prune >= 60:
            for key, (started, _) in list(self._buckets.items()):
                if now - started >= 60:
                    del self._buckets[key]
            self._last_prune = now
        limits = (5, 20) if purpose == 'interest' else (60, 120)
        keys = ((purpose, 'visitor', visitor), (purpose, 'network', network))
        for key, limit in zip(keys, limits):
            started, count = self._buckets.get(key, (now, 0))
            if now - started >= 60:
                started, count = now, 0
            if count >= limit:
                raise HTTPException(429, 'Слишком много обращений. Повтори через минуту.', headers={'Retry-After': '60'})
        for key in keys:
            started, count = self._buckets.get(key, (now, 0))
            if now - started >= 60:
                started, count = now, 0
            self._buckets[key] = (started, count + 1)
            self._buckets.move_to_end(key)
        while len(self._buckets) > 10_000:
            self._buckets.popitem(last=False)


interaction_throttle = InteractionThrottle()
