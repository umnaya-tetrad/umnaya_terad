from dataclasses import dataclass
from uuid import UUID,uuid4
import re
from .access import Actor
from .errors import DomainError
@dataclass(frozen=True)
class MutationContext:
    actor:Actor
    expected_revision:int|None
    idempotency_key:UUID
    request_id:UUID

def context_for_request(request,actor,*,create=False):
    try:
        key=UUID(request.headers['idempotency-key'])
        value=request.headers.get('if-match')
        if create: revision=None
        else:
            if not value or not re.fullmatch(r'"\d+"',value): raise ValueError()
            revision=int(value[1:-1])
        return MutationContext(actor,revision,key,uuid4())
    except (ValueError,KeyError): raise DomainError(422,'invalid_input','Нужны Idempotency-Key и актуальная версия проверки.')

def verify_origin(request,svc):
    origins={x.strip().rstrip('/') for x in svc.settings.allowed_browser_origins.split(',')}
    if request.headers.get('origin') not in origins: raise DomainError(403,'forbidden','Недопустимый источник запроса.')
