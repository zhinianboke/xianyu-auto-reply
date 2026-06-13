"""
认证API路由

功能：
1. 用户登录（用户名/邮箱+密码）
2. 令牌验证
3. 用户注册
4. 用户登出
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.security import decode_token
from common.models.user import User, UserRole, UserStatus
from common.schemas.auth import LoginRequest, LoginResponse, VerifyResponse
from common.schemas.common import ApiResponse
from common.schemas.user import UserCreate, UserPublic
from app.services.auth import AuthService
from app.services.user_service import UserService

router = APIRouter(tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login_user(
    payload: LoginRequest,
    auth_service: AuthService = Depends(deps.get_auth_service),
    session: AsyncSession = Depends(deps.get_db_session),
) -> LoginResponse:
    user: User | None = None
    error_message: str | None = None

    # 检查是否启用了登录滑动验证码
    from app.services.system_setting_service import SystemSettingService
    setting_service = SystemSettingService(session)
    all_settings = await setting_service.list_settings()
    captcha_enabled_str = all_settings.get("login_captcha_enabled")
    captcha_enabled = captcha_enabled_str in (None, "true", "1")  # 默认开启

    # 账号密码登录和邮箱密码登录需要验证滑动验证码
    if payload.username and payload.password:
        # 账号密码登录 - 需要滑动验证（如果开启）
        if captcha_enabled:
            from app.api.routes.geetest import check_geetest_verified
            
            if not payload.geetest_challenge:
                return LoginResponse(success=False, message="请完成滑动验证")
            
            geetest_ok, geetest_msg = check_geetest_verified(payload.geetest_challenge)
            if not geetest_ok:
                return LoginResponse(success=False, message=geetest_msg)
        
        user, error_message = await auth_service.authenticate_by_username(payload.username, payload.password)
    elif payload.email and payload.password:
        # 邮箱密码登录 - 需要滑动验证（如果开启）
        if captcha_enabled:
            from app.api.routes.geetest import check_geetest_verified
            
            if not payload.geetest_challenge:
                return LoginResponse(success=False, message="请完成滑动验证")
            
            geetest_ok, geetest_msg = check_geetest_verified(payload.geetest_challenge)
            if not geetest_ok:
                return LoginResponse(success=False, message=geetest_msg)
        
        user, error_message = await auth_service.authenticate_by_email(payload.email, payload.password)
    elif payload.email and payload.verification_code:
        # 邮箱验证码登录
        from app.api.routes.captcha import check_email_code
        
        # 验证验证码
        code_valid, code_msg = check_email_code(payload.email, payload.verification_code, "login")
        if not code_valid:
            return LoginResponse(success=False, message=code_msg)
        
        # 根据邮箱查找用户
        user_service = UserService(session)
        user = await user_service.get_by_email(payload.email)
        if not user:
            return LoginResponse(success=False, message="该邮箱未注册")
    else:
        return LoginResponse(success=False, message="请提供有效的登录信息")

    if not user:
        return LoginResponse(success=False, message=error_message or "登录失败")

    if user.status != UserStatus.ACTIVE:
        return LoginResponse(success=False, message="账号已禁用，请联系管理员")

    await auth_service.mark_login(user)
    return LoginResponse(
        success=True,
        message="登录成功",
        token=auth_service.create_access_token(user),
        refresh_token=auth_service.create_refresh_token(user),
        user_id=user.id,
        username=user.username,
        is_admin=user.role == UserRole.ADMIN,
        account_limit=user.account_limit,
    )


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


@router.post("/register", response_model=ApiResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    payload: UserCreate,
    user_service: UserService = Depends(deps.get_user_service),
) -> ApiResponse:
    # 验证邮箱验证码
    if payload.email and payload.verification_code:
        from app.api.routes.captcha import check_email_code
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
