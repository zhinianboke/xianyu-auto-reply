"""
工具函数模块

提供通用的工具函数
"""


def safe_str(e) -> str:
    """安全地将异常转换为字符串
    
    Args:
        e: 异常对象
        
    Returns:
        异常的字符串表示
    """
    try:
        return str(e)
    except:
        try:
            return repr(e)
        except:
            return "未知错误"
