"""Test-only HTTP adapter for APP-owned routes, sharing production domain ports.

The production processing/events routers are mounted unchanged. This harness is
deliberately kept outside application code and cannot be deployed as its entrypoint.
"""
import io
import json
import re
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import jsonschema
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse, Response
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
SHARED = ROOT / 'project-context/pilot/planning/shared'
SPEC = json.loads((SHARED / 'api/openapi.json').read_text(encoding='utf-8'))
OPS = {v['operationId']: (m.upper(), p, v) for p, methods in SPEC['paths'].items() for m, v in methods.items()}


def validate(value, schema):
    resolver = jsonschema.RefResolver((SHARED / 'api/openapi.json').as_uri(), SPEC)
    jsonschema.Draft202012Validator(schema, resolver=resolver).validate(value)


def png(size=(64, 64), fmt='PNG'):
    out = io.BytesIO()
    Image.new('RGB', size, (42, 83, 125)).save(out, format=fmt)
    return out.getvalue()


def make_app(svc):
    from pilot.domain import mutations as mu, queries as qu, auth
    from pilot.domain.access import require_actor
    from pilot.domain.revision import MutationContext
    from pilot.domain.errors import DomainError, install_error_handlers
    from pilot.domain.storage import prepare_photo
    from pilot.routes.processing import router as processing
    from pilot.routes.events import router as events
    from security import write_origin_allowed

    app = FastAPI()
    app.state.pilot_services = svc
    install_error_handlers(app)
    app.include_router(processing, prefix='/api')
    app.include_router(events, prefix='/api')

    async def endpoint(request: Request):
        operation = request.scope['route'].operation_id
        method, path, definition = OPS[operation]
        if not write_origin_allowed(request, svc.settings):
            raise DomainError(403, 'forbidden', 'Недопустимый источник запроса.')
        if operation == 'login':
            payload = await request.json()
            grant = await auth.authenticate(svc, payload['login'], payload['password'])
            response = JSONResponse(grant.session)
            response.set_cookie('smartnote_session', grant.token, httponly=True, samesite='lax', secure=svc.settings.visitor_cookie_secure)
            return response
        actor = await require_actor(request)
        if operation == 'getSession':
            return {'user_id': str(actor.user_id), 'role': actor.role}
        if operation == 'logout':
            await auth.revoke(svc, request.cookies.get('smartnote_session'))
            return Response(status_code=204)
        request_id = uuid4()
        args = [UUID(v) for v in request.path_params.values()]
        if method == 'GET':
            fn = {'listChecks': qu.list_checks, 'getCheck': qu.get_check, 'getBundleHistory': qu.get_bundle_history,
                  'getPhoto': qu.open_photo, 'listStaffChecks': qu.list_staff_checks, 'getStaffCheck': qu.get_staff_check}[operation]
            extra = {'owner_login': request.query_params.get('owner_login')} if operation == 'listStaffChecks' else {}
            value = await fn(svc, actor, *args, request_id=request_id, **extra)
            if operation == 'getPhoto':
                return FileResponse(value.path, media_type=value.media_type, headers={'Cache-Control': 'no-store'})
            return value
        key = UUID(request.headers['Idempotency-Key'])
        revision = request.headers.get('If-Match')
        ctx = MutationContext(actor, int(revision.strip('"')) if revision is not None else None, key, request_id)
        fn_name = re.sub(r'(?<!^)(?=[A-Z])', '_', operation).lower()
        fn = getattr(mu, fn_name)
        if operation == 'uploadPhoto':
            form = await request.form()
            upload = form['file']
            args.append(prepare_photo(upload.file, upload.content_type))
        elif 'requestBody' in definition:
            payload = await request.json()
            try:
                validate(payload, definition['requestBody']['content']['application/json']['schema'])
            except jsonschema.ValidationError:
                raise DomainError(422, 'invalid_input', 'Некорректные данные.')
            args.append(payload)
        value = await fn(svc, ctx, *args)
        status = int(next(k for k in definition['responses'] if k.startswith('2')))
        return JSONResponse(value, status_code=status)

    owned = {'login','logout','getSession','listChecks','createCheck','getCheck','deleteCheck','createNotebook','deleteNotebook',
             'createBundle','deleteBundle','createInputVersion','reorderPhotos','discardDraft','uploadPhoto','deleteDraftPhoto',
             'getPhoto','getBundleHistory','deleteTask','saveReview','listStaffChecks','getStaffCheck'}
    for operation in owned:
        method, path, _ = OPS[operation]
        app.add_api_route(path, endpoint, methods=[method], operation_id=operation)
    return app


