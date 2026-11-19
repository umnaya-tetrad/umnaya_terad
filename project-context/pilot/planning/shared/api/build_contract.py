"""Rebuild the offline HTTP contract. No application or network access."""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCHEMA = "https://json-schema.org/draft/2020-12/schema"
UUID = {"type": "string", "format": "uuid"}
REV = {"type": "integer", "minimum": 0}
TIME = {"type": "string", "format": "date-time"}
BOOL = {"type": "boolean"}
TEXT = {"type": "string"}


def enum(*values):
    return {"type": "string", "enum": list(values)}


def nullable(value):
    return {"anyOf": [copy.deepcopy(value), {"type": "null"}]}


def array(value, **extra):
    return {"type": "array", "items": copy.deepcopy(value), **extra}


def ref(name):
    return {"$ref": "#/$defs/" + name}


def field(schema, consumer):
    return {**copy.deepcopy(schema), "description": consumer}


def obj(**properties):
    return {"type": "object", "additionalProperties": False,
            "required": list(properties), "properties": properties}


D = {}
D["Error"] = obj(code=field(enum("invalid_input", "unauthenticated", "forbidden", "not_found",
    "revision_conflict", "idempotency_conflict", "invalid_state", "completion_blocked", "stale_analysis",
    "processing_unavailable"), "Клиент: выбрать действие после отказа."),
    message=field(TEXT, "Учитель: безопасное пояснение без traceback и секретов."),
    current_revision=field(nullable(REV), "Клиент: перечитать Check при конфликте; null вне контекста проверки."))
D["ErrorResponse"] = obj(error=ref("Error"))
D["Login"] = obj(login=field({"type": "string", "minLength": 1, "maxLength": 128}, "Auth: выданный логин."),
    password=field({"type": "string", "minLength": 1, "maxLength": 1024, "writeOnly": True}, "Auth: пароль; никогда не логировать."))
D["Session"] = obj(user_id=field(UUID, "Auth/UI: владелец; staff аудит сохраняет реального актора."),
    role=field(enum("teacher", "staff"), "Router: teacher свои материалы; staff только чтение команды. Пауза обработки — привилегированная CLI, без HTTP-роли оператора."))
D["Title"] = obj(title=field({"type": "string", "minLength": 1, "maxLength": 200}, "Учитель: название проверки без ФИО; пробелы по краям удаляет сервер."))
D["Photo"] = obj(id=field(UUID, "UI: приватный GET /assets/{id}; идентификатор сохраненного файла."),
    media_type=field(enum("image/jpeg", "image/png", "image/webp"), "UI/worker: фактический нормализованный формат."))
D["InputVersion"] = obj(id=field(UUID, "Submit/worker: неизменяемый после submit вход."),
    state=field(enum("draft", "sealed"), "UI: разрешены ли изменения фото."),
    photos=field(array(ref("Photo")), "UI/worker: порядок массива задает photo_index от 1; отдельного order нет."))
D["PhotoOrder"] = obj(photo_ids=field(array(UUID, uniqueItems=True), "Draft editor: точная перестановка всех существующих фото; не добавляет и не удаляет файл."))
D["VersionCreate"] = obj(photo_ids=field(array(UUID, uniqueItems=True), "Draft replacement: копировать выбранные фото последней sealed версии в указанном порядке; [] для пересъемки."))
D["Submit"] = obj(input_version_id=field(UUID, "Server: именно текущий draft, защищает от повторной отправки другого входа."))
D["ReviewWrite"] = obj(analysis_id=field(UUID, "Server: точный TaskAnalysis; чужой/старый анализ дает 409 stale_analysis."),
    state=field(enum("confirmed", "system_error"), "Учитель: согласие с ИИ либо ошибка ИИ; оба разрешают просмотр, только confirmed дает математический вклад."),
    comment=field({"type": "string", "maxLength": 4000}, "Учитель/staff: необязательный комментарий, пустая строка очищает; в summary не передается."))
D["Review"] = obj(state=field(enum("confirmed", "system_error"), "UI/summary: актуальная оценка одного анализа."),
    comment=field({"type": "string", "maxLength": 4000}, "UI/staff: сохраненный текст; не общий лог и не чат."))
