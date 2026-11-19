from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile
from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse

from pilot.contracts import BundleHistory, Check, Checks, Mutation
from pilot.domain import mutations, queries, storage
from pilot.domain.access import Actor, get_services, require_actor
from pilot.domain.errors import DomainError
from pilot.domain.revision import MutationContext
from pilot.domain.services import Services
from pilot.services.application import existing_mutation, new_check_mutation, request_id
from pilot.services.payloads import PhotoOrderBody, ReviewBody, TitleBody, VersionCreateBody

router = APIRouter()
Service = Annotated[Services, Depends(get_services)]
CurrentActor = Annotated[Actor, Depends(require_actor)]
Context = Annotated[MutationContext, Depends(existing_mutation)]


@router.get("/checks", operation_id="listChecks")
async def list_checks(
    request: Request, svc: Service, actor: CurrentActor,
    cursor: str | None = None, limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> Checks:
    return await queries.list_checks(svc, actor, cursor=cursor, limit=limit, request_id=request_id(request))


@router.post("/checks", operation_id="createCheck", status_code=201)
async def create_check(
    payload: TitleBody, svc: Service, ctx: Annotated[MutationContext, Depends(new_check_mutation)],
) -> Mutation:
    title = payload["title"].strip()
    if not title:
        raise DomainError(422, "invalid_input", "Введите название проверки.")
    return await mutations.create_check(svc, ctx, {"title": title})


@router.get("/checks/{check_id}", operation_id="getCheck")
async def get_check(check_id: UUID, request: Request, response: Response, svc: Service, actor: CurrentActor) -> Check:
    check = await queries.get_check(svc, actor, check_id, request_id=request_id(request))
    response.headers["ETag"] = f'"{check["revision"]}"'
    response.headers["Cache-Control"] = "private, no-store"
    return check


@router.delete("/checks/{check_id}", operation_id="deleteCheck")
async def delete_check(check_id: UUID, svc: Service, ctx: Context) -> Mutation:
    return await mutations.delete_check(svc, ctx, check_id)


@router.post("/checks/{check_id}/notebooks", operation_id="createNotebook", status_code=201)
async def create_notebook(check_id: UUID, svc: Service, ctx: Context) -> Mutation:
    return await mutations.create_notebook(svc, ctx, check_id)


@router.delete("/notebooks/{notebook_id}", operation_id="deleteNotebook")
async def delete_notebook(notebook_id: UUID, svc: Service, ctx: Context) -> Mutation:
    return await mutations.delete_notebook(svc, ctx, notebook_id)


@router.post("/notebooks/{notebook_id}/bundles", operation_id="createBundle", status_code=201)
async def create_bundle(notebook_id: UUID, svc: Service, ctx: Context) -> Mutation:
    return await mutations.create_bundle(svc, ctx, notebook_id)


@router.delete("/bundles/{bundle_id}", operation_id="deleteBundle")
async def delete_bundle(bundle_id: UUID, svc: Service, ctx: Context) -> Mutation:
    return await mutations.delete_bundle(svc, ctx, bundle_id)


@router.get("/bundles/{bundle_id}/history", operation_id="getBundleHistory")
async def get_bundle_history(bundle_id: UUID, request: Request, svc: Service, actor: CurrentActor) -> BundleHistory:
    if actor.role != "staff":
        raise DomainError(403, "forbidden", "Недостаточно прав.")
    return await queries.get_bundle_history(svc, actor, bundle_id, request_id=request_id(request))


@router.post("/bundles/{bundle_id}/versions", operation_id="createInputVersion", status_code=201)
async def create_input_version(bundle_id: UUID, payload: VersionCreateBody, svc: Service, ctx: Context) -> Mutation:
    return await mutations.create_input_version(svc, ctx, bundle_id, payload)


@router.patch("/input-versions/{input_version_id}", operation_id="reorderPhotos")
async def reorder_photos(input_version_id: UUID, payload: PhotoOrderBody, svc: Service, ctx: Context) -> Mutation:
    return await mutations.reorder_photos(svc, ctx, input_version_id, payload)


@router.delete("/input-versions/{input_version_id}", operation_id="discardDraft")
async def discard_draft(input_version_id: UUID, svc: Service, ctx: Context) -> Mutation:
    return await mutations.discard_draft(svc, ctx, input_version_id)


@router.post("/input-versions/{input_version_id}/photos", operation_id="uploadPhoto", status_code=201)
async def upload_photo(
    input_version_id: UUID, request: Request, svc: Service, ctx: Context, file: Annotated[UploadFile, File()],
) -> Mutation:
    if len((await request.form()).multi_items()) != 1:
        raise DomainError(422, "invalid_input", "Добавьте один файл.")
    prepared = await run_in_threadpool(storage.prepare_photo, file.file, file.content_type or "")
    return await mutations.upload_photo(svc, ctx, input_version_id, prepared)


@router.delete("/input-versions/{input_version_id}/photos/{photo_id}", operation_id="deleteDraftPhoto")
async def delete_draft_photo(input_version_id: UUID, photo_id: UUID, svc: Service, ctx: Context) -> Mutation:
    return await mutations.delete_draft_photo(svc, ctx, input_version_id, photo_id)


@router.get("/assets/{photo_id}", operation_id="getPhoto", response_class=FileResponse)
async def get_photo(photo_id: UUID, request: Request, svc: Service, actor: CurrentActor) -> FileResponse:
    photo = await queries.open_photo(svc, actor, photo_id, request_id=request_id(request))
    return FileResponse(
        photo.path,
        media_type=photo.media_type,
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.put("/tasks/{task_id}/review", operation_id="saveReview")
async def save_review(task_id: UUID, payload: ReviewBody, svc: Service, ctx: Context) -> Mutation:
    return await mutations.save_review(svc, ctx, task_id, payload)


@router.delete("/tasks/{task_id}", operation_id="deleteTask")
async def delete_task(task_id: UUID, svc: Service, ctx: Context) -> Mutation:
    return await mutations.delete_task(svc, ctx, task_id)
