"""卡券接口公共校验、依赖与响应适配，仅作用于卡券路由。"""
from __future__ import annotations

import hashlib
import json
from tempfile import TemporaryFile
from traceback import format_exception
from typing import Any, BinaryIO, Callable, Optional
from uuid import uuid4
from fastapi import Depends, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException
from starlette.concurrency import run_in_threadpool

from app.api import deps
from app.api.routes.card_multipart_audit import (
    CARD_BODY_CHUNK_BYTES, CardMultipartError, CardMultipartParser,
    audit_card_multipart, card_body_chunks, is_card_multipart,
)
from app.core.config import get_settings
from app.core.paths import STATIC_ROOT
from app.services.card_service import CardService
from common.db.error_messages import get_public_database_error_message
from common.schemas.common import ApiResponse
from common.utils.http_utils import get_client_ip

CARD_UPLOAD_DIR = STATIC_ROOT / "uploads" / "cards"
CARD_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _card_request_max_bytes() -> int:
    """通过项目统一配置读取请求上限，兼容环境变量与本地 .env；返回正整数字节数。"""
    return get_settings().card_request_max_bytes


# 缺省与现有 Nginx 的 50 MiB 上限一致；图片自身的 5 MiB 校验保持不变。
CARD_REQUEST_MAX_BYTES = _card_request_max_bytes()


def _card_response(payload: Any) -> dict:
    """将业务结果转为统一响应；参数为原返回数据，返回兼容旧字典字段的响应。"""
    if isinstance(payload, dict) and isinstance(payload.get("success"), bool):
        result = dict(payload)
        success = result["success"]
        result["code"] = 200 if success else (result.get("code") if result.get("code") in {401, 403} else 40001)
        result["message"] = result.get("message") or ("操作成功" if success else "操作失败")
        if success and "data" not in result:
            result["data"] = {key: value for key, value in payload.items() if key not in {"success", "code", "message"}}
        elif not success:
            result["data"] = None
        return result
    message = payload.get("message", "操作成功") if isinstance(payload, dict) else "操作成功"
    result = ApiResponse(success=True, code=200, message=message, data=payload).model_dump()
    if isinstance(payload, dict):
        # 保留旧版卡券详情、分页及上传接口的顶层字段。
        result.update({key: value for key, value in payload.items() if key not in result})
    return result


def _binary_body(content: bytes, content_type: Optional[str], *, field_name=None, filename=None) -> dict:
    """记录二进制元信息而非原始字节；参数为内容和文件信息，返回大小与 SHA256。"""
    return {
        "field_name": field_name, "filename": filename, "content_type": content_type,
        "size": len(content), "sha256": hashlib.sha256(content).hexdigest(),
    }


def _card_body_chunks(content: bytes | BinaryIO):
    """兼容原分片入口；参数为字节或文件，返回公共64KiB分片迭代器。"""
    yield from card_body_chunks(content)


def _card_multipart_body(content: bytes | BinaryIO, content_type: str, *, complete: bool = True) -> dict:
    """兼容原multipart审计入口；公共解析器限制物化规模，返回真实完整或前缀审计。"""
    return audit_card_multipart(content, content_type, complete=complete)


def _card_request_body(content: bytes | BinaryIO, content_type: str, *, complete: bool = True) -> Any:
    """读取有界审计缓冲；文本保留全文，multipart与二进制按块计算元信息。"""
    if is_card_multipart(content_type):
        return _card_multipart_body(content, content_type, complete=complete)
    media_type = content_type.split(";", 1)[0].strip().lower()
    is_text = not media_type or media_type.startswith("text/") or media_type in {
        "application/json", "application/xml", "application/x-www-form-urlencoded",
    } or media_type.endswith(("+json", "+xml"))
    if not is_text:
        digest = hashlib.sha256()
        size = 0
        for chunk in _card_body_chunks(content):
            size += len(chunk)
            digest.update(chunk)
        return {"field_name": None, "filename": None, "content_type": content_type, "size": size, "sha256": digest.hexdigest()}
    content = b"".join(_card_body_chunks(content))
    try:
        text = content.decode("utf-8")
    except UnicodeError:
        return _binary_body(content, content_type)
    return text


