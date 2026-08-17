"""
商品监控分类服务层

功能：
1. 分类的增删改查
2. 名称唯一性校验（分类名称全局唯一，跨用户不可重名）
3. 删除前检查关联数据（监控任务、兜底账号配置）：普通用户仅校验本人数据，管理员校验全量
4. 支持多用户数据隔离与管理员权限：普通用户仅可见/操作自己的分类，管理员可见/操作全部
"""
from __future__ import annotations

from typing import Dict, List, Optional

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.listing_monitor_category import ListingMonitorCategory
from common.models.listing_monitor_task import ListingMonitorTask
from common.models.collect_fallback_account import CollectFallbackAccount
from common.models.order_fallback_account import OrderFallbackAccount
from common.models.user import User, UserRole
from common.utils.time_utils import safe_isoformat


class ListingMonitorCategoryService:
    """商品监控分类服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _is_admin_user(self, user_id: int) -> bool:
        """检查用户是否为管理员"""
        user = await self.session.get(User, user_id)
        return user is not None and user.role == UserRole.ADMIN

    async def list_categories(
        self, owner_id: Optional[int], include_deleted: bool = False
    ) -> List[Dict]:
        """查询分类列表（按用户隔离）

        普通用户只能看到自己创建的分类，管理员可看到全部分类。
        分类名称仍保持全局唯一（见 _check_name_duplicate），便于按名称跨用户匹配兜底配置。

        Args:
            owner_id: 数据隔离范围。None 表示管理员（查看全部）；
                非 None 时按 owner_id 过滤（仅查看该用户的分类）
            include_deleted: 是否包含已删除的分类

        Returns:
            分类列表，按创建时间倒序
        """
        conditions = []
        if not include_deleted:
            conditions.append(ListingMonitorCategory.is_deleted.is_(False))
        # owner_id=None 为管理员哨兵，不加 owner 过滤；非 None 时仅看本人分类
        if owner_id is not None:
            conditions.append(ListingMonitorCategory.owner_id == owner_id)

        stmt = (
            select(ListingMonitorCategory)
            .where(*conditions)
            .order_by(ListingMonitorCategory.created_at.desc())
        )
        result = await self.session.execute(stmt)
        categories = result.scalars().all()

        return [
            {
                "id": cat.id,
                "owner_id": cat.owner_id,
                "name": cat.name,
                "is_deleted": cat.is_deleted,
                "created_at": safe_isoformat(cat.created_at),
                "updated_at": safe_isoformat(cat.updated_at),
            }
            for cat in categories
        ]

    async def get_category(
        self, category_id: int, owner_id: Optional[int]
    ) -> Optional[Dict]:
        """查询单个分类详情（按用户隔离）

        普通用户只能查看自己创建的分类，管理员可查看全部。

        Args:
            category_id: 分类ID
            owner_id: 数据隔离范围。None 表示管理员（不限制 owner）；
                非 None 时仅可查看该用户的分类

        Returns:
            分类详情，不存在或无权限时返回 None
        """
        conditions = [ListingMonitorCategory.id == category_id]
        # owner_id=None 为管理员哨兵，不加 owner 过滤
        if owner_id is not None:
            conditions.append(ListingMonitorCategory.owner_id == owner_id)
        stmt = select(ListingMonitorCategory).where(*conditions)
        result = await self.session.execute(stmt)
        category = result.scalar_one_or_none()

        if not category:
            return None

        return {
            "id": category.id,
            "owner_id": category.owner_id,
            "name": category.name,
            "is_deleted": category.is_deleted,
            "created_at": safe_isoformat(category.created_at),
            "updated_at": safe_isoformat(category.updated_at),
        }

    async def _check_name_duplicate(
        self, name: str, exclude_id: Optional[int] = None
    ) -> bool:
        """检查分类名称是否重复（全局唯一）

        分类名称全局唯一：跨所有用户不允许重名，便于按名称跨用户匹配兜底配置。

        Args:
            name: 分类名称
            exclude_id: 排除的分类ID（用于编辑时排除自身）

        Returns:
            True 表示重复，False 表示不重复
        """
        conditions = [
            ListingMonitorCategory.name == name,
            ListingMonitorCategory.is_deleted.is_(False),
        ]
        if exclude_id is not None:
            conditions.append(ListingMonitorCategory.id != exclude_id)

        stmt = select(func.count()).select_from(ListingMonitorCategory).where(*conditions)
        result = await self.session.execute(stmt)
        count = result.scalar()
        return count > 0

    async def create_category(self, owner_id: int, name: str) -> Dict:
        """创建分类

        Args:
            owner_id: 当前用户ID
            name: 分类名称

        Returns:
            创建的分类详情

        Raises:
            ValueError: 名称为空或重复
        """
        name = name.strip()
        if not name:
            raise ValueError("分类名称不能为空")

        if await self._check_name_duplicate(name):
            raise ValueError(f"分类名称「{name}」已存在")

        category = ListingMonitorCategory(
            owner_id=owner_id,
            name=name,
        )
        self.session.add(category)
        await self.session.flush()
        await self.session.refresh(category)

        return {
            "id": category.id,
            "owner_id": category.owner_id,
            "name": category.name,
            "is_deleted": category.is_deleted,
            "created_at": safe_isoformat(category.created_at),
            "updated_at": safe_isoformat(category.updated_at),
        }

    async def update_category(
        self, category_id: int, owner_id: int, name: str
    ) -> Dict:
        """修改分类名称

        Args:
            category_id: 分类ID
            owner_id: 当前用户ID
            name: 新分类名称

        Returns:
            更新后的分类详情

        Raises:
            ValueError: 名称为空、重复或分类不存在/无权限
        """
        is_admin = await self._is_admin_user(owner_id)
        stmt = select(ListingMonitorCategory).where(
            ListingMonitorCategory.id == category_id,
            ListingMonitorCategory.is_deleted.is_(False),
        )
        result = await self.session.execute(stmt)
        category = result.scalar_one_or_none()

        if not category:
            raise ValueError("分类不存在")
        # 仅创建人或管理员可修改
        if not is_admin and category.owner_id != owner_id:
            raise ValueError("无权限修改该分类（仅创建人或管理员可操作）")

        name = name.strip()
        if not name:
            raise ValueError("分类名称不能为空")

        if await self._check_name_duplicate(name, exclude_id=category_id):
            raise ValueError(f"分类名称「{name}」已存在")

        category.name = name
        await self.session.flush()
        await self.session.refresh(category)

        return {
            "id": category.id,
            "owner_id": category.owner_id,
            "name": category.name,
            "is_deleted": category.is_deleted,
            "created_at": safe_isoformat(category.created_at),
            "updated_at": safe_isoformat(category.updated_at),
        }

    async def delete_category(self, category_id: int, owner_id: int) -> None:
        """软删除分类

        删除前检查是否有关联数据：
        - 该分类下是否有监控任务（未删除）
        - 该分类是否有兜底账号配置（采集/下单）

        关联数据的校验范围按角色区分：
        - 普通用户：只校验本人的关联数据。他人（含管理员）在该分类上的配置不应阻塞本人
          删除自己创建的分类——否则用户会收到"该分类下还有兜底账号配置"却在界面上
          找不到任何自己的配置。这些他人配置删除后变成悬空引用，其兜底层自然失效，
          故记录一条 warning 便于排查；
        - 管理员：校验全部用户的关联数据（管理员是全量视角，避免误删他人还在用的分类）。

        Args:
            category_id: 分类ID
            owner_id: 当前用户ID

        Raises:
            ValueError: 分类不存在、无权限或有关联数据
        """
        is_admin = await self._is_admin_user(owner_id)
        stmt = select(ListingMonitorCategory).where(
            ListingMonitorCategory.id == category_id,
            ListingMonitorCategory.is_deleted.is_(False),
        )
        result = await self.session.execute(stmt)
        category = result.scalar_one_or_none()

        if not category:
            raise ValueError("分类不存在")
        # 仅创建人或管理员可删除
        if not is_admin and category.owner_id != owner_id:
            raise ValueError("无权限删除该分类（仅创建人或管理员可操作）")

        # 关联数据校验范围：管理员校验全量，普通用户仅校验本人数据
        scope_owner_id = None if is_admin else owner_id

        # 检查是否有关联的监控任务（未删除）
        task_conditions = [
            ListingMonitorTask.category_id == category_id,
            ListingMonitorTask.is_deleted.is_(False),
        ]
        if scope_owner_id is not None:
            task_conditions.append(ListingMonitorTask.owner_id == scope_owner_id)
        task_count_stmt = (
            select(func.count()).select_from(ListingMonitorTask).where(*task_conditions)
        )
        task_count_result = await self.session.execute(task_count_stmt)
        task_count = task_count_result.scalar()
        if task_count > 0:
            raise ValueError(f"该分类下还有 {task_count} 个监控任务，请先删除或迁移任务后再删除分类")

        # 检查是否有兜底采集账号配置（仅统计未软删除的，避免历史软删配置永久挡删分类）
        collect_conditions = [
            CollectFallbackAccount.category_id == category_id,
            CollectFallbackAccount.is_deleted.is_(False),
        ]
        if scope_owner_id is not None:
            collect_conditions.append(CollectFallbackAccount.owner_id == scope_owner_id)
        collect_fallback_stmt = (
            select(func.count()).select_from(CollectFallbackAccount).where(*collect_conditions)
        )
        collect_count_result = await self.session.execute(collect_fallback_stmt)
        collect_count = collect_count_result.scalar()
        if collect_count > 0:
            raise ValueError("该分类下还有兜底采集账号配置，请先删除配置后再删除分类")

        # 检查是否有兜底下单账号配置（仅统计未软删除的，避免历史软删配置永久挡删分类）
        order_conditions = [
            OrderFallbackAccount.category_id == category_id,
            OrderFallbackAccount.is_deleted.is_(False),
        ]
        if scope_owner_id is not None:
            order_conditions.append(OrderFallbackAccount.owner_id == scope_owner_id)
        order_fallback_stmt = (
            select(func.count()).select_from(OrderFallbackAccount).where(*order_conditions)
        )
        order_count_result = await self.session.execute(order_fallback_stmt)
        order_count = order_count_result.scalar()
        if order_count > 0:
            raise ValueError("该分类下还有兜底下单账号配置，请先删除配置后再删除分类")

        # 普通用户删除自己的分类时，他人（含管理员）在该分类上的配置会变成悬空引用、
        # 其"本分类"兜底层失效，记录 warning 便于后续排查兜底为何不生效
        if scope_owner_id is not None:
            await self._warn_orphaned_references(category_id, category.name, owner_id)

        # 软删除
        category.is_deleted = True
        await self.session.flush()

    async def _warn_orphaned_references(
        self, category_id: int, category_name: str, operator_id: int
    ) -> None:
        """删除分类前，若存在他人的关联数据，记录一条 warning（不阻塞删除）。

        Args:
            category_id: 待删除的分类ID
            category_name: 分类名称（便于日志排查）
            operator_id: 操作人用户ID（其本人数据已在前面校验过）
        """
        others: List[str] = []

        task_owners = (
            await self.session.execute(
                select(ListingMonitorTask.owner_id)
                .where(
                    ListingMonitorTask.category_id == category_id,
                    ListingMonitorTask.is_deleted.is_(False),
                    ListingMonitorTask.owner_id != operator_id,
                )
                .distinct()
            )
        ).scalars().all()
        if task_owners:
            others.append(f"监控任务所属用户{sorted({oid for oid in task_owners if oid})}")

        for model, label in (
            (CollectFallbackAccount, "兜底采集账号配置"),
            (OrderFallbackAccount, "兜底下单账号配置"),
        ):
            owners = (
                await self.session.execute(
                    select(model.owner_id)
                    .where(
                        model.category_id == category_id,
                        model.is_deleted.is_(False),
                        model.owner_id != operator_id,
                    )
                    .distinct()
                )
            ).scalars().all()
            if owners:
                others.append(f"{label}所属用户{sorted(set(owners))}")

        if others:
            logger.warning(
                f"[商品监控分类] 用户{operator_id}删除分类「{category_name}」(id={category_id})，"
                f"以下他人数据将变成悬空引用（其「本分类」兜底层失效）：{'；'.join(others)}"
            )
