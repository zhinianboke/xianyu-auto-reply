"""
二级分销对接记录服务

提供二级分销相关功能：创建二级对接、开放/关闭下级对接、级联禁用、查询下级分销商等
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from common.models.dock_record import DockRecord
from common.models.card import Card
from common.models.user import User


from common.utils.time_utils import safe_isoformat
class SubDockRecordService:
    """二级分销对接记录服务类"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_sub_dock_record(
        self,
        user_id: int,
        parent_dock_id: int,
        dock_name: str,
        markup_amount: Optional[str] = None,
        remark: Optional[str] = None,
    ) -> Dict[str, Any]:
        """创建二级对接记录
        
        Args:
            user_id: 二级分销商用户ID
            parent_dock_id: 上级对接记录ID
            dock_name: 对接名称
            markup_amount: 加价金额
            remark: 备注
            
        Returns:
            {"success": bool, "message": str, "id": int|None}
        """
        # 1. 查询上级对接记录
        parent_stmt = select(DockRecord).where(DockRecord.id == parent_dock_id)
        parent_result = await self.session.execute(parent_stmt)
        parent_record = parent_result.scalar_one_or_none()
        
        if not parent_record:
            return {"success": False, "message": "上级对接记录不存在", "id": None}
        
        # 2. 检查上级是否允许下级对接
        if not parent_record.allow_sub_dock:
            return {"success": False, "message": "上级分销商未开放二级对接", "id": None}
        
        # 3. 检查上级是否已被禁用
        if not parent_record.status:
            return {"success": False, "message": "上级对接记录已被禁用", "id": None}
        
        # 4. 只允许一级分销商开放二级对接（不允许三级及以上）
        if parent_record.level != 1:
            return {"success": False, "message": "仅支持二级分销，不能对接二级分销商", "id": None}
        
        # 5. 不能对接自己
        if user_id == parent_record.user_id:
            return {"success": False, "message": "不能对接自己的记录", "id": None}
        
        # 6. 检查是否已对接过同一张卡券（通过同一个上级）
        exist_stmt = select(DockRecord).where(
            DockRecord.user_id == user_id,
            DockRecord.card_id == parent_record.card_id,
            DockRecord.parent_dock_id == parent_dock_id,
        )
        exist_result = await self.session.execute(exist_stmt)
        if exist_result.scalar_one_or_none():
            return {"success": False, "message": "已对接过该记录，不能重复对接", "id": None}
        
        # 7. 创建二级对接记录
        from app.services.dock_record_service import DockRecordService
        dock_service = DockRecordService(self.session)
        record_id = await dock_service.create_dock_record(
            user_id=user_id,
            card_id=parent_record.card_id,
            dock_name=dock_name,
            markup_amount=markup_amount,
            remark=remark,
            level=2,
            parent_dock_id=parent_dock_id,
            source_user_id=parent_record.user_id,
        )
        
        return {"success": True, "message": "二级对接成功", "id": record_id}

    async def toggle_allow_sub_dock(
        self,
        record_id: int,
        user_id: int,
        allow: bool,
    ) -> bool:
        """开放/关闭下级对接（仅一级分销商可操作自己的对接记录）
        
        Args:
            record_id: 对接记录ID
            user_id: 用户ID（权限校验）
            allow: 是否允许下级对接
            
        Returns:
            是否操作成功
        """
        stmt = select(DockRecord).where(
            DockRecord.id == record_id,
            DockRecord.user_id == user_id,
            DockRecord.level == 1,
        )
        result = await self.session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            return False
        
        record.allow_sub_dock = allow
        await self.session.commit()
        action = "开放" if allow else "关闭"
        logger.info(f"用户 {user_id} {action}对接记录 {record_id} 的下级对接")
        return True

    async def cascade_disable_sub_docks(
        self,
        parent_dock_id: int,
        disable_reason: str = "上级分销商被禁用",
    ) -> int:
        """级联禁用所有下级对接记录
        
        Args:
            parent_dock_id: 上级对接记录ID
            disable_reason: 禁用原因
            
        Returns:
            被禁用的下级记录数
        """
        stmt = select(DockRecord).where(
            DockRecord.parent_dock_id == parent_dock_id,
            DockRecord.status == True,
        )
        result = await self.session.execute(stmt)
        sub_records = result.scalars().all()
        
        count = 0
        for record in sub_records:
            record.status = False
            record.disable_reason = disable_reason
            count += 1
        
        if count > 0:
            await self.session.commit()
            logger.info(f"级联禁用上级对接 {parent_dock_id} 的 {count} 条下级对接记录")
        
        return count

    async def update_dock_record_status_with_cascade(
        self,
        record_id: int,
        owner_user_id: int,
        status: bool,
        disable_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """更新对接记录状态（带级联禁用下级）
        
        当禁用一级分销商时，级联禁用其所有二级分销商
        
        Args:
            record_id: 对接记录ID
            owner_user_id: 卡券拥有者用户ID
            status: 启用/禁用状态
            disable_reason: 禁用原因
            
        Returns:
            {"success": bool, "message": str, "cascade_count": int}
        """
        # 验证权限：卡券拥有者
        stmt = (
            select(DockRecord)
            .join(Card, DockRecord.card_id == Card.id)
            .where(
                DockRecord.id == record_id,
                Card.user_id == owner_user_id,
            )
        )
        result = await self.session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            return {"success": False, "message": "对接记录不存在或无权限", "cascade_count": 0}
        
        record.status = status
        if not status:
            record.disable_reason = disable_reason or "分销主禁用"
        else:
            record.disable_reason = None
        
        await self.session.commit()
        
        # 禁用一级分销商时，级联禁用其所有二级
        cascade_count = 0
        if not status and record.level == 1:
            cascade_count = await self.cascade_disable_sub_docks(
                parent_dock_id=record_id,
                disable_reason="上级分销商被禁用",
            )
        
        return {"success": True, "message": "更新成功", "cascade_count": cascade_count}

    async def get_dockable_sub_records_paginated(
        self,
        current_user_id: int,
        page: int = 1,
        page_size: int = 20,
        search: str = "",
    ) -> Dict[str, Any]:
        """获取可对接的一级分销商记录列表（二级分销商货源广场）
        
        查询条件：level=1, allow_sub_dock=True, status=True，排除自己的记录
        sub_dock_visibility 过滤：
        - public / NULL → 所有人可见
        - dealer_only → 仅绑定了该一级分销商对接码的用户可见
        
        Args:
            current_user_id: 当前用户ID
            page: 页码
            page_size: 每页数量
            search: 搜索关键词（匹配对接名称或卡券名称）
            
        Returns:
            分页数据字典
        """
        from sqlalchemy import and_
        from common.models.dock_code_binding import DockCodeBinding
        
        # 查出当前用户通过对接码绑定的上级分销商ID列表
        binding_stmt = (
            select(DockCodeBinding.target_user_id)
            .where(DockCodeBinding.user_id == current_user_id)
        )
        binding_result = await self.session.execute(binding_stmt)
        bound_source_ids = [row[0] for row in binding_result.all()]
        
        base_conditions = [
            DockRecord.level == 1,
            DockRecord.allow_sub_dock == True,
            DockRecord.status == True,
            DockRecord.user_id != current_user_id,
        ]
        
        # sub_dock_visibility 过滤：public/NULL 所有人可见，dealer_only 仅已绑定对接码的可见
        if bound_source_ids:
            visibility_condition = or_(
                DockRecord.sub_dock_visibility == None,
                DockRecord.sub_dock_visibility == 'public',
                and_(DockRecord.sub_dock_visibility == 'dealer_only', DockRecord.user_id.in_(bound_source_ids)),
            )
        else:
            visibility_condition = or_(
                DockRecord.sub_dock_visibility == None,
                DockRecord.sub_dock_visibility == 'public',
            )
        base_conditions.append(visibility_condition)
        
        if search:
            base_conditions.append(
                or_(
                    DockRecord.dock_name.ilike(f"%{search}%"),
                    Card.name.ilike(f"%{search}%"),
                )
            )
        
        # 查询总数
        count_stmt = (
            select(func.count(DockRecord.id))
            .join(Card, DockRecord.card_id == Card.id)
            .where(*base_conditions)
        )
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0
        
        # 分页查询
        offset = (page - 1) * page_size
        data_stmt = (
            select(
                DockRecord,
                Card.name.label("card_name"),
                Card.price,
                Card.is_multi_spec,
                Card.spec_name,
                Card.spec_value,
                Card.fee_payer,
                Card.min_price,
                User.username.label("source_username"),
            )
            .join(Card, DockRecord.card_id == Card.id)
            .join(User, DockRecord.user_id == User.id)
            .where(*base_conditions)
            .order_by(DockRecord.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self.session.execute(data_stmt)
        rows = result.all()
        
        # 查询当前用户已对接的上级记录ID
        docked_parent_ids: set = set()
        if rows:
            parent_ids = [row[0].id for row in rows]
            docked_stmt = select(DockRecord.parent_dock_id).where(
                DockRecord.user_id == current_user_id,
                DockRecord.parent_dock_id.in_(parent_ids),
            )
            docked_result = await self.session.execute(docked_stmt)
            docked_parent_ids = {r[0] for r in docked_result.all() if r[0]}
        
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        
        records = []
        for row in rows:
            record = row[0]
            records.append({
                "id": record.id,
                "source_user_id": record.user_id,
                "source_username": row[8],
                "card_id": record.card_id,
                "card_name": row[1],
                "card_price": row[2],
                "dock_name": record.dock_name,
                "markup_amount": record.markup_amount,
                "is_multi_spec": row[3],
                "spec_name": row[4],
                "spec_value": row[5],
                "fee_payer": row[6],
                "min_price": row[7],
                "is_docked": record.id in docked_parent_ids,
            })
        
        return {
            "list": records,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    async def get_sub_dealers_paginated(
        self,
        source_user_id: int,
        page: int = 1,
        page_size: int = 20,
        search: str = "",
    ) -> Dict[str, Any]:
        """获取当前一级分销商的下级分销商列表
        
        Args:
            source_user_id: 一级分销商用户ID
            page: 页码
            page_size: 每页数量
            search: 搜索关键词（匹配用户名）
            
        Returns:
            分页数据字典
        """
        base_conditions = [
            DockRecord.source_user_id == source_user_id,
            DockRecord.level == 2,
        ]
        if search:
            base_conditions.append(User.username.ilike(f"%{search}%"))
        
        # 查询总数（不同的下级分销商数量）
        count_stmt = (
            select(func.count(func.distinct(DockRecord.user_id)))
            .join(User, DockRecord.user_id == User.id)
            .where(*base_conditions)
        )
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0
        
        # 分页查询
        offset = (page - 1) * page_size
        data_stmt = (
            select(
                DockRecord.user_id,
                User.username,
                User.email,
                func.count(DockRecord.id).label("dock_count"),
                func.max(DockRecord.created_at).label("last_dock_time"),
            )
            .join(User, DockRecord.user_id == User.id)
            .where(*base_conditions)
            .group_by(DockRecord.user_id, User.username, User.email)
            .order_by(func.count(DockRecord.id).desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self.session.execute(data_stmt)
        rows = result.all()
        
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0
        
        dealers = []
        for row in rows:
            dealers.append({
                "user_id": row[0],
                "username": row[1],
                "email": row[2],
                "dock_count": row[3],
                "last_dock_time": safe_isoformat(row[4]),
            })
        
        return {
            "list": dealers,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    async def disable_sub_dealer_record(
        self,
        record_id: int,
        source_user_id: int,
        disable_reason: Optional[str] = None,
    ) -> bool:
        """一级分销商禁用下级分销商的对接记录
        
        Args:
            record_id: 二级对接记录ID
            source_user_id: 一级分销商用户ID（权限校验）
            disable_reason: 禁用原因
            
        Returns:
            是否操作成功
        """
        stmt = select(DockRecord).where(
            DockRecord.id == record_id,
            DockRecord.source_user_id == source_user_id,
            DockRecord.level == 2,
        )
        result = await self.session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            return False
        
        record.status = False
        record.disable_reason = disable_reason or "一级分销商禁用"
        await self.session.commit()
        logger.info(f"一级分销商 {source_user_id} 禁用二级对接记录 {record_id}")
        return True
