from fastapi import APIRouter

from pilot.routes import application, auth, events, processing

router = APIRouter()
router.include_router(auth.router)
router.include_router(application.router)
router.include_router(processing.router)
router.include_router(events.router)
# Release mounts its staff router here after B4.
