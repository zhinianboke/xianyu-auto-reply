"""
数据库和Redis连接验证模块

功能：
1. 验证MySQL连接是否正常
2. 验证Redis连接是否正常
3. 供GUI界面调用，验证用户填写的连接信息
"""
import socket


def check_mysql_connection(host: str, port: int, user: str, password: str, database: str) -> dict:
    """
    检查MySQL数据库连接
    
    先通过socket检测端口是否可达，再尝试用pymysql建立真实连接。
    
    Args:
        host: MySQL主机地址
        port: MySQL端口
        user: 用户名
        password: 密码
        database: 数据库名
    Returns:
        字典包含:
        - success: bool 连接是否成功
        - message: str 结果说明
    """
    # 先检查端口可达性
    try:
        sock = socket.create_connection((host, port), timeout=5)
        sock.close()
    except socket.timeout:
        return {"success": False, "message": f"连接超时：无法连接到 {host}:{port}"}
    except socket.error as e:
        return {"success": False, "message": f"网络错误：{host}:{port} 不可达 - {e}"}
    
    # 尝试真实数据库连接
    try:
        import pymysql
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            connect_timeout=10,
            charset="utf8mb4",
        )
        conn.ping(reconnect=False)
        conn.close()
        return {"success": True, "message": "MySQL连接成功"}
    except ImportError:
        return {"success": False, "message": "缺少pymysql依赖，请检查安装"}
    except Exception as e:
        return {"success": False, "message": f"MySQL连接失败: {e}"}


def check_redis_connection(host: str, port: int, password: str, db: int) -> dict:
    """
    检查Redis连接
    
    尝试建立Redis连接并执行PING命令。
    
    Args:
        host: Redis主机地址
        port: Redis端口
        password: Redis密码（可为空字符串）
        db: Redis数据库编号
    Returns:
        字典包含:
        - success: bool 连接是否成功
        - message: str 结果说明
    """
    # 先检查端口可达性
    try:
        sock = socket.create_connection((host, port), timeout=5)
        sock.close()
    except socket.timeout:
        return {"success": False, "message": f"连接超时：无法连接到 {host}:{port}"}
    except socket.error as e:
        return {"success": False, "message": f"网络错误：{host}:{port} 不可达 - {e}"}
    
    # 尝试真实Redis连接
    try:
        import redis
        r = redis.Redis(
            host=host,
            port=port,
            password=password if password else None,
            db=db,
            socket_connect_timeout=10,
            decode_responses=True,
        )
        r.ping()
        r.close()
        return {"success": True, "message": "Redis连接成功"}
    except ImportError:
        return {"success": False, "message": "缺少redis依赖，请检查安装"}
    except Exception as e:
        return {"success": False, "message": f"Redis连接失败: {e}"}
