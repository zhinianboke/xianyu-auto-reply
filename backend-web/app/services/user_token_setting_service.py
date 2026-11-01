"""
个人远程 Token 配置服务。

功能：
1. 按当前用户读取远程 URL 和秘钥
2. 校验后在同一事务中保存两个设置，避免只保存其中一项
3. 两项同时留空时恢复使用系统级 Token 配置
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.user import User
from common.models.user_setting import UserSetting
from common.schemas.common import ApiResponse
from common.schemas.system_setting import RemoteTokenTestRequest
from common.services.remote_token_api import (
    TOKEN_REMOTE_SECRET_KEY_SETTING_KEY,
    TOKEN_REMOTE_URL_SETTING_KEY,
    validate_remote_token_settings,
)


class UserTokenSettingService:
    """管理用户设置表中的 Token 远程配置。"""

    def __init__(self, session: AsyncSession, owner_id: int) -> None:
        """接收请求会话及认证用户 ID，不创建额外连接池。"""
        self.session = session
        self.owner_id = owner_id

    async def _rollback_safely(self) -> None:
        """尽力回滚失败事务，避免回滚异常覆盖原始错误。"""
        try:
            await self.session.rollback()
        except Exception as exc:  # noqa: BLE001
            logger.opt(exception=exc).error(
                "个人Token配置事务回滚失败：owner_id={} exception_type={} exception={}",
                self.owner_id,
                type(exc).__name__,
                exc,
            )

    async def _load_settings(self, *, for_update: bool = False) -> dict[str, UserSetting]:
        """查询当前用户设置；保存时使用当前读，避免认证查询的旧快照导致并发重复插入。"""
        statement = select(UserSetting).where(
            UserSetting.user_id == self.owner_id,
            UserSetting.key.in_((
                TOKEN_REMOTE_URL_SETTING_KEY,
                TOKEN_REMOTE_SECRET_KEY_SETTING_KEY,
            )),
        ).order_by(UserSetting.id)
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return {setting.key: setting for setting in result.scalars().all()}

    async def get_settings(self) -> ApiResponse:
        """读取个人配置；连接失效时回滚后重试一次，失败则由统一异常处理展示。"""
        for attempt in range(2):
            try:
                settings = await self._load_settings()
                url = settings.get(TOKEN_REMOTE_URL_SETTING_KEY)
                secret = settings.get(TOKEN_REMOTE_SECRET_KEY_SETTING_KEY)
                logger.info("读取个人Token远程配置成功：owner_id={}", self.owner_id)
                return ApiResponse(success=True, message="配置读取成功", data={
                    "remote_url": url.value if url else "",
                    "remote_secret_key": secret.value if secret else "",
                })
            except DBAPIError as exc:
                await self._rollback_safely()
                logger.opt(exception=exc).error(
                    "读取个人Token远程配置失败：owner_id={} attempt={}", self.owner_id, attempt + 1,
                )
                if exc.connection_invalidated and not attempt:
                    continue
                return ApiResponse(success=False, code=40001, message="个人Token远程配置读取失败，请稍后重试")
            except Exception as exc:  # noqa: BLE001
                await self._rollback_safely()
                logger.opt(exception=exc).error(
                    "读取个人Token远程配置异常：owner_id={} exception_type={} exception={}",
                    self.owner_id,
                    type(exc).__name__,
                    exc,
                )
                return ApiResponse(success=False, code=40001, message="个人Token远程配置读取失败，请稍后重试")
        return ApiResponse(success=False, code=40001, message="个人Token远程配置读取失败，请稍后重试")

    async def save_settings(self, payload: RemoteTokenTestRequest) -> ApiResponse:
        """校验 URL 和秘钥，并原子保存当前用户的两个配置项。

        Args:
            payload: 待保存的远程 URL 和秘钥，保存前去除首尾空格。
        Returns:
            统一保存结果；校验失败不写入数据库。
        """
        remote_url = payload.remote_url.strip()
        secret_key = payload.remote_secret_key.strip()
        if remote_url or secret_key:
            error = validate_remote_token_settings(remote_url, secret_key)
            if error:
                return ApiResponse(success=False, code=40001, message=error)

        for attempt in range(2):
            try:
                # 锁定当前用户，防止首次保存时并发创建重复设置。
                await self.session.execute(
                    select(User.id).where(User.id == self.owner_id).with_for_update()
                )
                settings = await self._load_settings(for_update=True)
                for key, value, description in (
                    (TOKEN_REMOTE_URL_SETTING_KEY, remote_url, "个人Token远程URL"),
                    (TOKEN_REMOTE_SECRET_KEY_SETTING_KEY, secret_key, "个人Token远程秘钥"),
                ):
                    setting = settings.get(key)
                    if setting is None:
                        self.session.add(UserSetting(
                            user_id=self.owner_id, key=key, value=value, description=description,
                        ))
                    else:
                        setting.value = value
                        setting.description = description
                await self.session.commit()
                cleared = not remote_url and not secret_key
                logger.info(
                    "保存个人Token远程配置成功：owner_id={} cleared={}",
                    self.owner_id,
                    cleared,
                )
                return ApiResponse(success=True, message=(
                    "个人Token远程配置已清空，将使用系统级配置"
                    if cleared else "Token远程配置已保存"
                ), data={
                    "remote_url": remote_url,
                    "remote_secret_key": secret_key,
                })
            except DBAPIError as exc:
                await self._rollback_safely()
                logger.opt(exception=exc).error(
                    "保存个人Token远程配置失败：owner_id={} attempt={}", self.owner_id, attempt + 1,
                )
                if exc.connection_invalidated and not attempt:
                    continue
                return ApiResponse(success=False, code=40001, message="个人Token远程配置保存失败，请稍后重试")
            except Exception as exc:  # noqa: BLE001 - 任意写库异常都必须回滚并转成用户可见业务错误。
                await self._rollback_safely()
                logger.opt(exception=exc).error(
                    "保存个人Token远程配置异常：owner_id={} exception_type={} exception={}",
                    self.owner_id,
                    type(exc).__name__,
                    exc,
                )
                return ApiResponse(success=False, code=40001, message="个人Token远程配置保存失败，请稍后重试")
        return ApiResponse(success=False, code=40001, message="个人Token远程配置保存失败，请稍后重试")