D["AnalysisTarget"] = obj(analysis_id=field(UUID, "Server: пропустить только актуальный not_assessed анализ; соседние задачи не затронуты."))
D["InputTarget"] = obj(input_version_id=field(UUID, "Server: retry/skip только актуального sealed входа; история сохраняется."))
D["TaskAnalysis"] = obj(task_id=field(UUID, "Review/delete/summary: серверная идентичность только внутри поколения."),
    analysis_id=field(UUID, "Review: неизменяемый выделенный разбор; ID не равен task_id модели."),
    analysis=field({"$ref": "../../../../ai/response-schema-v1.2.json#/$defs/Task"}, "UI/summary: неизмененный frozen Task, включая свободное rule; локальный analysis.task_id не ключ БД."),
    review=field(nullable(ref("Review")), "UI/completion: null означает отсутствие явной оценки."),
    skipped=field(BOOL, "Completion: явный пропуск только not_assessed; никогда не означает математическое подтверждение."))
JOB_STATES = ("queued", "running", "retry_wait", "blocked", "unknown", "succeeded", "failed", "cancelled", "superseded")
D["Job"] = obj(id=field(UUID, "Polling/history: одна долговечная работа, несколько технических Attempt внутри."),
    kind=field(enum("page_check", "class_analytics"), "Worker/telemetry: раздельные промпты, входы и стоимость."),
    input_id=field(UUID, "Worker: InputVersion.id для checker, Snapshot.id для аналитики."),
    state=field(enum(*JOB_STATES), "UI/queue: succeeded не означает математически правильную работу."),
    reason=field(nullable(enum("funds_unavailable", "service_paused", "provider_outcome_unknown", "temporary_failure",
        "provider_rejected", "invalid_response", "input_uncheckable", "deleted", "replaced", "skipped")), "UI/staff: безопасная причина состояния; математические объяснения находятся в Report."),
    can_retry=field(BOOL, "UI: только сервер решает, доступен ли ручной retry после сверки денег/исхода."))
D["BundleReport"] = obj(id=field(UUID, "History: неизменяемый ID поколения/полного отчета."),
    input_version_id=field(UUID, "Worker/history: принадлежность результата точному sealed входу."),
    report=field({"$ref": "../../../../ai/response-schema-v1.2.json"}, "UI/history: исходный Report без редактирования, в том числе удаленные впоследствии задачи."))
D["Bundle"] = obj(id=field(UUID, "UI/worker: логическая группа совместного запроса внутри тетради."),
    draft=field(nullable(ref("InputVersion")), "Capture: единственный редактируемый draft либо null."),
    current_input=field(nullable(ref("InputVersion")), "UI/worker: текущий sealed вход; прежние версии только в history."),
    job=field(nullable(ref("Job")), "UI: актуальная работа checker; старые попытки не создают задачи."),
    result=field(nullable(ref("BundleReport")), "UI: только опубликованное актуальное поколение."),
    tasks=field(array(ref("TaskAnalysis")), "UI/completion: только активные задачи текущего поколения; tombstones и старые поколения не возвращаются здесь."),
    skipped=field(BOOL, "Completion: failed/uncheckable вход разрешен явным пропуском; не считается проверенным с нулем ошибок."))
D["Notebook"] = obj(id=field(UUID, "UI/summary: условная работа внутри проверки, не постоянный профиль ученика."),
    number=field({"type": "integer", "minimum": 1}, "UI: серверный монотонный номер внутри Check; после удаления не переиспользуется. Подпись Тетрадь N форматирует UI, переименования нет."),
    bundles=field(array(ref("Bundle")), "UI: порядок создания; фото разных комплектов модель не объединяет."))
D["Completion"] = obj(pending_jobs=field(REV, "UI: queued/running/retry_wait/blocked/unknown checker jobs; ожидание не ноль ошибок."),
    unreviewed_tasks=field(REV, "UI: assessable задачи без confirmed/system_error."),
    unresolved_tasks=field(REV, "UI: not_assessed задачи без явного skipped."),
    unresolved_bundles=field(REV, "UI: failed/uncheckable без skipped; skip не делает тетрадь полной в summary."),
    unsent_drafts=field(REV, "UI: число непустых draft, которые нужно отправить либо явно удалить."),
    can_finalize=field(BOOL, "UI: phase=review, есть хотя бы один активный sealed вход и все пять счетчиков равны 0; сервер перепроверяет транзакционно."))
