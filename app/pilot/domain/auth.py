"""Opaque hashed sessions. Provisioning functions are trusted local ports only."""
from dataclasses import dataclass,field
from uuid import UUID,uuid4
from datetime import datetime,timedelta,timezone
import asyncio,hmac,re,secrets
from auth import hash_password,verify_password,normalise_username,validate_password,AuthenticationError
from .access import Actor
from .errors import DomainError
from ..events.audit import audit
@dataclass(frozen=True)
class SessionGrant:
    session:dict
    token:str=field(repr=False)
def token_hash(svc,token): return hmac.new(svc.settings.visitor_cookie_secret.encode(),token.encode('ascii'),'sha256').hexdigest()
async def authenticate(svc,login,password):
    try: login=normalise_username(login)
    except AuthenticationError: raise DomainError(401,'unauthenticated','Неверный логин или пароль.')
    row=await svc.pool.fetchrow('SELECT * FROM users WHERE username=$1 AND is_active',login)
    if row is None or not await asyncio.to_thread(verify_password,password,row['password_hash']): raise DomainError(401,'unauthenticated','Неверный логин или пароль.')
    token=secrets.token_urlsafe(32)
    async with svc.pool.acquire() as con,con.transaction():
        await con.execute('INSERT INTO auth_sessions(token_hash,user_id,expires_at) VALUES($1,$2,$3)',token_hash(svc,token),row['id'],datetime.now(timezone.utc)+timedelta(days=svc.settings.auth_session_days))
        await audit(con,'auth_login',actor=Actor(row['id'],row['role']))
    return SessionGrant({'user_id':str(row['id']),'role':row['role']},token)
async def actor_for_token(svc,token):
    if not token or not re.fullmatch(r'[A-Za-z0-9_-]{43}',token): return None
    row=await svc.pool.fetchrow('SELECT u.id,u.role FROM users u JOIN auth_sessions s ON u.id=s.user_id WHERE s.token_hash=$1 AND s.expires_at>now() AND s.revoked_at IS NULL AND u.is_active',token_hash(svc,token))
    return Actor(row['id'],row['role']) if row else None
async def revoke(svc,token):
    if token and re.fullmatch(r'[A-Za-z0-9_-]{43}',token):
        await svc.pool.execute('UPDATE auth_sessions SET revoked_at=now() WHERE token_hash=$1 AND revoked_at IS NULL',token_hash(svc,token))
async def ensure_account(svc,login,password,role,*,operator_ref='local-seed',request_id=None):
    try: login=normalise_username(login);validate_password(password)
    except AuthenticationError as e: raise DomainError(422,'invalid_input',str(e))
    if role not in ('teacher','staff'): raise DomainError(422,'invalid_input','Недопустимая роль.')
    digest=await asyncio.to_thread(hash_password,password)
    async with svc.pool.acquire() as con,con.transaction():
        await con.execute('SELECT pg_advisory_xact_lock(hashtext($1))','pilot-account:'+login)
        row=await con.fetchrow('SELECT * FROM users WHERE username=$1 FOR UPDATE',login)
        if row and row['role']!=role: raise DomainError(409,'invalid_state','Роль аккаунта отличается.')
        if not row:
            uid=uuid4();await con.execute('INSERT INTO users(id,username,password_hash,role) VALUES($1,$2,$3,$4)',uid,login,digest,role)
            await audit(con,'account_created',request_id=request_id,entity_id=uid,payload={'operator_ref':operator_ref})
        else: uid=row['id']
    return {'user_id':str(uid),'role':role}
async def reset_account_password(svc,*,login,password,operator_ref,request_id):
    validate_password(password);digest=await asyncio.to_thread(hash_password,password)
    async with svc.pool.acquire() as con,con.transaction():
        row=await con.fetchrow('SELECT id,role FROM users WHERE username=$1 FOR UPDATE',normalise_username(login))
        if not row: raise DomainError(404,'not_found','Аккаунт не найден.')
        await con.execute('UPDATE users SET password_hash=$2 WHERE id=$1',row['id'],digest)
        await con.execute('UPDATE auth_sessions SET revoked_at=now() WHERE user_id=$1 AND revoked_at IS NULL',row['id'])
        await audit(con,'password_reset',request_id=request_id,entity_id=row['id'],payload={'operator_ref':operator_ref})
    return {'user_id':str(row['id']),'role':row['role']}
