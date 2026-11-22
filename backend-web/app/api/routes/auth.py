"""
认证API路由

功能：
1. 用户登录（用户名/邮箱+密码）
2. 令牌验证
3. 用户注册
4. 用户登出
"""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.security import decode_token, get_password_hash
from app.services.auth import AuthService
from app.services.login_flow_service import perform_login
from app.services.registration_flow_service import perform_registration
from app.services.system_setting_service import SystemSettingService
from app.services.user_login_log_service import UserLoginLogService
from app.services.user_service import UserService
from common.models.user import User, UserRole, UserStatus
from common.schemas.auth import LoginRequest, LoginResponse, VerifyResponse
from common.schemas.common import ApiResponse
from common.schemas.user import UserCreate
from common.services.auth_request_validation import AuthenticationAPIRoute
from common.services.email_verification_code_service import check_email_code
from common.utils.http_utils import get_client_ip

router = APIRouter(tags=["auth"], route_class=AuthenticationAPIRoute)

class ResetPasswordRequest(BaseModel):
    """重置密码请求"""
    email: str
    verification_code: str
    new_password: str


@router.post("/login", response_model=LoginResponse)
async def login_user(
    payload: LoginRequest,
    request: Request,
    auth_service: AuthService = Depends(deps.get_auth_service),
    session: AsyncSession = Depends(deps.get_db_session),
    login_log_service: UserLoginLogService = Depends(deps.get_user_login_log_service),
) -> LoginResponse:
    """调用统一登录流程，先校验后缀与限流，再认证并提交审计日志。"""
    return await perform_login(payload, get_client_ip(request), auth_service, session, login_log_service)


@router.get("/verify", response_model=VerifyResponse)
async def verify_token(
    request: Request,
    session: AsyncSession = Depends(deps.get_db_session),
) -> VerifyResponse:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return VerifyResponse(authenticated=False)

    token = auth_header.split(" ", 1)[1]
    try:
        payload = decode_token(token)
    except ValueError:
        return VerifyResponse(authenticated=False)

    sub = payload.get("sub")
    if not sub:
        return VerifyResponse(authenticated=False)

    user = await session.get(User, int(sub))
    if not user or user.status != UserStatus.ACTIVE:
        return VerifyResponse(authenticated=False)

    return VerifyResponse(
        authenticated=True,
        user_id=user.id,
        username=user.username,
        is_admin=user.role == UserRole.ADMIN,
        account_limit=user.account_limit,
    )


@router.post("/logout", response_model=ApiResponse)
async def logout_user() -> ApiResponse:
    return ApiResponse(success=True, message="已退出登录")


@router.post("/refresh", response_model=LoginResponse)
async def refresh_token(
    request: Request,
    session: AsyncSession = Depends(deps.get_db_session),
    auth_service: AuthService = Depends(deps.get_auth_service),
) -> LoginResponse:
    """刷新访问令牌"""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return LoginResponse(success=False, message="未提供刷新令牌")

    refresh_token = auth_header.split(" ", 1)[1]
    try:
        payload = decode_token(refresh_token)
    except ValueError:
        return LoginResponse(success=False, message="刷新令牌无效")

    # 验证是否为refresh token
    if payload.get("type") != "refresh":
        return LoginResponse(success=False, message="令牌类型错误")

    sub = payload.get("sub")
    if not sub:
        return LoginResponse(success=False, message="刷新令牌无效")

    user = await session.get(User, int(sub))
    if not user or user.status != UserStatus.ACTIVE:
        return LoginResponse(success=False, message="用户不存在或已被禁用")

    # 生成新的access token和refresh token
    return LoginResponse(
        success=True,
        message="令牌刷新成功",
        token=auth_service.create_access_token(user),
        refresh_token=auth_service.create_refresh_token(user),
        user_id=user.id,
        username=user.username,
        is_admin=user.role == UserRole.ADMIN,
        account_limit=user.account_limit,
    )


@router.get("/check-default-password", response_model=ApiResponse)
async def check_default_password(
    current_user: User = Depends(deps.get_current_admin_user),
    auth_service: AuthService = Depends(deps.get_auth_service),
) -> ApiResponse:
    """
    检查管理员密码是否为默认值（admin123）
    仅管理员可调用，返回 data.is_default 表示是否为默认密码
    """
    is_default = auth_service._verify_user_password(current_user, "admin123")
    return ApiResponse(
        success=True,
        message="检查完成",
        data={"is_default": is_default},
    )


@router.post("/register", response_model=ApiResponse)
async def register_user(
    payload: UserCreate,
    request: Request,
    user_service: UserService = Depends(deps.get_user_service),
    setting_service: SystemSettingService = Depends(deps.get_system_setting_service),
) -> ApiResponse:
    """按当前注册开关与邮箱验证码创建用户。

    Args:
        payload: 用户注册资料与邮箱验证码。
        request: 请求对象，用于公共客户端 IP 获取与注册限流。
        user_service: 用户查询与创建服务。
        setting_service: 读取当前注册开关的设置服务。
    Returns:
        统一业务响应，关闭注册时不消费验证码或创建账号。
    """
    request.state.registration_started = True
    return await perform_registration(payload, get_client_ip(request), user_service, setting_service)


@router.post("/reset-password", response_model=ApiResponse)
async def reset_password(
    payload: ResetPasswordRequest,
    session: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """重置密码（通过邮箱验证码）

    业务错误统一以 HTTP 200 + success=False 返回，由前端展示具体消息。
    """
    # 先校验新密码长度，避免在密码不合规时提前消费掉验证码
    if len(payload.new_password) < 6:
        return ApiResponse(success=False, message="新密码长度不能少于6位")

    # 验证邮箱验证码（校验成功后会消费该验证码）
    code_valid, code_msg = check_email_code(payload.email, payload.verification_code, "reset_password")
    if not code_valid:
        return ApiResponse(success=False, message=code_msg)

    # 查找用户
    user_service = UserService(session)
    user = await user_service.get_by_email(payload.email)
    if not user:
        return ApiResponse(success=False, message="该邮箱未注册")

    # 更新密码（直接操作 ORM 对象后 commit）
    user.password_hash = get_password_hash(payload.new_password)
    await session.commit()

    return ApiResponse(success=True, message="密码重置成功")