D["Summary"] = obj(state=field(enum("not_started", *JOB_STATES), "UI: состояние выбранного последнего запуска, GET не создает job."),
    stale=field(BOOL, "UI: snapshot.data_revision отличается от Check.data_revision; нельзя показывать как актуальный итог."),
    snapshot_id=field(nullable(UUID), "UI/history: точный неизменяемый вход LLM."),
    job_id=field(nullable(UUID), "Polling/retry: выбранная аналитическая работа."),
    data_revision=field(nullable(REV), "History/UI: версия математически значимого основания выбранного запуска."),
    can_retry=field(BOOL, "UI: только finalized, failed, свежий snapshot и подтвержденная сервером безопасность новой попытки; blocked/unknown не дают retry."),
    can_refresh=field(BOOL, "UI: finalized+stale; прежний Job терминален либо queued/blocked гарантированно не отправлен без in-flight/unknown Attempt. Сервер перепроверяет под guard."),
    result=field(nullable({"$ref": "../../analytics/result.schema.json"}), "UI: JSON отдельного LLM; null пока валидного результата нет."))
D["CheckListItem"] = obj(id=field(UUID, "UI: перейти к сохраненной проверке."),
    title=field({"type": "string", "minLength": 1, "maxLength": 200}, "UI: название."),
    phase=field(enum("editing", "review", "finalized"), "UI: двухэтапное завершение; finalized запрещает изменение состава."),
    revision=field(REV, "Concurrency: общий guard всех изменений проверки; ETag повторяет это число."),
    created_at=field(TIME, "History: время создания UTC, порядок списка по времени/id."))
D["Check"] = obj(**D["CheckListItem"]["properties"],
    data_revision=field(REV, "Summary: меняется при изменении состава/актуального анализа/review.state, но не комментария или job-progress."),
    notebooks=field(array(ref("Notebook")), "UI/restore: весь текущий состав без удаленных объектов."),
    completion=field(ref("Completion"), "UI: производные блокеры окончательного согласия."),
    summary=field(ref("Summary"), "UI: состояние сохраненной аналитики; отдельный GET не запускает LLM."))
D["Checks"] = obj(items=field(array(ref("CheckListItem")), "UI: страницы истории в порядке created_at desc,id desc."),
    next_cursor=field(nullable(TEXT), "UI: непрозрачный серверный курсор следующей страницы, null если конец."))
D["Owner"] = obj(user_id=field(UUID, "Staff: определить владельца материала для поддержки."),
    login=field({"type": "string", "minLength": 1, "maxLength": 128}, "Staff: найти учителя по выданному логину; ФИО и контактов нет."))
D["StaffCheckListItem"] = obj(owner=ref("Owner"), check=ref("CheckListItem"))
D["StaffChecks"] = obj(items=array(ref("StaffCheckListItem")), next_cursor=nullable(TEXT))
D["StaffCheck"] = obj(owner=ref("Owner"), check=ref("Check"))
D["Mutation"] = obj(check_id=field(UUID, "Клиент: какая проверка изменилась."),
    check_revision=field(REV, "Клиент: новый If-Match; после ответа перечитать детали, включая completion."),
    entity_id=field(nullable(UUID), "Клиент: созданный/измененный/удаленный объект; null для изменения самой проверки."),
    job=field(nullable(ref("Job")), "Клиент: принятый checker/analytics job, null для изменения без обработки."))
D["HistoryRun"] = obj(job=field(ref("Job"), "Staff: job.id однозначно идентифицирует поколение, включая retry того же InputVersion."),
    result=field(nullable(ref("BundleReport")), "Staff: исходный отчет только этого поколения либо null, если ответа не было."),
    tasks=field(array(ref("TaskAnalysis")), "Staff: разборы и последние отзывы только этого поколения, включая удаленные задачи."),
    deleted_task_ids=field(array(UUID, uniqueItems=True), "Staff: tombstones этого поколения; остальные элементы tasks были активны до замещения."))
D["HistoryVersion"] = obj(input=field(ref("InputVersion"), "Staff: одна неизменяемая версия входа."),
    runs=field(array(ref("HistoryRun")), "Staff: все поколения этой версии по времени создания Job, даже при нескольких успешных retry."))
D["BundleHistory"] = obj(bundle_id=UUID, versions=array(ref("HistoryVersion")))
D["SummaryHistoryItem"] = obj(created_at=TIME, summary=ref("Summary"))
D["SummaryHistory"] = obj(items=array(ref("SummaryHistoryItem")))
D["Event"] = obj(id=field(UUID, "Ingest: дедупликация одного наблюдения, повторный ID с другим payload дает 409."),
    session_id=field(UUID, "Telemetry: клиентская вкладка/сессия наблюдений, не cookie auth."),
    occurred_at=field(TIME, "Telemetry: клиентское приблизительное время, сервер отдельно пишет received_at."),
    name=field(enum("capture_opened", "photo_selected", "result_opened", "result_closed", "app_visible", "app_hidden", "heartbeat"), "Telemetry: только клиентские наблюдения; серверные факты фиксирует сам сервер."),
    check_id=field(nullable(UUID), "Access/telemetry: контекст своей проверки, null вне проверки."),
    entity_id=field(nullable(UUID), "Telemetry: Bundle/Task ID при наблюдении; null если отсутствует."))