class _CardBodyBuffer:
    """请求级磁盘缓冲：限制实际接收大小，为原路由重放相同字节并提供完整审计。"""

    def __init__(self, buffer: BinaryIO, request: Request):
        """保存临时文件与原请求；不创建常驻资源，文件由路由上下文自动关闭。"""
        self.buffer = buffer
        self.request = request
        self.size = 0
        self.received_size = 0
        self.complete = False
        self.digest = hashlib.sha256()
        self.rejection = None
        self.replayed_size = 0
        self.replayed_complete = False

    async def capture(self) -> None:
        """按实际字节数读取到有界磁盘文件；超限立即拒绝，不继续读取剩余上传。"""
        message = f"卡券请求体不能超过{CARD_REQUEST_MAX_BYTES / (1024 * 1024):g}MB，请减少提交内容后重试"
        for declared in self.request.headers.getlist("content-length"):
            declared = declared.strip().lstrip("0") or "0"
            maximum = str(CARD_REQUEST_MAX_BYTES)
            # 不把攻击者提供的超长数字转为 int，也不能只相信声明而略过实际计数。
            if declared.isascii() and declared.isdecimal() and (
                len(declared) > len(maximum) or (len(declared) == len(maximum) and declared > maximum)
            ):
                raise ValueError(message)
        content_type = self.request.headers.get("content-type", "")
        try:
            parser = CardMultipartParser(content_type) if is_card_multipart(content_type) else None
            async for chunk in self.request.stream():
                self.received_size += len(chunk)
                # memoryview 落盘不复制整个巨型 ASGI 块；预检最多复制64KiB且不保存字段文本。
                retained = memoryview(chunk)[:max(0, CARD_REQUEST_MAX_BYTES - self.size)]
                if retained:
                    await run_in_threadpool(self.buffer.write, retained)
                    self.size += len(retained)
                    self.digest.update(retained)
                    if parser is not None:
                        for offset in range(0, len(retained), CARD_BODY_CHUNK_BYTES):
                            await run_in_threadpool(parser.feed, bytes(retained[offset:offset + CARD_BODY_CHUNK_BYTES]))
                if self.received_size > CARD_REQUEST_MAX_BYTES:
                    raise ValueError(message)
            if parser is not None:
                await run_in_threadpool(parser.finish)
            self.complete = True
        except CardMultipartError as exc:
            self.rejection = {**exc.details, "message": str(exc)}
            raise

    def audit(self) -> Any:
        """从磁盘解析请求审计；未完整接收时明确标注前缀、实际观察长度与拒绝上限。"""
        self.buffer.seek(0)
        body = _card_request_body(self.buffer, self.request.headers.get("content-type", ""), complete=self.complete)
        self.buffer.seek(0)
        if self.complete:
            return body
        result = {"received_body": body, "read_status": {
            "complete": False, "received_size": self.received_size, "buffered_size": self.size,
            "sha256": self.digest.hexdigest(), "sha256_scope": "已缓冲请求前缀",
            "declared_content_lengths": self.request.headers.getlist("content-length"),
            "max_size": CARD_REQUEST_MAX_BYTES,
        }}
        if self.rejection is not None:
            result["rejection"] = self.rejection
        return result

    def audit_failure(self, exc: Exception) -> dict:
        """审计本身异常时记录可信的接收计量；不能覆盖首次拒绝，也不能假称完整正文。"""
        return {"audit_error": {"type": type(exc).__name__, "message": str(exc)},
                "read_status": {"complete": False, "received_size": self.received_size,
                                "buffered_size": self.size, "sha256": self.digest.hexdigest(),
                                "sha256_scope": "已缓冲请求前缀", "max_size": CARD_REQUEST_MAX_BYTES},
                "rejection": self.rejection}

    async def receive(self) -> dict:
        """按块重放原始请求供 FastAPI 解析；完成后保留原连接的断开检测能力。"""
        if self.replayed_complete:
            return await self.request.receive()
        chunk = await run_in_threadpool(self.buffer.read, CARD_BODY_CHUNK_BYTES)
        self.replayed_size += len(chunk)
        self.replayed_complete = self.replayed_size >= self.size
        return {"type": "http.request", "body": chunk, "more_body": not self.replayed_complete}


