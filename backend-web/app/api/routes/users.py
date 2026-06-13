import secrets
import string

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.security import get_password_hash, verify_password
from common.models.user import User
from common.schemas.common import ApiResponse
from common.schemas.user import UserPublic, UserUpdate
from common.utils.security import generate_secret_key as _generate_secret_key
from app.services.user_service import UserService


def _generate_dock_code(length: int = 8) -> str:
    """生成随机对接码（大写字母+数字）"""
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

router = APIRouter(tags=["users"])


class ChangePasswordRequest(BaseModel):
    """修改密码请求"""
    current_password: str
    new_password: str


@router.get("/me", response_model=UserPublic)
async def read_current_user(current_user: User = Depends(deps.get_current_active_user)) -> UserPublic:
    return UserPublic.model_validate(current_user)


# 说明：用户列表查询与用户信息（角色/状态等）修改，统一收口到带管理员鉴权的
# /api/v1/admin/users 接口（见 app/api/routes/admin.py）。
# 此处不再暴露无鉴权的 GET / 与 PATCH /{user_id}，避免越权枚举用户及提权风险。


@router.post("/change-password", response_model=ApiResponse)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(deps.get_current_active_user),
    user_service: UserService = Depends(deps.get_user_service),
) -> ApiResponse:
    """修改当前用户密码"""
    # 验证当前密码
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前密码不正确")
    
    # 验证新密码长度
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="新密码长度不能少于6位")
    
    # 更新密码
    current_user.password_hash = get_password_hash(payload.new_password)
    await user_service.update(current_user, UserUpdate())
    
    return ApiResponse(success=True, message="密码修改成功")


@router.get("/dock-code")
async def get_dock_code(
    current_user: User = Depends(deps.get_current_active_user),
    user_service: UserService = Depends(deps.get_user_service),
):
    """获取当前用户的对接码，若无则自动生成"""
    if not current_user.dock_code:
        # 自动生成对接码
        for _ in range(10):  # 最多尝试10次避免冲突
            code = _generate_dock_code()
            current_user.dock_code = code
            try:
                await user_service.update(current_user, UserUpdate())
                break
            except Exception:
                current_user.dock_code = None
                continue
        else:
            raise HTTPException(status_code=500, detail="生成对接码失败，请重试")
    return {"success": True, "dock_code": current_user.dock_code}


@router.post("/dock-code/reset", response_model=ApiResponse)
async def reset_dock_code(
    current_user: User = Depends(deps.get_current_active_user),
    user_service: UserService = Depends(deps.get_user_service),
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """重置当前用户的对接码，同时清除所有绑定记录和相关对接记录"""
    from sqlalchemy import delete as sql_delete
    from common.models.dock_code_binding import DockCodeBinding
    from common.models.dock_record import DockRecord
    from common.models.card import Card

    for _ in range(10):
        code = _generate_dock_code()
        current_user.dock_code = code
        try:
            await user_service.update(current_user, UserUpdate())

            # 查出所有分销商对接该供应商卡券的一级对接记录ID
            level1_ids_stmt = (
                select(DockRecord.id)
                .join(Card, Card.id == DockRecord.card_id)
                .where(DockRecord.level == 1, Card.user_id == current_user.id)
            )
            level1_result = await session.execute(level1_ids_stmt)
            level1_ids = [row[0] for row in level1_result.all()]

            if level1_ids:
                # 先删除二级对接记录
                await session.execute(
                    sql_delete(DockRecord).where(DockRecord.parent_dock_id.in_(level1_ids))
                )
                # 再删除一级对接记录
                await session.execute(
                    sql_delete(DockRecord).where(DockRecord.id.in_(level1_ids))
                )

            # 删除所有绑定记录
            await session.execute(
                sql_delete(DockCodeBinding).where(DockCodeBinding.target_user_id == current_user.id)
            )
            await session.commit()
            return ApiResponse(success=True, message="对接码已重置，所有已绑定的分销商及对接记录已清除")
        except Exception:
            current_user.dock_code = None
            continue
    raise HTTPException(status_code=500, detail="重置对接码失败，请重试")


@router.get("/secret-key")
async def get_secret_key(
    current_user: User = Depends(deps.get_current_active_user),
    user_service: UserService = Depends(deps.get_user_service),
):
    """获取当前用户的分销秘钥，若无则自动生成（32位随机字符，全局唯一）"""
    if not current_user.secret_key:
        # 自动生成秘钥，最多尝试10次避免唯一约束冲突
        for _ in range(10):
            key = _generate_secret_key()
            current_user.secret_key = key
            try:
                await user_service.update(current_user, UserUpdate())
                break
            except Exception:
                current_user.secret_key = None
                continue
        else:
            raise HTTPException(status_code=500, detail="生成分销秘钥失败，请重试")
    return {"success": True, "secret_key": current_user.secret_key}


@router.post("/secret-key/reset", response_model=ApiResponse)
async def reset_secret_key(
    current_user: User = Depends(deps.get_current_active_user),
    user_service: UserService = Depends(deps.get_user_service),
) -> ApiResponse:
    """更换当前用户的分销秘钥，生成新的32位随机字符（全局唯一）"""
    # 最多尝试10次避免唯一约束冲突
    for _ in range(10):
        key = _generate_secret_key()
        current_user.secret_key = key
        try:
            await user_service.update(current_user, UserUpdate())
            return ApiResponse(
                success=True,
                message="分销秘钥已更换",
                data={"secret_key": key},
            )
        except Exception:
            current_user.secret_key = None
            continue
    raise HTTPException(status_code=500, detail="更换分销秘钥失败，请重试")