D["Events"] = obj(events=array(ref("Event"), minItems=1, maxItems=100))
D["EventsAccepted"] = obj(accepted_ids=field(array(UUID, uniqueItems=True), "Клиент: все надежно сохраненные ID, включая уже принятые идентичные дубли."))


def schema_ref(name):
    return {"$ref": "schemas/domain.schema.json#/$defs/" + name}


PATHS = {}
TAG_MAP = {}


def route(path, method, operation, output, request=None, status=200, mutation=False,
          roles="teacher", binary=False, upload=False, query=False):
    params = []
    import re
    for name in re.findall(r"\{([^}]+)\}", path):
        params.append({"name": name, "in": "path", "required": True, "schema": UUID})
    if query:
        params += [{"name": "cursor", "in": "query", "schema": TEXT},
                   {"name": "limit", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 30}}]
        if operation == "listStaffChecks":
            params.append({"name": "owner_login", "in": "query", "schema": {"type": "string", "minLength": 1, "maxLength": 128},
                           "description": "Точный выданный логин учителя; без отдельного каталога учителей."})
    if mutation:
        params += [{"name": "If-Match", "in": "header", "required": True,
                    "description": "Точный quoted ETag родительской Check: например, \\\"12\\\". Обязателен даже для photo upload и worker-конкурирующих операций.",
                    "schema": {"type": "string", "pattern": '^"[0-9]+"$'}},
                   {"name": "Idempotency-Key", "in": "header", "required": True,
                    "description": "UUID одного намерения. Точный повтор ищется до If-Match, возвращает исходный ответ даже после изменения revision.", "schema": UUID}]
    elif operation == "createCheck":
        params.append({"name": "Idempotency-Key", "in": "header", "required": True, "schema": UUID})
    responses = {str(status): {"description": "Успех; изменение надежно сохранено до ответа."}}
    if output:
        responses[str(status)]["content"] = {"image/jpeg" if binary else "application/json": {"schema": {"type": "string", "format": "binary"} if binary else schema_ref(output)}}
        if binary:
            responses[str(status)]["content"].update({kind: {"schema": {"type": "string", "format": "binary"}} for kind in ("image/png", "image/webp")})
    for code in (400, 401, 403, 404, 409, 413, 415, 422, 503):
        responses[str(code)] = {"description": "Безопасная ошибка; состояние не изменено.", "content": {"application/json": {"schema": schema_ref("ErrorResponse")}}}
    spec = {"operationId": operation, "tags": [roles], "summary": operation,
            "x-required-role": roles, "security": [{"sessionCookie": []}], "responses": responses}
    if params:
        spec["parameters"] = params
    if request:
        spec["requestBody"] = {"required": True, "content": {"application/json": {"schema": schema_ref(request)}}}
    if upload:
        spec["requestBody"] = {"required": True, "content": {"multipart/form-data": {"schema": obj(file={"type": "string", "format": "binary"}),
            "encoding": {"file": {"contentType": "image/jpeg, image/png, image/webp, image/heic, image/heif"}}}}}
    if operation == "login":
        spec["security"] = []
        responses[str(status)]["headers"] = {"Set-Cookie": {"description": "HttpOnly; SameSite=Lax; Path=/; Secure в HTTPS. Значение не журналируется.", "schema": TEXT}}
    if operation in ("submitBundle", "retryBundle", "finalizeCheck", "refreshSummary", "retrySummary"):
        spec["description"] = "Mutation проверяет версии/поколение под общей блокировкой Check до создания Job/outbox. Worker повторно проверяет current job/input/snapshot и отсутствие удаления до резервирования/первой возможной отправки LLM. Устаревший неотправленный snapshot не расходует деньги; HTTP GET ничего не запускает."
    if operation in ("getCheck", "getStaffCheck"):
        responses[str(status)]["headers"] = {"ETag": {"schema": {"type": "string", "pattern": '^"[0-9]+"$'}}}
    PATHS.setdefault(path, {})[method.lower()] = spec


