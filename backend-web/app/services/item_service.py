"""
商品服务

功能：
1. 商品目录CRUD操作
2. 商品信息更新（标题、价格、描述等）
3. 商品列表查询
4. 批量删除商品
5. 抓取闲鱼商品并入库（带账号级并发锁）

此文件从 common.services.item_service 导入，保持向后兼容；
真正的实现位于 common 目录，供 backend-web 与 scheduler 服务共同使用。
"""
from common.services.item_service import ItemService

__all__ = ["ItemService"]
