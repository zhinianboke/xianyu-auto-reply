"""
闲鱼账号密码登录（协议化）公共模块

提供纯 API（不依赖浏览器）的账号密码登录能力，供 backend-web 协议登录复用：
1. password2：RSA 加密登录密码
2. login_do：构造 login.do 表单、发起请求、对响应做四分支分类
3. face_verification：触发人脸后的纯 API 人脸验证链路（渲染二维码 + 轮询 + 收 Cookie）

浏览器登录（websocket 侧）为兜底方案，与本模块并存，互不影响。
"""
from __future__ import annotations

from common.services.xianyu_login.login_do import (
    LoginBranch,
    LoginClassifyResult,
    build_login_form,
    classify_login_response,
    post_login_do,
)
from common.services.xianyu_login.password2 import generate_password2

__all__ = [
    "generate_password2",
    "build_login_form",
    "post_login_do",
    "classify_login_response",
    "LoginBranch",
    "LoginClassifyResult",
]