route("/api/auth/login", "post", "login", "Session", "Login", roles="public")
route("/api/auth/session", "get", "getSession", "Session", roles="authenticated")
route("/api/auth/logout", "post", "logout", None, status=204, roles="authenticated")
route("/api/checks", "get", "listChecks", "Checks", query=True)
route("/api/checks", "post", "createCheck", "Mutation", "Title", status=201)
route("/api/checks/{check_id}", "get", "getCheck", "Check")
route("/api/checks/{check_id}", "delete", "deleteCheck", "Mutation", mutation=True)
route("/api/checks/{check_id}/notebooks", "post", "createNotebook", "Mutation", status=201, mutation=True)
route("/api/notebooks/{notebook_id}", "delete", "deleteNotebook", "Mutation", mutation=True)
route("/api/notebooks/{notebook_id}/bundles", "post", "createBundle", "Mutation", status=201, mutation=True)
route("/api/bundles/{bundle_id}", "delete", "deleteBundle", "Mutation", mutation=True)
route("/api/bundles/{bundle_id}/versions", "post", "createInputVersion", "Mutation", "VersionCreate", status=201, mutation=True)
route("/api/input-versions/{input_version_id}", "patch", "reorderPhotos", "Mutation", "PhotoOrder", mutation=True)
route("/api/input-versions/{input_version_id}", "delete", "discardDraft", "Mutation", mutation=True)
route("/api/input-versions/{input_version_id}/photos", "post", "uploadPhoto", "Mutation", status=201, mutation=True, upload=True)
route("/api/input-versions/{input_version_id}/photos/{photo_id}", "delete", "deleteDraftPhoto", "Mutation", mutation=True)
route("/api/assets/{photo_id}", "get", "getPhoto", "Photo", roles="owner_or_staff", binary=True)
route("/api/bundles/{bundle_id}/submit", "post", "submitBundle", "Mutation", "Submit", status=202, mutation=True)
route("/api/bundles/{bundle_id}/retry", "post", "retryBundle", "Mutation", "InputTarget", status=202, mutation=True)
route("/api/bundles/{bundle_id}/skip", "post", "skipBundle", "Mutation", "InputTarget", mutation=True)
route("/api/bundles/{bundle_id}/history", "get", "getBundleHistory", "BundleHistory", roles="staff")
route("/api/tasks/{task_id}", "delete", "deleteTask", "Mutation", mutation=True)
route("/api/tasks/{task_id}/review", "put", "saveReview", "Mutation", "ReviewWrite", mutation=True)
route("/api/tasks/{task_id}/skip", "post", "skipTask", "Mutation", "AnalysisTarget", mutation=True)
route("/api/jobs/{job_id}", "get", "getJob", "Job", roles="owner_or_staff")
route("/api/checks/{check_id}/begin-completion", "post", "beginCompletion", "Mutation", mutation=True)
route("/api/checks/{check_id}/finalize", "post", "finalizeCheck", "Mutation", status=202, mutation=True)
route("/api/checks/{check_id}/summary", "get", "getSummary", "Summary")
route("/api/checks/{check_id}/summary/history", "get", "getSummaryHistory", "SummaryHistory", roles="staff")
route("/api/checks/{check_id}/summary/refresh", "post", "refreshSummary", "Mutation", status=202, mutation=True)
route("/api/checks/{check_id}/summary/retry", "post", "retrySummary", "Mutation", status=202, mutation=True)
route("/api/staff/checks", "get", "listStaffChecks", "StaffChecks", roles="staff", query=True)
route("/api/staff/checks/{check_id}", "get", "getStaffCheck", "StaffCheck", roles="staff")
route("/api/events", "post", "ingestEvents", "EventsAccepted", "Events", status=202, roles="authenticated")


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def documents():
    return {"schemas/domain.schema.json": {"$schema": SCHEMA, "$id": "domain.schema.json", "$defs": D},
            "openapi.json": {"openapi": "3.1.0", "info": {"title": "SmartNote Pilot API", "version": "1.0.0",
        "description": "Замороженный минимальный HTTP-контракт независимой реализации. Приложение еще не реализовано."},
        "servers": [{"url": "http://localhost:8000"}], "paths": PATHS,
        "components": {"securitySchemes": {"sessionCookie": {"type": "apiKey", "in": "cookie", "name": "smartnote_session"}}}}}