def _card_validation_details(value: Any) -> Any:
    """记录完整校验明细；二进制输入改记元信息，避免异常 repr 泄出文件字节。"""
    if isinstance(value, bytes):
        return _binary_body(value, "application/octet-stream")
    if isinstance(value, dict):
        return {key: _card_validation_details(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_card_validation_details(item) for item in value]
    return value if isinstance(value, (str, int, float, bool, type(None))) else str(value)


def _card_request_origin(request: Request) -> dict:
    """分别记录连接对端和代理声明；现有公共 IP 工具未经可信校验，结果仅标为声明。"""
    peer = request.client
    if peer is None:
        connection_peer = "unknown"
    else:
        host = f"[{peer.host}]" if ":" in peer.host else peer.host
        connection_peer = f"{host}:{peer.port}"
    return {
        "connection_peer": connection_peer,
        "client_ip_claim": get_client_ip(request),
        "x_forwarded_for": request.headers.get("x-forwarded-for", ""),
        "x_real_ip": request.headers.get("x-real-ip", ""),
    }


def _write_card_log(level: str, message: str, entry: dict, exc: Exception | None = None) -> None:
    """安全写入卡券审计日志，保留非法 Unicode 的转义及完整异常链。

    Args:
        level: 日志级别；message: 固定中文操作名称；entry: 完整日志字段。
        exc: 可选异常，其原始类型、消息和完整堆栈追加到日志字段。
    Returns:
        无返回值；同一记录由现有控制台、业务及错误日志配置输出。
    """
    details = dict(entry)
    if exc is not None:
        details.update(exception_type=type(exc).__name__, exception_message=str(exc),
                       exception_traceback="".join(format_exception(exc)))
    # 只转义不能以 UTF-8 编码的代理码；中文和 emoji 原样保留，不丢弃字段。
    serialized = json.dumps(details, ensure_ascii=False, separators=(",", ":"))
    serialized = serialized.encode("utf-8", errors="backslashreplace").decode("utf-8")
    # 堆栈已完整纳入安全 JSON，不能再让 Loguru 追加含原始代理码的异常文本。
    logger.opt(exception=None).log(level, "{}: {}", message, serialized)


def _log_card_response(request: Request, response, request_id: str, body: Any, exc=None) -> None:
    """统一记录卡券结果及完整失败上下文；已知拒绝 WARNING，未预期异常 ERROR 双写。"""
    response_body = getattr(response, "body", b"")
    payload = json.loads(response_body) if response.media_type == "application/json" and response_body else None
    failed = exc is not None or response.status_code >= 400 or (
        isinstance(payload, dict) and payload.get("success") is False
    )
    entry = {
        "request_id": request_id, "operation": "cards", "result": "failure" if failed else "success",
        "method": request.method, "url": str(request.url), "path": request.url.path,
        "query": list(request.query_params.multi_items()), "origin": _card_request_origin(request),
        "response_status": response.status_code,
        "business_code": payload.get("code") if isinstance(payload, dict) else None,
    }
    if failed:
        entry.update({
            "request_headers": [(name.decode("latin-1"), value.decode("latin-1")) for name, value in request.scope["headers"]],
            "request_body": body,
            "response_headers": [(name.decode("latin-1"), value.decode("latin-1")) for name, value in response.raw_headers],
            "response_body": response_body.decode("utf-8", errors="backslashreplace"),
            "exception_type": type(exc).__name__ if exc is not None else None,
            "exception_message": "卡券请求参数校验失败" if isinstance(exc, RequestValidationError) else (str(exc) if exc is not None else None),
        })
        if isinstance(exc, RequestValidationError):
            entry["validation_errors"] = _card_validation_details(exc.errors())
    level = "ERROR" if exc is not None and not isinstance(exc, (RequestValidationError, HTTPException, ValueError)) else ("WARNING" if failed else "INFO")
    # 同一 loguru 记录交给既有控制台/文件配置；ERROR 自然进入正常与错误两类 sink。
    _write_card_log(level, "卡券请求结果", entry, exc if level == "ERROR" else None)


class CardAPIRoute(APIRoute):
    """为卡券接口统一成功响应及可预期业务错误，不改变其他模块路由。"""

    def get_route_handler(self) -> Callable:
        """包装原请求处理器；无参数，返回处理当前请求的异步函数。"""
        handler = super().get_route_handler()

        async def handle(request: Request):
            """处理卡券请求，返回 HTTP 200 的统一响应，权限与参数错误明确反馈。"""
            request_id = uuid4().hex
            body = None
            failure = None
            try:
                # 不调用 request.body()：multipart 文件始终按块落盘，未认证请求也有上限。
                with TemporaryFile() as buffer:
                    captured = _CardBodyBuffer(buffer, request)
                    capture_failure = None
                    try:
                        await captured.capture()
                    except Exception as exc:
                        capture_failure = exc
                        raise
                    finally:
                        try:
                            body = await run_in_threadpool(captured.audit)
                        except Exception as audit_error:
                            if capture_failure is None:
                                raise
                            body = captured.audit_failure(audit_error)
                            _write_card_log("ERROR", "卡券拒绝后的请求审计失败", {
                                "request_id": request_id, "rejection": str(capture_failure),
                                "audit_error": str(audit_error),
                            }, audit_error)
                    replay = Request(request.scope, receive=captured.receive)
                    response = await handler(replay)
                if response.media_type == "application/json" and hasattr(response, "body"):
                    normalized = JSONResponse(_card_response(json.loads(response.body)), status_code=200)
                    # raw_headers 保留多个 Set-Cookie 等重复响应头，不改变后台任务。
                    normalized.raw_headers.extend((name, value) for name, value in response.raw_headers if name not in {b"content-length", b"content-type"})
                    normalized.background = response.background
                    response = normalized
            except RequestValidationError as exc:
                failure = exc
                response = JSONResponse(ApiResponse(
                    success=False, code=40001, message="卡券请求参数格式错误，请检查后重试", data=None,
                ).model_dump(), status_code=200)
            except (HTTPException, ValueError) as exc:
                failure = exc
                message = str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
                message = {
                    "Not authenticated": "请先登录后再操作",
                    "Could not validate credentials": "登录状态无效，请重新登录",
                    "Inactive user": "当前账号已停用",
                    "Admin privileges required": "此操作仅限管理员",
                }.get(message, message)
                # 认证失效沿用客户端刷新令牌所识别的业务码，对象越权仍返回 40001。
                code = exc.status_code if isinstance(exc, HTTPException) and exc.status_code in {401, 403} else 40001
                result = ApiResponse(success=False, code=code, message=message, data=None).model_dump()
                result["detail"] = message
                headers = exc.headers if isinstance(exc, HTTPException) else None
                response = JSONResponse(result, status_code=200, headers=headers)
            except Exception as exc:
                failure = exc
                # 沿用全局异常处理器的响应契约，同时补齐本次请求的完整失败日志。
                message = get_public_database_error_message(exc) or f"服务器内部错误: {exc}"
                response = JSONResponse(ApiResponse(success=False, code=500, message=message, data=None).model_dump(), status_code=200)
            _log_card_response(request, response, request_id, body, failure)
            return response

        return handle


async def get_card_service(session: AsyncSession = Depends(deps.get_db_session)) -> CardService:
    """依赖注入当前请求的卡券服务；参数为数据库会话，返回服务实例。"""
    return CardService(session)


def _validate_card_payload(data: Any, *, validate_fee_payer: bool = True) -> Optional[str]:
    """校验卡券请求负载的公共逻辑。

    被 create_card / update_card / batch_save_card 三处共用，避免多处重复
    书写多规格、图片数量、手续费支付方式三块同样的校验代码。

    Args:
        data: ``CardCreate`` / ``CardUpdate`` / ``BatchSaveCardRequest`` 实例，
            需拥有 ``is_multi_spec`` / ``spec_name`` / ``spec_value`` /
            ``image_urls`` / ``is_dockable`` / ``fee_payer`` 这些字段。
        validate_fee_payer: 是否对 ``is_dockable`` 与 ``fee_payer`` 执行校验。
            默认开启；批量保存接口历史上不做该校验，由调用方传 ``False``
            以保持原有行为，避免意外重收紧。

    Returns:
        首个不通过项的中文错误消息，可直接作为 HTTPException ``detail`` 或
        ApiResponse ``message``；全部通过返回 ``None``。
    """
    if data.is_multi_spec:
        if not data.spec_name or not data.spec_value:
            return "多规格卡券必须提供规格名称和规格值"

    if data.image_urls and len(data.image_urls) > 3:
        return "最多只能上传3张图片"

    if validate_fee_payer:
        if data.is_dockable and not data.fee_payer:
            return "勾选可对接时，手续费支付方式必选"
        if data.fee_payer and data.fee_payer not in ('distributor', 'dealer'):
            return "手续费支付方式无效"

    return None
