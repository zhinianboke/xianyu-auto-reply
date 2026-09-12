"""
通用查询按钮配置 - 数据迁移脚本（部署时在服务器上手动执行）

功能：
1. 给指定的两个闲鱼商品（item_id 1083580260536 / 1084268940799）的
   ``xy_catalog_items.metadata`` 合并写入「查余额」查询按钮配置
   （JSON_MERGE_PATCH；已存在 query_buttons 的行跳过，不覆盖手工改动）
2. 更新 xy_keyword_rules id 1-7 的回复文案，引导买家使用「查余额」按钮
3. 打印执行前后状态；``--dry-run`` 只打印不提交

用法（密码绝不写死在脚本/命令历史之外的地方，优先用环境变量或交互输入）：
    MYSQL_PASSWORD=xxx python scripts/deploy_query_buttons_migration.py --host 127.0.0.1
    python scripts/deploy_query_buttons_migration.py --dry-run   # 预演，不提交

注意：数据库列名为 ``metadata``（ORM 属性 metadata_json 映射），不涉及表结构变更。
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys

try:
    import pymysql
except ImportError:
    print("缺少 pymysql 依赖，请先安装：pip install pymysql")
    sys.exit(1)

# 需要写入「查余额」配置的商品（请替换为你自己的商品ID）
TARGET_ITEM_IDS = ("your-item-id-1", "your-item-id-2")

# 「查余额」按钮配置（与全局接口契约 QueryButton 一致）
# 注意：url 请替换为你自己的余额查询接口
BALANCE_BUTTON = {
    "name": "查余额",
    "method": "GET",
    "url": "https://your-api.example.com/wallet/summary",
    "headers": {"Cookie": "{cookie}"},
    "body": None,
    "success_path": "code",
    "success_value": "0",
    "error_path": "message",
    "result_fields": [
        {"label": "可用余额", "path": "data.availableBalanceCny", "highlight": True, "prefix": "¥"},
        {"label": "赠送总额", "path": "data.giftTotalCny", "highlight": False, "prefix": "¥"},
        {"label": "锁定金额", "path": "data.giftLockedCny", "highlight": False, "prefix": "¥"},
        {"label": "账户状态", "path": "data.giftStatus", "highlight": False, "prefix": ""},
    ],
}

# 需要更新文案的关键词规则 id 范围（1-7）
KEYWORD_RULE_IDS = tuple(range(1, 8))

# 新回复文案：引导买家使用提货链接底部的「查余额」按钮
KEYWORD_REPLY_CONTENT = "点发货链接底部的「查余额」按钮即可直接查询余额，无需手动复制 Cookie。"


def parse_args() -> argparse.Namespace:
    """解析命令行参数；连接信息优先取命令行，其次环境变量，密码最后交互输入。"""
    parser = argparse.ArgumentParser(description="通用查询按钮配置数据迁移（查余额 + 关键词文案）")
    parser.add_argument("--host", default=os.environ.get("MYSQL_HOST", "127.0.0.1"), help="MySQL 主机")
    parser.add_argument("--port", type=int, default=int(os.environ.get("MYSQL_PORT", "3306")), help="MySQL 端口")
    parser.add_argument("--user", default=os.environ.get("MYSQL_USER", "root"), help="MySQL 用户")
    parser.add_argument("--password", default=os.environ.get("MYSQL_PASSWORD"), help="MySQL 密码（建议用环境变量 MYSQL_PASSWORD 传入）")
    parser.add_argument("--database", default=os.environ.get("MYSQL_DATABASE", "xianyu_data"), help="数据库名")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要执行的变更，不实际提交")
    return parser.parse_args()


def print_item_state(cursor, title: str) -> None:
    """打印目标商品当前的 query_buttons 配置状态。"""
    print(f"\n== {title}：xy_catalog_items 目标商品状态 ==")
    cursor.execute(
        "SELECT id, item_id, JSON_EXTRACT(COALESCE(metadata, '{}'), '$.query_buttons') AS buttons "
        "FROM xy_catalog_items WHERE item_id IN %s ORDER BY id",
        (TARGET_ITEM_IDS,),
    )
    rows = cursor.fetchall()
    if not rows:
        print("  （未找到目标商品行，请确认 item_id 是否正确）")
    for row in rows:
        buttons = row[2]
        state = "已配置" if buttons else "未配置"
        print(f"  id={row[0]} item_id={row[1]} query_buttons={state}")
        if buttons:
            print(f"    当前内容: {buttons}")


def print_keyword_state(cursor, title: str) -> None:
    """打印目标关键词规则当前的回复文案。"""
    print(f"\n== {title}：xy_keyword_rules id 1-7 状态 ==")
    cursor.execute(
        "SELECT id, keyword, reply_content FROM xy_keyword_rules WHERE id IN %s ORDER BY id",
        (KEYWORD_RULE_IDS,),
    )
    rows = cursor.fetchall()
    if not rows:
        print("  （未找到 id 1-7 的关键词规则）")
    for row in rows:
        content = (row[2] or "").replace("\n", " ")
        print(f"  id={row[0]} keyword={row[1]} reply_content={content[:60]}")


def migrate_items(cursor, dry_run: bool) -> None:
    """给目标商品合并写入「查余额」配置；已配置的行跳过。"""
    patch = json.dumps({"query_buttons": [BALANCE_BUTTON]}, ensure_ascii=False)
    cursor.execute(
        "SELECT item_id FROM xy_catalog_items "
        "WHERE item_id IN %s AND JSON_EXTRACT(COALESCE(metadata, '{}'), '$.query_buttons') IS NOT NULL",
        (TARGET_ITEM_IDS,),
    )
    configured = {row[0] for row in cursor.fetchall()}

    for item_id in TARGET_ITEM_IDS:
        if item_id in configured:
            print(f"  [跳过] item_id={item_id} 已存在 query_buttons 配置")
            continue
        print(f"  [写入] item_id={item_id} 合并 query_buttons「查余额」配置")
        if not dry_run:
            cursor.execute(
                "UPDATE xy_catalog_items "
                "SET metadata = JSON_MERGE_PATCH(COALESCE(metadata, '{}'), %s) "
                "WHERE item_id = %s "
                "AND JSON_EXTRACT(COALESCE(metadata, '{}'), '$.query_buttons') IS NULL",
                (patch, item_id),
            )
            if cursor.rowcount == 0:
                print(f"  [警告] item_id={item_id} 未更新任何行（商品不存在或已被并发写入）")


def migrate_keywords(cursor, dry_run: bool) -> None:
    """更新 xy_keyword_rules id 1-7 的回复文案为「查余额」按钮引导语。"""
    print(f"  [更新] xy_keyword_rules id 1-7 reply_content -> {KEYWORD_REPLY_CONTENT}")
    if not dry_run:
        cursor.execute(
            "UPDATE xy_keyword_rules SET reply_content = %s WHERE id IN %s",
            (KEYWORD_REPLY_CONTENT, KEYWORD_RULE_IDS),
        )
        print(f"  [完成] 实际更新 {cursor.rowcount} 行")


def main() -> None:
    args = parse_args()
    password = args.password
    if not password:
        # 命令行/环境变量都未提供密码时交互输入，避免明文落盘
        password = getpass.getpass("请输入 MySQL 密码: ")

    mode = "DRY-RUN（不提交）" if args.dry_run else "正式执行"
    print(f"连接 {args.user}@{args.host}:{args.port}/{args.database}，模式：{mode}")

    conn = pymysql.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=password,
        database=args.database,
        charset="utf8mb4",
        connect_timeout=10,
        autocommit=False,
    )
    try:
        with conn.cursor() as cursor:
            print_item_state(cursor, "执行前")
            print_keyword_state(cursor, "执行前")

            print("\n== 执行迁移 ==")
            migrate_items(cursor, args.dry_run)
            migrate_keywords(cursor, args.dry_run)

            if args.dry_run:
                conn.rollback()
                print("\nDRY-RUN：已回滚，未提交任何变更")
            else:
                conn.commit()
                print("\n已提交全部变更")

            print_item_state(cursor, "执行后")
            print_keyword_state(cursor, "执行后")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
