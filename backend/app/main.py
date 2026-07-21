from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    admin_admins,
    admin_ai,
    admin_auth,
    admin_cases,
    admin_content,
    admin_jurisdictions,
    admin_settings,
    admin_submissions,
    geo,
    health,
    public_intake,
    user_auth,
    user_documents,
    user_portal,
)
from app.config import settings
from app.deps import get_current_admin, get_current_user
from app.errors import register_error_handlers

app = FastAPI(title="AcciAssist API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

_admin_auth = [Depends(get_current_admin)]

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(geo.router, prefix="/api", tags=["public"])
app.include_router(public_intake.router, prefix="/api", tags=["public"])
app.include_router(user_auth.router, prefix="/api/auth", tags=["user-auth"])
app.include_router(
    user_portal.router,
    prefix="/api/me",
    tags=["user-portal"],
    dependencies=[Depends(get_current_user)],
)
app.include_router(
    user_documents.router,
    prefix="/api/me",
    tags=["user-documents"],
    dependencies=[Depends(get_current_user)],
)
app.include_router(admin_auth.router, prefix="/api/admin", tags=["admin-auth"])
app.include_router(
    admin_admins.router, prefix="/api/admin/admins", tags=["admin-admins"], dependencies=_admin_auth
)
app.include_router(
    admin_content.router, prefix="/api/admin", tags=["admin-content"], dependencies=_admin_auth
)
app.include_router(
    admin_submissions.router,
    prefix="/api/admin",
    tags=["admin-submissions"],
    dependencies=_admin_auth,
)
app.include_router(
    admin_settings.router,
    prefix="/api/admin/settings",
    tags=["admin-settings"],
    dependencies=_admin_auth,
)
app.include_router(
    admin_cases.router, prefix="/api/admin", tags=["admin-cases"], dependencies=_admin_auth
)
app.include_router(
    admin_ai.router, prefix="/api/admin/ai", tags=["admin-ai"], dependencies=_admin_auth
)
app.include_router(
    admin_jurisdictions.router,
    prefix="/api/admin/jurisdictions",
    tags=["admin-jurisdictions"],
    dependencies=_admin_auth,
)
