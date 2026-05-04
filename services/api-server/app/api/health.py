from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health", summary="健康检查", description="返回 API 服务健康状态。")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "api-server"}
