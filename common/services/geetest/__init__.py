"""
极验滑动验证码SDK（共享模块）

功能：
1. 验证码初始化（register）
2. 二次验证（validate）
3. 支持正常模式和宕机降级模式
"""
from .geetest_config import GeetestConfig, get_geetest_config
from .geetest_lib import GeetestLib

__all__ = ["GeetestConfig", "GeetestLib", "get_geetest_config"]
