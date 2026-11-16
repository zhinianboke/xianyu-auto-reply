"""
认证API路由

功能：
1. 用户登录（用户名/邮箱+密码）
2. 令牌验证
3. 用户注册
4. 用户登出
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from loguru import logger
from app.services.login_flow_service import perform_login
from common.services.auth_rate_limit_service import AuthRateLimitRejected, check_registration_limit
from common.db.session_recovery import rollback_session
from common.services.email_domain_policy import EmailDomainRejected, enforce_email_domain
from common.services.email_verification_code_service import check_email_code
from common.services.registration_policy import get_registration_rejection_message
from app.core.security import decode_token, get_password_hash
from common.models.user import User, UserRole, UserStatus
from common.schemas.auth import LoginRequest, LoginResponse, VerifyResponse
from common.schemas.common import ApiResponse
from common.schemas.user import UserCreate
from app.services.auth import AuthService
from app.services.system_setting_service import SystemSettingService
from app.services.user_service import UserService
from app.services.user_login_log_service import UserLoginLogService
from common.utils.http_utils import get_client_ip

router = APIRouter(tags=["auth"])

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
    # 注册尝试先计数；后缀或开关拒绝也占用额度，且不能消费旧验证码。
    try:
        await check_registration_limit(get_client_ip(request), payload.email)
        await enforce_email_domain(setting_service.session, payload.email)
    except (EmailDomainRejected, AuthRateLimitRejected) as exc:
        return ApiResponse(success=False, code=exc.code, message=str(exc))
    except Exception as exc:
        logger.opt(exception=exc).error("注册策略检查失败：email={}", payload.email)
        await rollback_session(setting_service.session, operation="注册策略检查")
        return ApiResponse(success=False, code=50001, message="注册校验暂不可用，请稍后重试")

    # 在消费验证码和创建账号前重新读取开关，旧验证码不能绕过已关闭的注册。
    settings = await setting_service.list_settings()
    rejection_message = get_registration_rejection_message(settings)
    if rejection_message:
        return ApiResponse(
            success=False,
            code=status.HTTP_403_FORBIDDEN,
            message=rejection_message,
        )

    # 验证邮箱验证码
    if payload.email and payload.verification_code:
        code_valid, code_msg = check_email_code(payload.email, payload.verification_code, "register")
        if not code_valid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=code_msg)
    elif payload.email:
        # 有邮箱但没有验证码
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请输入邮箱验证码")
    
    # 检查用户名是否已存在
    existing = await user_service.get_by_username(payload.username)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已被注册")
    
    # 检查邮箱是否已存在
    if payload.email:
        existing_email = await user_service.get_by_email(payload.email)
        if existing_email:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邮箱已被注册")
    
    await user_service.create(payload)
    return ApiResponse(success=True, message="注册成功")


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
