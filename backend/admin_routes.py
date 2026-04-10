from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from .database import QueryLog, User, get_db

admin_router = APIRouter(prefix="/api/admin", tags=["admin"])

def require_admin(user: User = Depends(get_current_user)):
    if user.tier != "clinic" and not user.is_admin:
        raise HTTPException(403, "Admin access required")
    return user

@admin_router.get("/stats")
async def admin_stats(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    # Total queries
    total_queries = await db.scalar(select(func.count()).select_from(QueryLog))
    
    # Average latency by model
    latency_by_model = await db.execute(
        select(QueryLog.llm_model, func.avg(QueryLog.latency_ms))
        .group_by(QueryLog.llm_model)
    )
    
    # Users by tier
    users_by_tier = await db.execute(
        select(User.tier, func.count()).group_by(User.tier)
    )
    
    return {
        "total_queries": total_queries,
        "latency_by_model": dict(latency_by_model),
        "users_by_tier": dict(users_by_tier),
    }