def render_types():
    frozen = json.loads((ROOT.parents[2] / "ai/response-schema-v1.2.json").read_text(encoding="utf-8"))
    analytics = json.loads((ROOT.parent / "analytics/result.schema.json").read_text(encoding="utf-8"))
    definitions = {"Checker" + name: schema for name, schema in frozen["$defs"].items()}
    definitions["CheckerReport"] = {k: v for k, v in frozen.items() if k != "$defs"}
    definitions["ClassSummary"] = analytics
    definitions.update(D)

    def target(reference, owner):
        if reference.endswith("/response-schema-v1.2.json"):
            return "CheckerReport"
        if reference.endswith("/analytics/result.schema.json"):
            return "ClassSummary"
        if "response-schema-v1.2.json#/$defs/" in reference:
            return "Checker" + reference.rsplit("/", 1)[-1]
        name = reference.rsplit("/", 1)[-1]
        return "Checker" + name if owner.startswith("Checker") else name

    def ts(schema, owner):
        if "$ref" in schema:
            return target(schema["$ref"], owner)
        if "anyOf" in schema:
            return " | ".join(ts(value, owner) for value in schema["anyOf"])
        if "const" in schema:
            return json.dumps(schema["const"], ensure_ascii=False)
        if "enum" in schema:
            return " | ".join(json.dumps(value, ensure_ascii=False) for value in schema["enum"])
        kind = schema.get("type")
        if isinstance(kind, list):
            return " | ".join(ts({**schema, "type": item}, owner) for item in kind)
        if kind == "array":
            return "Array<" + ts(schema["items"], owner) + ">"
        if kind == "object":
            required = schema.get("required", [])
            return "{ " + "; ".join(key + ("" if key in required else "?") + ": " + ts(value, owner) for key, value in schema["properties"].items()) + " }"
        return {"integer": "number", "number": "number", "string": "string", "boolean": "boolean", "null": "null"}[kind]

    python_defs = {}

    def py(schema, owner, field_name=""):
        if "$ref" in schema:
            return target(schema["$ref"], owner)
        if "anyOf" in schema:
            variants = schema["anyOf"]
            if len(variants) == 2 and variants[1].get("type") == "null":
                return "Optional[" + py(variants[0], owner, field_name) + "]"
            return "Union[" + ", ".join(py(value, owner, field_name) for value in variants) + "]"
        if "const" in schema:
            return "Literal[" + repr(schema["const"]) + "]"
        if "enum" in schema:
            return "Literal[" + ", ".join(repr(value) for value in schema["enum"]) + "]"
        kind = schema.get("type")
        if isinstance(kind, list):
            return "Union[" + ", ".join(py({**schema, "type": item}, owner, field_name) for item in kind) + "]"
        if kind == "array":
            return "list[" + py(schema["items"], owner, field_name + "Item") + "]"
        if kind == "object":
            name = owner + "".join(part.capitalize() for part in field_name.split("_"))
            if name not in python_defs:
                python_defs[name] = None
                python_defs[name] = "class " + name + "(TypedDict):\n" + "\n".join("    " + key + ": " + py(value, name, key) for key, value in schema["properties"].items())
            return name
        return {"integer": "int", "number": "float", "string": "str", "boolean": "bool", "null": "None"}[kind]

    ts_lines = ["// Generated by build_contract.py. JSON Schema remains runtime authority."]
    for name, schema in definitions.items():
        ts_lines.append("export type " + name + " = " + ts(schema, name) + ";")
        py(schema, name)
    py_lines = ['"""Generated portable DTO types; validate all untrusted data with JSON Schema."""',
                "from __future__ import annotations", "from typing import Literal, Optional, TypedDict, Union", ""]
    py_lines.extend(python_defs.values())
    return {"contracts.ts": "\n\n".join(ts_lines) + "\n", "contracts.py": "\n\n".join(py_lines) + "\n"}


def generated_artifacts():
    artifacts = {name: json.dumps(value, ensure_ascii=False, indent=2) + "\n" for name, value in documents().items()}
    artifacts.update(render_types())
    return artifacts


def check_generated():
    for name, expected in generated_artifacts().items():
        path = ROOT / name
        assert path.is_file() and path.read_text(encoding="utf-8") == expected, "Generated artifact drift: " + name


if __name__ == "__main__":
    if "--check" in sys.argv:
        check_generated()
        print("PASS generated OpenAPI, schemas and portable Python/TypeScript types")
    else:
        for name, content in generated_artifacts().items():
            path = ROOT / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        print("Wrote OpenAPI 3.1, domain schema, portable Python and TypeScript types")
