from fastapi import APIRouter

from app.api.v1 import (
    analysis,
    applications,
    auth,
    enterprises,
    evidence_growth,
    health,
    jobs,
    mcp_tools,
    notifications,
    portfolio,
    users,
    visual,
)

router = APIRouter()
router.include_router(health.router)
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(enterprises.router, prefix="/enterprises", tags=["enterprises"])
router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
router.include_router(portfolio.router, tags=["portfolio"])
router.include_router(analysis.router, tags=["analysis"])
router.include_router(applications.router, tags=["applications"])
router.include_router(evidence_growth.router, tags=["evidence-growth"])
router.include_router(visual.router, tags=["visual"])

router.include_router(mcp_tools.router)

router.include_router(notifications.router, tags=["notifications"])
