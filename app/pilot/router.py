from fastapi import APIRouter

from pilot.routes import application, auth, events, processing, staff

router = APIRouter()
router.include_router(auth.router)
router.include_router(application.router)
router.include_router(processing.router)
router.include_router(events.router)
router.include_router(staff.router)
