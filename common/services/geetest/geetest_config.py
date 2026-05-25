"""
极验验证码配置

从环境变量读取配置，提供默认值
"""
import os


class GeetestConfig:
    """极验验证码配置类"""
    
    # 极验分配的captcha_id（从环境变量读取，有默认值）
    CAPTCHA_ID = os.getenv("GEETEST_CAPTCHA_ID", "a30cdbb466e9349385762477cb2c7df6")
    
    # 极验分配的私钥（从环境变量读取，有默认值）
    PRIVATE_KEY = os.getenv("GEETEST_PRIVATE_KEY", "6f70322308eb29ae0d85516a14a32d2c")
    
    # 用户标识（可选）
    USER_ID = os.getenv("GEETEST_USER_ID", "xianyu_system")
    
    # 客户端类型：web, h5, native, unknown
    CLIENT_TYPE = "web"
    
    # API地址
    API_URL = "http://api.geetest.com"
    REGISTER_URL = "/register.php"
    VALIDATE_URL = "/validate.php"
    
    # SDK版本
    VERSION = "python-fastapi:3.1.1"
    
    # 请求超时时间（秒）- 优化为3秒以提升响应速度
    TIMEOUT = 3.0
