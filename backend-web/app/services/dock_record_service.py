"""
对接记录服务

提供对接记录的增删改查功能
支持二级分销：level=1为一级分销（直接对接卡券拥有者），level=2为二级分销（对接一级分销商）
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from common.models.dock_record import DockRecord
from common.models.card import Card
from common.models.user import User


from common.utils.time_utils import safe_isoformat
class DockRecordService:
    """对接记录服务类"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_dock_record(
        self,
        user_id: int,
        card_id: int,
        dock_name: str,
        markup_amount: Optional[str] = None,
        remark: Optional[str] = None,
        level: int = 1,
        parent_dock_id: Optional[int] = None,
        source_user_id: Optional[int] = None,
    ) -> int:
        """创建对接记录（支持一级和二级分销）
        
        Args:
            user_id: 用户ID
            card_id: 来源卡券ID
            dock_name: 对接名称
            markup_amount: 加价金额
            remark: 备注
            level: 分销层级，1=一级分销，2=二级分销
            parent_dock_id: 上级对接记录ID，一级分销为None
            source_user_id: 上级分销商用户ID，一级分销为None
            
        Returns:
            新建记录的ID
        """
        record = DockRecord(
            user_id=user_id,
            card_id=card_id,
            dock_name=dock_name,
            markup_amount=markup_amount,
            remark=remark,
            status=True,
            level=level,
            parent_dock_id=parent_dock_id,
            source_user_id=source_user_id,
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        level_str = "一级" if level == 1 else "二级"
        logger.info(f"用户 {user_id} 创建{level_str}对接记录 {record.id}，卡券ID: {card_id}")
        return record.id

    async def update_dock_record(
        self,
        record_id: int,
        user_id: int,
        is_admin: bool = False,
        **kwargs,
    ) -> tuple[bool, str]:
        """更新对接记录（分销商自助更新 / 管理员更新）

        Args:
            record_id: 记录ID
            user_id: 用户ID（权限校验）
            is_admin: 是否管理员，管理员可操作任意用户的对接记录
            **kwargs: 要更新的字段

        Returns:
            (是否成功, 提示信息)

        说明：
        - owner_disabled 为上级锁定标记，分销商无法通过本方法修改它，
          且被上级禁用（owner_disabled=True）的记录，分销商不能自行启用；
        - 仅管理员启用时可解除上级锁定。
        """
        # 非管理员仅能操作本人记录；管理员不限制归属
        conditions = [DockRecord.id == record_id]
        if not is_admin:
            conditions.append(DockRecord.user_id == user_id)
        stmt = select(DockRecord).where(*conditions)
        result = await self.session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            return False, "对接记录不存在或无权限"

        # 上级锁定保护：被上级禁用的记录，分销商不能自行启用
        if 'status' in kwargs and bool(kwargs['status']):
            if record.owner_disabled and not is_admin:
                return False, "该对接记录已被上级禁用，无法自行启用，请联系上级分销商"
            # 管理员启用时解除上级锁定
            if is_admin:
                record.owner_disabled = False

        # owner_disabled 只能由上级/管理员逻辑控制，禁止经普通更新被篡改
        protected_fields = {'owner_disabled'}
        for key, value in kwargs.items():
            if key in protected_fields:
                continue
            if hasattr(record, key):
                setattr(record, key, value)

        await self.session.commit()
        return True, "更新成功"

    async def update_dock_record_by_owner(
        self,
        record_id: int,
        owner_user_id: int,
        **kwargs,
    ) -> bool:
        """卡券拥有者（分销主）更新对接记录
        
        仅允许更新status和disable_reason字段
        
        Args:
            record_id: 记录ID
            owner_user_id: 卡券拥有者用户ID
            **kwargs: 要更新的字段
            
        Returns:
            是否更新成功
        """
        # 通过关联卡券验证当前用户是卡券拥有者
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
            return False

        # 仅允许更新状态和禁用原因
        allowed_fields = {'status', 'disable_reason'}
        for key, value in kwargs.items():
            if key in allowed_fields and hasattr(record, key):
                setattr(record, key, value)

        # 同步上级锁定标记：上级禁用 → 锁定；上级启用 → 解除锁定
        if 'status' in kwargs:
            record.owner_disabled = not bool(kwargs['status'])

        await self.session.commit()
        return True

    async def delete_dock_record(self, record_id: int, user_id: int, is_admin: bool = False) -> bool:
        """删除对接记录
        
        Args:
            record_id: 记录ID
            user_id: 用户ID（权限校验）
            is_admin: 是否管理员，管理员可删除任意用户的对接记录
            
        Returns:
            是否删除成功
        """
        # 非管理员仅能删除本人记录；管理员不限制归属
        conditions = [DockRecord.id == record_id]
        if not is_admin:
            conditions.append(DockRecord.user_id == user_id)
        stmt = select(DockRecord).where(*conditions)
        result = await self.session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            return False

        await self.session.delete(record)
        await self.session.commit()
        logger.info(f"用户 {user_id} 删除对接记录 {record_id}（管理员={is_admin}）")
        return True

    async def get_dock_records_paginated(
        self,
        user_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 20,
        search: str = "",
        status: Optional[bool] = None,
        level: Optional[int] = None,
        allow_sub_dock: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """分页获取对接记录列表
        
        Args:
            user_id: 用户ID，None表示查询所有用户（管理员）
            page: 页码
            page_size: 每页数量
            search: 搜索关键词（匹配对接名称）
            status: 启用状态筛选，None表示不筛选
            level: 分销层级筛选（1=一级，2=二级），None表示不筛选
            allow_sub_dock: 是否开放下级对接筛选，None表示不筛选
            
        Returns:
            分页数据字典
        """
        base_conditions = []
        if user_id is not None:
            base_conditions.append(DockRecord.user_id == user_id)
        if search:
            base_conditions.append(DockRecord.dock_name.ilike(f"%{search}%"))
        if status is not None:
            base_conditions.append(DockRecord.status == status)
        if level is not None:
            base_conditions.append(DockRecord.level == level)
        if allow_sub_dock is not None:
            base_conditions.append(DockRecord.allow_sub_dock == allow_sub_dock)

        # 查询总数
        count_stmt = select(func.count(DockRecord.id)).where(*base_conditions)
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        # 查询分页数据，同时关联卡券获取对接价格
        # 自关联获取上级记录的 sub_dock_price（用于二级记录显示对接价）
        from sqlalchemy.orm import aliased
        ParentDock = aliased(DockRecord)

        offset = (page - 1) * page_size
        data_stmt = (
            select(
                DockRecord, Card.price, Card.name.label("card_name"),
                Card.is_multi_spec, Card.spec_name, Card.spec_value,
                Card.fee_payer, Card.min_price,
                ParentDock.sub_dock_price.label("parent_sub_dock_price"),
                Card.user_id.label("card_owner_id"),
                User.username.label("owner_username"),
            )
            .outerjoin(Card, DockRecord.card_id == Card.id)
            .outerjoin(ParentDock, DockRecord.parent_dock_id == ParentDock.id)
            .outerjoin(User, DockRecord.user_id == User.id)
            .where(*base_conditions)
            .order_by(DockRecord.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self.session.execute(data_stmt)
        rows = result.all()

        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        # 收集需要查询联系方式的用户ID：一级记录取卡券拥有者，二级记录取一级代理
        contact_user_ids = set()
        for row in rows:
            record = row[0]
            card_owner_id = row.card_owner_id
            if record.level == 2 and record.source_user_id:
                contact_user_ids.add(record.source_user_id)
            elif card_owner_id:
                contact_user_ids.add(card_owner_id)
        contact_map = await self._batch_get_source_contacts(list(contact_user_ids))

        records = []
        for row in rows:
            record = row[0]
            card_price = row[1]
            card_name = row[2]
            is_multi_spec = row[3]
            spec_name = row[4]
            spec_value = row[5]
            fee_payer = row[6]
            min_price = row[7]
            parent_sub_dock_price = row[8]
            card_owner_id = row.card_owner_id
            # 二级记录显示上级的sub_dock_price作为对接价格
            display_price = parent_sub_dock_price if record.level == 2 and parent_sub_dock_price else card_price
            # 联系方式：一级取卡券拥有者，二级取一级代理
            contact_uid = record.source_user_id if record.level == 2 and record.source_user_id else card_owner_id
            contact = contact_map.get(contact_uid, {}) if contact_uid else {}
            records.append(self._record_to_dict(
                record, display_price, card_name,
                is_multi_spec, spec_name, spec_value, fee_payer, min_price,
                contact, owner_username=row.owner_username,
            ))

        return {
            "list": records,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    def _record_to_dict(
        self,
        record: DockRecord,
        card_price: Optional[str] = None,
        card_name: Optional[str] = None,
        is_multi_spec: Optional[bool] = None,
        spec_name: Optional[str] = None,
        spec_value: Optional[str] = None,
        fee_payer: Optional[str] = None,
        min_price: Optional[str] = None,
        contact: Optional[Dict[str, str]] = None,
        owner_username: Optional[str] = None,
    ) -> Dict[str, Any]:
        """将对接记录转换为字典"""
        c = contact or {}
        return {
            "id": record.id,
            "user_id": record.user_id,
            "owner_username": owner_username,
            "card_id": record.card_id,
            "card_name": card_name,
            "dock_name": record.dock_name,
            "markup_amount": record.markup_amount,
            "card_price": card_price,
            "fee_payer": fee_payer,
            "min_price": min_price,
            "is_multi_spec": is_multi_spec,
            "spec_name": spec_name,
            "spec_value": spec_value,
            "remark": record.remark,
            "delivery_count": record.delivery_count,
            "status": record.status,
            "disable_reason": record.disable_reason,
            "owner_disabled": record.owner_disabled,
            "level": record.level,
            "parent_dock_id": record.parent_dock_id,
            "source_user_id": record.source_user_id,
            "allow_sub_dock": record.allow_sub_dock,
            "sub_dock_price": record.sub_dock_price,
            "sub_dock_visibility": record.sub_dock_visibility,
            "created_at": safe_isoformat(record.created_at),
            "updated_at": safe_isoformat(record.updated_at),
            "contact_wechat": c.get("wechat", ""),
            "contact_qq": c.get("qq", ""),
            "contact_email": c.get("email", ""),
        }

    async def get_dealers_paginated(
        self,
        owner_user_id: int,
        page: int = 1,
        page_size: int = 20,
        search: str = "",
    ) -> Dict[str, Any]:
        """分页获取对接了当前用户卡券的分销商列表
        
        Args:
            owner_user_id: 卡券拥有者用户ID
            page: 页码
            page_size: 每页数量
            search: 搜索关键词（匹配用户名）
            
        Returns:
            分页数据字典，每条记录包含分销商信息和对接卡券数量
        """
        # 基础条件：对接记录关联的卡券属于当前用户
        base_conditions = [Card.user_id == owner_user_id]
        if search:
            base_conditions.append(User.username.ilike(f"%{search}%"))

        # 查询总数（不同的分销商数量）
        count_stmt = (
            select(func.count(func.distinct(DockRecord.user_id)))
            .join(Card, DockRecord.card_id == Card.id)
            .join(User, DockRecord.user_id == User.id)
            .where(*base_conditions)
        )
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        # 分页查询分销商及其对接数量
        offset = (page - 1) * page_size
        from sqlalchemy import case as sa_case
        data_stmt = (
            select(
                DockRecord.user_id,
                User.username,
                User.email,
                func.count(DockRecord.id).label("dock_count"),
                func.max(DockRecord.created_at).label("last_dock_time"),
                func.sum(sa_case((DockRecord.level == 1, 1), else_=0)).label("level_1_count"),
                func.sum(sa_case((DockRecord.level == 2, 1), else_=0)).label("level_2_count"),
            )
            .join(Card, DockRecord.card_id == Card.id)
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
                "level_1_count": row[5] or 0,
                "level_2_count": row[6] or 0,
            })

        return {
            "list": dealers,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    async def get_dealer_dock_details(
        self,
        owner_user_id: int,
        dealer_user_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """分页获取某个分销商对接当前用户卡券的明细
        
        Args:
            owner_user_id: 卡券拥有者用户ID
            dealer_user_id: 分销商用户ID
            page: 页码
            page_size: 每页数量
            
        Returns:
            分页数据字典，包含对接记录明细
        """
        base_conditions = [
            DockRecord.user_id == dealer_user_id,
            Card.user_id == owner_user_id,
        ]

        # 查询总数
        count_stmt = (
            select(func.count(DockRecord.id))
            .join(Card, DockRecord.card_id == Card.id)
            .where(*base_conditions)
        )
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        # 分页查询明细
        offset = (page - 1) * page_size
        data_stmt = (
            select(
                DockRecord, Card.price, Card.name.label("card_name"),
                Card.is_multi_spec, Card.spec_name, Card.spec_value,
                Card.fee_payer, Card.min_price,
            )
            .join(Card, DockRecord.card_id == Card.id)
            .where(*base_conditions)
            .order_by(DockRecord.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self.session.execute(data_stmt)
        rows = result.all()

        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        records = []
        for row in rows:
            record = row[0]
            records.append(self._record_to_dict(
                record, row[1], row[2], row[3], row[4], row[5], row[6], row[7],
            ))

        return {
            "list": records,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    async def get_sub_dealer_dock_details(
        self,
        source_user_id: int,
        dealer_user_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """分页获取某个下级分销商对接当前一级分销商的明细
        
        Args:
            source_user_id: 一级分销商用户ID（当前用户）
            dealer_user_id: 二级分销商用户ID
            page: 页码
            page_size: 每页数量
            
        Returns:
            分页数据字典，包含对接记录明细
        """
        base_conditions = [
            DockRecord.user_id == dealer_user_id,
            DockRecord.source_user_id == source_user_id,
            DockRecord.level == 2,
        ]

        # 查询总数
        count_stmt = (
            select(func.count(DockRecord.id))
            .where(*base_conditions)
        )
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar() or 0

        # 自关联获取上级记录的 sub_dock_price
        from sqlalchemy.orm import aliased
        ParentDock = aliased(DockRecord)

        # 分页查询明细
        offset = (page - 1) * page_size
        data_stmt = (
            select(
                DockRecord, Card.price, Card.name.label("card_name"),
                Card.is_multi_spec, Card.spec_name, Card.spec_value,
                Card.fee_payer, Card.min_price,
                ParentDock.sub_dock_price.label("parent_sub_dock_price"),
            )
            .outerjoin(Card, DockRecord.card_id == Card.id)
            .outerjoin(ParentDock, DockRecord.parent_dock_id == ParentDock.id)
            .where(*base_conditions)
            .order_by(DockRecord.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self.session.execute(data_stmt)
        rows = result.all()

        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        records = []
        for row in rows:
            record = row[0]
            card_price = row[1]
            parent_sub_dock_price = row[8]
            display_price = parent_sub_dock_price if parent_sub_dock_price else card_price
            records.append(self._record_to_dict(
                record, display_price, row[2], row[3], row[4], row[5], row[6], row[7],
            ))

        return {
            "list": records,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    async def _batch_get_source_contacts(self, user_ids: list[int]) -> Dict[int, Dict[str, str]]:
        """批量查询用户联系方式（微信、QQ来自UserSetting，邮箱来自User表）
        
        Returns:
            {user_id: {"wechat": ..., "qq": ..., "email": ...}}
        """
        from common.models.user_setting import UserSetting
        
        unique_ids = list(set(uid for uid in user_ids if uid))
        if not unique_ids:
            return {}
        
        contact_map: Dict[int, Dict[str, str]] = {uid: {"wechat": "", "qq": "", "email": ""} for uid in unique_ids}
        
        # 查询邮箱
        email_stmt = select(User.id, User.email).where(User.id.in_(unique_ids))
        email_result = await self.session.execute(email_stmt)
        for row in email_result.all():
            contact_map[row[0]]["email"] = row[1] or ""
        
        # 查询微信和QQ（从 UserSetting 表）
        setting_stmt = select(UserSetting.user_id, UserSetting.key, UserSetting.value).where(
            UserSetting.user_id.in_(unique_ids),
            UserSetting.key.in_(["contact_wechat", "contact_qq"]),
        )
        setting_result = await self.session.execute(setting_stmt)
        for row in setting_result.all():
            uid, key, value = row[0], row[1], row[2]
            if key == "contact_wechat":
                contact_map[uid]["wechat"] = value or ""
            elif key == "contact_qq":
                contact_map[uid]["qq"] = value or ""
        
        return contact_map

    # ========== 二级分销方法 ==========

    async def get_dockable_sub_records_paginated(
        self,
        current_user_id: int,
        page: int = 1,
        page_size: int = 20,
        search: str = "",
    ) -> Dict[str, Any]:
        """获取可对接的一级分销商记录列表（二级分销货源广场）
        
        查询条件：level=1, allow_sub_dock=True, status=True, 且不是自己的记录
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
        from sqlalchemy.orm import aliased
        from common.models.dock_code_binding import DockCodeBinding
        
        SourceUser = aliased(User)
        
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
                Card.price.label("card_price"),
                Card.is_multi_spec,
                Card.spec_name,
                Card.spec_value,
                Card.fee_payer,
                Card.min_price,
                SourceUser.username.label("source_username"),
            )
            .join(Card, DockRecord.card_id == Card.id)
            .join(SourceUser, DockRecord.user_id == SourceUser.id)
            .where(*base_conditions)
            .order_by(DockRecord.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self.session.execute(data_stmt)
        rows = result.all()

        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        # 批量检查当前用户是否已对接这些记录
        parent_dock_ids = [row[0].id for row in rows]
        docked_set: set = set()
        if parent_dock_ids:
            docked_stmt = (
                select(DockRecord.parent_dock_id)
                .where(
                    DockRecord.user_id == current_user_id,
                    DockRecord.level == 2,
                    DockRecord.parent_dock_id.in_(parent_dock_ids),
                )
            )
            docked_result = await self.session.execute(docked_stmt)
            docked_set = {r[0] for r in docked_result.all()}

        records = []
        for row in rows:
            record = row[0]
            records.append({
                "id": record.id,
                "source_user_id": record.user_id,
                "source_username": row.source_username,
                "card_id": record.card_id,
                "card_name": row.card_name,
                "card_price": row.card_price,
                "sub_dock_price": record.sub_dock_price,
                "dock_name": record.dock_name,
                "markup_amount": record.markup_amount,
                "is_multi_spec": row.is_multi_spec,
                "spec_name": row.spec_name,
                "spec_value": row.spec_value,
                "fee_payer": row.fee_payer,
                "min_price": row.min_price,
                "is_docked": record.id in docked_set,
            })

        return {
            "list": records,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    async def create_sub_dock_record(
        self,
        user_id: int,
        parent_dock_id: int,
        dock_name: str,
        markup_amount: Optional[str] = None,
        remark: Optional[str] = None,
    ) -> Dict[str, Any]:
        """创建二级对接记录
        
        校验规则：
        1. 上级记录必须存在且为一级分销
        2. 上级记录必须开放了下级对接 (allow_sub_dock=True)
        3. 上级记录必须启用状态 (status=True)
        4. 不能对接自己的记录
        5. 不能重复对接同一个上级记录
        
        Args:
            user_id: 当前用户ID
            parent_dock_id: 上级对接记录ID
            dock_name: 对接名称
            markup_amount: 加价金额
            remark: 备注
            
        Returns:
            结果字典 {"success": bool, "message": str, "id": int|None}
        """
        # 1. 查询上级对接记录
        parent_stmt = select(DockRecord).where(DockRecord.id == parent_dock_id)
        parent_result = await self.session.execute(parent_stmt)
        parent_record = parent_result.scalar_one_or_none()

        if not parent_record:
            return {"success": False, "message": "上级对接记录不存在", "id": None}

        if parent_record.level != 1:
            return {"success": False, "message": "仅支持对接一级分销商的记录", "id": None}

        if not parent_record.allow_sub_dock:
            return {"success": False, "message": "该一级分销商未开放下级对接", "id": None}

        if not parent_record.status:
            return {"success": False, "message": "该对接记录已被禁用", "id": None}

        if parent_record.user_id == user_id:
            return {"success": False, "message": "不能对接自己的记录", "id": None}

        # 2. 检查是否已对接
        dup_stmt = select(func.count(DockRecord.id)).where(
            DockRecord.user_id == user_id,
            DockRecord.level == 2,
            DockRecord.parent_dock_id == parent_dock_id,
        )
        dup_result = await self.session.execute(dup_stmt)
        if (dup_result.scalar() or 0) > 0:
            return {"success": False, "message": "您已对接该记录，不能重复对接", "id": None}

        # 3. 创建二级对接记录
        record_id = await self.create_dock_record(
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
        sub_dock_price: Optional[str] = None,
        sub_dock_visibility: Optional[str] = None,
        is_admin: bool = False,
    ) -> bool:
        """开放/关闭下级对接（一级分销商可操作自己的对接记录，管理员可操作任意记录）
        
        Args:
            record_id: 对接记录ID
            user_id: 当前用户ID
            allow: 是否允许下级对接
            sub_dock_price: 给下级的对接价格
            sub_dock_visibility: 下级对接可见性：public/dealer_only
            is_admin: 是否管理员，管理员不限制记录归属
            
        Returns:
            是否操作成功
        """
        # 仅限一级分销记录；非管理员还需校验记录归属
        conditions = [DockRecord.id == record_id, DockRecord.level == 1]
        if not is_admin:
            conditions.append(DockRecord.user_id == user_id)
        stmt = select(DockRecord).where(*conditions)
        result = await self.session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            return False

        record.allow_sub_dock = allow
        if allow and sub_dock_price is not None:
            record.sub_dock_price = sub_dock_price
        elif not allow:
            record.sub_dock_price = None
        if allow and sub_dock_visibility is not None:
            record.sub_dock_visibility = sub_dock_visibility
        elif not allow:
            record.sub_dock_visibility = None
        await self.session.commit()
        action = "开放" if allow else "关闭"
        logger.info(f"用户 {user_id} {action}对接记录 {record_id} 的下级对接，对接价: {sub_dock_price}，可见性: {sub_dock_visibility}")
        return True

    async def update_dock_record_status_with_cascade(
        self,
        record_id: int,
        owner_user_id: int,
        status: bool,
        disable_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """更新对接记录状态，禁用时级联禁用下级
        
        业务规则：
        - 禁用一级 → 级联禁用该一级下的所有二级，disable_reason="上级分销商被禁用"
        - 启用一级 → 不自动恢复二级（需手动启用）
        - 卡券拥有者直接禁用二级 → 支持，disable_reason="分销主禁用"
        
        Args:
            record_id: 对接记录ID
            owner_user_id: 卡券拥有者用户ID（权限校验）
            status: 目标状态
            disable_reason: 禁用原因
            
        Returns:
            结果字典 {"success": bool, "message": str, "cascade_count": int}
        """
        # 通过关联卡券验证当前用户是卡券拥有者
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

        # 更新目标记录状态
        record.status = status
        record.disable_reason = disable_reason if not status else None
        # 同步上级锁定标记：上级禁用 → 锁定，分销商不可自行启用；上级启用 → 解除锁定
        record.owner_disabled = not status

        cascade_count = 0

        # 禁用且目标为一级记录时，级联禁用所有下级
        if not status and record.level == 1:
            sub_stmt = select(DockRecord).where(
                DockRecord.parent_dock_id == record_id,
                DockRecord.level == 2,
                DockRecord.status == True,
            )
            sub_result = await self.session.execute(sub_stmt)
            sub_records = sub_result.scalars().all()
            for sub in sub_records:
                sub.status = False
                sub.disable_reason = "上级分销商被禁用"
                sub.owner_disabled = True
                cascade_count += 1

        await self.session.commit()

        action = "启用" if status else "禁用"
        logger.info(
            f"卡券拥有者 {owner_user_id} {action}对接记录 {record_id}，级联影响 {cascade_count} 条下级记录"
        )
        return {"success": True, "message": f"{action}成功", "cascade_count": cascade_count}

    async def get_sub_dealers_paginated(
        self,
        source_user_id: int,
        page: int = 1,
        page_size: int = 20,
        search: str = "",
    ) -> Dict[str, Any]:
        """获取当前一级分销商的下级分销商列表
        
        查询 level=2 且 source_user_id=当前用户 的对接记录，按用户分组
        
        Args:
            source_user_id: 一级分销商用户ID
            page: 页码
            page_size: 每页数量
            search: 搜索关键词（匹配用户名）
            
        Returns:
            分页数据字典
        """
        base_conditions = [
            DockRecord.level == 2,
            DockRecord.source_user_id == source_user_id,
        ]
        if search:
            base_conditions.append(User.username.ilike(f"%{search}%"))

        # 查询不同二级分销商数量
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
            DockRecord.level == 2,
            DockRecord.source_user_id == source_user_id,
        )
        result = await self.session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            return False

        record.status = False
        record.disable_reason = disable_reason or "一级分销商禁用"
        record.owner_disabled = True
        await self.session.commit()
        logger.info(f"一级分销商 {source_user_id} 禁用下级对接记录 {record_id}")
        return True

    async def enable_sub_dealer_record(
        self,
        record_id: int,
        source_user_id: int,
    ) -> bool:
        """一级分销商启用（恢复）下级分销商的对接记录

        与 disable_sub_dealer_record 对称：作为上级解除对该二级记录的禁用锁定，
        使下级可正常使用。仅记录所属的一级分销商可操作。

        Args:
            record_id: 二级对接记录ID
            source_user_id: 一级分销商用户ID（权限校验）

        Returns:
            是否操作成功
        """
        stmt = select(DockRecord).where(
            DockRecord.id == record_id,
            DockRecord.level == 2,
            DockRecord.source_user_id == source_user_id,
        )
        result = await self.session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            return False

        record.status = True
        record.disable_reason = None
        record.owner_disabled = False
        await self.session.commit()
        logger.info(f"一级分销商 {source_user_id} 启用下级对接记录 {record_id}")
        return True

