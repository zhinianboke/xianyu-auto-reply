"""启动器前端静态文件服务、存活检查及后端 API 代理。"""
from __future__ import annotations

import http.server
import json
import os
import urllib.request
from pathlib import Path
from urllib.parse import unquote

from loguru import logger


class FrontendHandler(http.server.SimpleHTTPRequestHandler):
    """托管前端页面并代理 API，公开状态请求按 socket 地址转发真实 IP。"""

    def __init__(self, *args, dist_dir: str = "", **kwargs):
        """保存构建目录与可配置的后端代理地址，初始化请求处理器。"""
        self._dist_dir = dist_dir
        self._backend_url = os.environ.get("BACKEND_WEB_SERVICE_URL", "http://127.0.0.1:8089").rstrip("/")
        super().__init__(*args, directory=dist_dir, **kwargs)

    def _proxy_if_needed(self) -> bool:
        """匹配 API 或上传文件路径，转发成功返回 True，否则返回 False。"""
        pathname, separator, query = self.path.partition("?")
        decoded_path = unquote(pathname)
        if decoded_path in {"/api/v1/public/status", "/api/v1/public/status/"}:
            # 仅规范化公开状态路径，查询参数原样保留，兼容编码后的 /api/ 前缀。
            self.path = decoded_path + (separator + query if separator else "")
        if self.path.startswith(("/api/", "/static/uploads/")):
            self._proxy_request(self._backend_url)
            return True
        return False

    def do_GET(self):
        """处理存活检查、API 代理及 SPA 静态页面请求。"""
        if self.path.split("?", 1)[0] == "/frontend-health":
            self._send_json(200, {"success": True, "code": 200, "message": "前端服务已启动", "data": {"status": "running"}})
            return
        if self._proxy_if_needed():
            return
        file_path = Path(self._dist_dir) / self.path.lstrip("/").split("?")[0]
        if not file_path.exists() and not file_path.suffix:
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self):
        """转发 POST API 请求；非 API 路径返回未找到。"""
        if not self._proxy_if_needed():
            self.send_error(404)

    def do_HEAD(self):
        """公开状态 HEAD 请求交给后端校验，其他路径沿用静态服务器行为。"""
        if not self._proxy_if_needed():
            super().do_HEAD()

    def do_PATCH(self):
        """转发 PATCH 请求，由公开接口返回统一的方法错误和限流结果。"""
        if not self._proxy_if_needed():
            self.send_error(404)

    def do_OPTIONS(self):
        """转发 OPTIONS 请求，公开接口及跨域校验由后端统一处理。"""
        if not self._proxy_if_needed():
            self.send_error(404)

    def do_TRACE(self):
        """转发 TRACE 请求，公开接口返回方法错误而不回显请求内容。"""
        if not self._proxy_if_needed():
            self.send_error(404)

    def do_PUT(self):
        """转发 PUT API 请求；非 API 路径返回未找到。"""
        if not self._proxy_if_needed():
            self.send_error(404)

    def do_DELETE(self):
        """转发 DELETE API 请求；非 API 路径返回未找到。"""
        if not self._proxy_if_needed():
            self.send_error(404)

    def _send_json(self, status: int, payload: dict):
        """按给定 HTTP 状态发送 UTF-8 JSON，并禁止缓存。"""
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _proxy_request(self, target_base: str):
        """将请求转发到配置的后端；公开状态代理失败时返回统一中文业务响应。"""
        is_public = unquote(self.path.split("?", 1)[0]).startswith("/api/v1/public/")
        response_started = False
        try:
            target_url = f"{target_base}{self.path}"
            body = None
            if is_public:
                # 公开接口无需请求体，错误方法也直接进入限流，不等待客户端发送内容。
                self.close_connection = True
            else:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length) if content_length > 0 else None
            req = urllib.request.Request(target_url, data=body, method=self.command)
            excluded = {"host", "content-length"}
            if is_public:
                excluded.update({
                    "x-forwarded-for", "x-real-ip", "transfer-encoding", "expect",
                    "connection", "proxy-connection", "te", "trailer", "upgrade",
                })
            for header, value in self.headers.items():
                if header.lower() not in excluded:
                    req.add_header(header, value)
            if is_public:
                req.add_header("X-Forwarded-For", self.client_address[0])
                req.add_header("X-Real-IP", self.client_address[0])
            with urllib.request.urlopen(req, timeout=15 if is_public else 90) as resp:
                # 先完整读取上游响应，读取失败时仍能返回统一 JSON。
                response_body = resp.read()
                response_started = True
                self.send_response(resp.status)
                for header, value in resp.getheaders():
                    if header.lower() != "transfer-encoding":
                        self.send_header(header, value)
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(response_body)
        except Exception as exc:
            logger.exception("前端代理请求失败：method={} path={}", self.command, self.path)
            if response_started:
                self.close_connection = True
                return
            self._send_json(200 if is_public else 502, {
                "success": False, "code": 50303 if is_public else 502,
                "message": "状态查询服务暂不可用，请稍后重试" if is_public else f"代理请求失败: {exc}",
                "data": None,
            })

    def log_message(self, format, *args):
        """使用公共日志配置记录前端请求结果。"""
        logger.info("前端请求：ip={} result={}", self.client_address[0], format % args)