class Harness:
    def __init__(self, svc):
        self.svc = svc
        self.clients = {}
        self.ids = {}
        self.http = []
        self.check_id = None

    async def start(self):
        from pilot.domain.auth import ensure_account
        for name, role in [('t1','teacher'),('t2','teacher'),('staff','staff')]:
            account = await ensure_account(self.svc, 'test_'+name, 'synthetic-test-password-47', role)
            self.ids[name] = account['user_id']
        self.app = make_app(self.svc)
        for name in ['t1','t2','staff','anon']:
            self.clients[name] = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test', headers={'Origin':'http://localhost:5173'})
            if name != 'anon':
                response = await self.call('login', actor=name, payload={'login':'test_'+name,'password':'synthetic-test-password-47'}, expected=200)
                assert response.json()['user_id'] == self.ids[name]

    async def close(self):
        for client in self.clients.values():
            await client.aclose()

    async def call(self, operation, *, actor='t1', payload=None, expected=None, key=None, revision=None, files=None, **ids):
        method, path, definition = OPS[operation]
        for name, value in ids.items():
            path = path.replace('{' + name + '}', str(value))
        headers = {}
        if method != 'GET' and operation not in ('login','logout','ingestEvents'):
            headers['Idempotency-Key'] = str(key or uuid4())
            if operation != 'createCheck':
                if revision is None and self.check_id:
                    revision = await self.svc.pool.fetchval('SELECT revision FROM pilot_checks WHERE id=$1', UUID(str(self.check_id)))
                headers['If-Match'] = '"' + str(revision) + '"'
        response = await self.clients[actor].request(method, path, json=payload, headers=headers, files=files)
        self.http.append((operation, response.status_code))
        if expected is not None:
            assert response.status_code == expected, (operation,response.status_code,response.text)
        schema = definition['responses'].get(str(response.status_code),{}).get('content',{}).get('application/json',{}).get('schema')
        if schema:
            validate(response.json(), schema)
        return response

    async def create(self, *, actor='t1', photos=1):
        result = (await self.call('createCheck', actor=actor, payload={'title':'Синтетическая проверка'}, expected=201)).json()
        self.check_id = result['check_id']
        notebook = (await self.call('createNotebook', actor=actor, check_id=self.check_id, expected=201)).json()
        bundle = (await self.call('createBundle', actor=actor, notebook_id=notebook['entity_id'], expected=201)).json()
        check = await self.check(actor)
        item = next(b for n in check['notebooks'] for b in n['bundles'] if b['id'] == bundle['entity_id'])
        version = item['draft']['id']
        for _ in range(photos):
            await self.call('uploadPhoto', actor=actor, input_version_id=version, files={'file':('synthetic.png',png(),'image/png')}, expected=201)
        return self.check_id, notebook['entity_id'], bundle['entity_id'], version

    async def check(self, actor='t1'):
        return (await self.call('getCheck', actor=actor, check_id=self.check_id, expected=200)).json()

    async def submit(self, bundle, version, **kwargs):
        return await self.call('submitBundle', bundle_id=bundle, payload={'input_version_id':version}, **kwargs)

    async def run(self):
        from pilot.processing.worker import run_once
        return await run_once(self.svc)

    async def review_all(self):
        for notebook in (await self.check())['notebooks']:
            for bundle in notebook['bundles']:
                for task in bundle['tasks']:
                    analysis = task['analysis']
                    if analysis['result'] == 'not_assessed':
                        await self.call('skipTask',task_id=task['task_id'],payload={'analysis_id':task['analysis_id']},expected=200)
                    else:
                        await self.call('saveReview',task_id=task['task_id'],payload={'analysis_id':task['analysis_id'],'state':'confirmed','comment':''},expected=200)
