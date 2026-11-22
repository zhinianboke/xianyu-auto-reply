"""卡券 multipart 增量限额与审计：接收预检和磁盘重读共用原始字节计量规则。"""
from __future__ import annotations

import hashlib
from typing import BinaryIO

from starlette.datastructures import Headers
from starlette.formparsers import multipart, parse_options_header

CARD_BODY_CHUNK_BYTES = 64 * 1024
CARD_MULTIPART_MAX_FIELDS = 1000
CARD_MULTIPART_MAX_FILES = 1000
CARD_MULTIPART_MAX_FIELD_BYTES = 1024 * 1024
CARD_MULTIPART_MAX_TEXT_BYTES = 4 * 1024 * 1024
CARD_MULTIPART_MAX_HEADERS = 32
CARD_MULTIPART_MAX_HEADER_BYTES = 8 * 1024
CARD_MULTIPART_MAX_PART_HEADER_BYTES = 16 * 1024
CARD_MULTIPART_MAX_METADATA_BYTES = 1024 * 1024
CARD_MULTIPART_PART_METADATA_BYTES = 256
CARD_MULTIPART_MAX_CONTENT_TYPE_BYTES = 4 * 1024
CARD_MULTIPART_MAX_BOUNDARY_BYTES = 200


class CardMultipartError(ValueError):
    """携带中文拒绝原因及真实限额计量，供统一业务响应和失败审计使用。"""

    def __init__(self, message: str, reason: str, *, limit=None, observed=None):
        """保存拒绝文案、类别和原始字节/对象计量；不保存请求体或创建资源。"""
        super().__init__(message)
        self.details = {"reason": reason, "limit": limit, "observed": observed}


def is_card_multipart(content_type: str) -> bool:
    """检查媒体类型是否为 multipart；参数为原始 Content-Type，返回布尔值。"""
    start = 0
    while start < len(content_type) and content_type[start].isspace():
        start += 1
    return content_type[start:start + 10].lower() == "multipart/"


def card_body_chunks(content: bytes | BinaryIO):
    """分片读取字节或磁盘缓冲；每次最多复制64 KiB，不复制完整大型 ASGI 块。"""
    if isinstance(content, bytes):
        for offset in range(0, len(content), CARD_BODY_CHUNK_BYTES):
            yield content[offset:offset + CARD_BODY_CHUNK_BYTES]
    else:
        while chunk := content.read(CARD_BODY_CHUNK_BYTES):
            yield chunk


def decode_card_multipart(content: bytes | bytearray, charset: str) -> str:
    """按 Starlette 的字符集与 latin-1 回退规则解码；返回完整的受限字段文本。"""
    try:
        return content.decode(charset)
    except (UnicodeDecodeError, LookupError):
        return content.decode("latin-1")


class CardMultipartParser:
    """共用有界解析器；预检不物化字段值/结果列表，审计仅保留限额内的真实内容。"""

    def __init__(self, content_type: str, *, collect: bool = False):
        """验证边界并初始化状态；collect 控制是否收集审计字段，非法请求明确拒绝。"""
        self.collect = collect
        self.content_type = content_type
        self.fields = []
        self.current = {}
        self.field_count = self.file_count = self.text_bytes = self.metadata_bytes = 0
        self.ended = False
        self.error = None
        # ASGI头按latin-1逐字节解码；先检查字符数，不能为超大头再复制完整编码内容。
        self._limit(len(content_type), CARD_MULTIPART_MAX_CONTENT_TYPE_BYTES, "content_type_bytes", "表单 Content-Type 不能超过4KiB")
        try:
            content_type.encode("latin-1")
            _, params = parse_options_header(content_type)
            self.charset = params.get(b"charset", b"utf-8").decode("latin-1")
            if "\x00" in self.charset:
                raise CardMultipartError("表单字符集格式无效", "invalid_content_type")
            boundary = params.get(b"boundary", b"")
            if not boundary or any(value < 32 or value > 126 for value in boundary) or boundary[-1:] == b" ":
                raise CardMultipartError("请求缺少有效的表单边界", "invalid_boundary")
            self._limit(len(boundary), CARD_MULTIPART_MAX_BOUNDARY_BYTES, "boundary_bytes", "表单边界不能超过200字节")
            self.parser = multipart.MultipartParser(boundary, {
                name: getattr(self, name) for name in (
                    "on_part_begin", "on_part_data", "on_part_end", "on_header_field",
                    "on_header_value", "on_header_end", "on_headers_finished", "on_end",
                )
            })
        except CardMultipartError:
            raise
        except Exception as exc:
            raise CardMultipartError(f"表单请求格式错误：{exc}", "invalid_content_type") from exc

    @staticmethod
    def _limit(observed: int, maximum: int, reason: str, message: str) -> None:
        """在分配或解码之前比较原始计量；刚好达到限额允许，超限携带观测值拒绝。"""
        if observed > maximum:
            raise CardMultipartError(message, reason, limit=maximum, observed=observed)

    def _add_metadata(self, size: int) -> None:
        """累计头、字段名、文件名及每part对象预算；超限时不保存新增元数据。"""
        observed = self.metadata_bytes + size
        self._limit(observed, CARD_MULTIPART_MAX_METADATA_BYTES, "metadata_bytes", "表单元数据累计不能超过1MiB")
        self.metadata_bytes = observed

    def on_part_begin(self) -> None:
        """初始化单part的有界临时状态；每part先计固定预算以防小字段对象放大。"""
        self.current = {}
        self._add_metadata(CARD_MULTIPART_PART_METADATA_BYTES)
        self.current = {
            "headers": [], "header_name": bytearray(), "header_value": bytearray(),
            "header_count": 0, "header_bytes": 0, "header_active": False,
            "data": bytearray() if self.collect else None, "size": 0, "finished": False,
        }

    def _header_data(self, key: str, data: bytes, start: int, end: int) -> None:
        """先校验头数量、单头及part头字节，再保存当前64KiB以内回调片段。"""
        current = self.current
        if not current["header_active"]:
            observed = current["header_count"] + 1
            self._limit(observed, CARD_MULTIPART_MAX_HEADERS, "part_headers", "每个表单部分最多允许32个头字段")
            current["header_count"], current["header_active"] = observed, True
        size = end - start
        self._limit(len(current["header_name"]) + len(current["header_value"]) + size,
                    CARD_MULTIPART_MAX_HEADER_BYTES, "header_bytes", "单个表单头字段不能超过8KiB")
        self._limit(current["header_bytes"] + size, CARD_MULTIPART_MAX_PART_HEADER_BYTES,
                    "part_header_bytes", "单个表单部分的头字段累计不能超过16KiB")
        self._add_metadata(size)
        current["header_bytes"] += size
        current[key].extend(data[start:end])

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        """接收分片原始头名；不提前解码或生成不受限字符串。"""
        self._header_data("header_name", data, start, end)

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        """接收分片原始头值；复用头限额而非另行实现计数。"""
        self._header_data("header_value", data, start, end)

    def on_header_end(self) -> None:
        """保存受限头；重复 Content-Disposition 取最后一项，与 Starlette 保持一致。"""
        current = self.current
        name, value = bytes(current["header_name"]).lower(), bytes(current["header_value"])
        current["headers"].append((name, value))
        if name == b"content-disposition":
            current["content_disposition"] = value
        current["header_name"].clear()
        current["header_value"].clear()
        current["header_active"] = False

    def on_headers_finished(self) -> None:
        """先校验字段/文件数量并计量名称字节，再按需生成审计字符串和文件摘要。"""
        current = self.current
        _, options = parse_options_header(current.get("content_disposition"))
        if b"name" not in options:
            raise CardMultipartError("表单 Content-Disposition 缺少 name 字段", "missing_field_name")
        is_file = b"filename" in options
        observed = (self.file_count if is_file else self.field_count) + 1
        maximum = CARD_MULTIPART_MAX_FILES if is_file else CARD_MULTIPART_MAX_FIELDS
        self._limit(observed, maximum, "files" if is_file else "fields",
                    "表单文件数量不能超过1000个" if is_file else "表单普通字段数量不能超过1000个")
        self._add_metadata(len(options[b"name"]) + len(options.get(b"filename", b"")))
        if is_file:
            self.file_count = observed
        else:
            self.field_count = observed
        current["is_file"] = is_file
        if self.collect:
            field_name = decode_card_multipart(options[b"name"], self.charset)
            if is_file:
                # 解码失败之前不公布半初始化文件状态，防止partial审计覆盖首次拒绝原因。
                filename = decode_card_multipart(options[b"filename"], self.charset)
                current["file"] = {
                    "field_name": field_name, "filename": filename,
                    "content_type": Headers(raw=current["headers"]).get("content-type"),
                    "size": 0,
                }
                current["digest"] = hashlib.sha256()
            current["field_name"] = field_name

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        """按原始字节计量普通字段；文件只在审计模式累计大小和SHA，不保留文件内容。"""
        current = self.current
        size = end - start
        if not current["is_file"]:
            self._limit(current["size"] + size, CARD_MULTIPART_MAX_FIELD_BYTES,
                        "field_bytes", "单个表单普通字段不能超过1MiB")
            self._limit(self.text_bytes + size, CARD_MULTIPART_MAX_TEXT_BYTES,
                        "text_bytes", "表单普通字段文本累计不能超过4MiB")
            self.text_bytes += size
            if self.collect:
                current["data"].extend(data[start:end])
        elif self.collect:
            current["file"]["size"] += size
            current["digest"].update(data[start:end])
        current["size"] += size

    def on_part_end(self) -> None:
        """只物化限额以内的完整part；预检模式不会创建结果字段字典。"""
        current = self.current
        if self.collect:
            if current["is_file"]:
                current["file"]["sha256"] = current["digest"].hexdigest()
                self.fields.append(current["file"])
            else:
                self.fields.append({"field_name": current["field_name"],
                                    "value": decode_card_multipart(current["data"], self.charset)})
        current["finished"] = True

    def on_end(self) -> None:
        """标记完整结束边界；不能将已接收但尚未结束的表单称为完整。"""
        self.ended = True

    def feed(self, chunk: bytes) -> None:
        """增量解析一个有界片段；保存首次拒绝原因并立即中止后续part物化。"""
        if self.error is not None:
            raise self.error
        try:
            self.parser.write(chunk)
        except Exception as exc:
            self.error = exc if isinstance(exc, CardMultipartError) else CardMultipartError(
                f"表单请求格式错误：{exc}", "invalid_multipart",
            )
            if self.error is exc:
                raise
            raise self.error from exc

    def finish(self) -> None:
        """验证结束边界；截断表单明确拒绝，不允许进入业务handler。"""
        if self.error is not None:
            raise self.error
        try:
            self.parser.finalize()
            if not self.ended:
                raise CardMultipartError("请求缺少有效的表单结束边界", "incomplete_multipart")
        except Exception as exc:
            self.error = exc if isinstance(exc, CardMultipartError) else CardMultipartError(
                f"表单请求格式错误：{exc}", "invalid_multipart",
            )
            if self.error is exc:
                raise
            raise self.error from exc

    def partial_fields(self) -> list:
        """返回已审计part及当前合法字段前缀；不把拒绝字段或未解析内容冒充完整数据。"""
        current = self.current
        partial = []
        if current.get("field_name") is not None and not current.get("finished"):
            if current.get("is_file"):
                partial.append({**current["file"], "sha256": current["digest"].hexdigest(), "complete": False})
            else:
                partial.append({"field_name": current["field_name"],
                                "value": decode_card_multipart(current["data"], self.charset),
                                "complete": False, "value_scope": "已解析字段前缀"})
        return self.fields + partial


def audit_card_multipart(content: bytes | BinaryIO, content_type: str, *, complete: bool = True) -> dict:
    """有界重读磁盘审计；拒绝后仅计算剩余已缓冲前缀SHA，不再解析/物化攻击字段。"""
    parser = None
    error = None
    size = 0
    digest = hashlib.sha256()
    try:
        parser = CardMultipartParser(content_type, collect=True)
    except CardMultipartError as exc:
        error = exc
    for chunk in card_body_chunks(content):
        size += len(chunk)
        digest.update(chunk)
        if error is None:
            try:
                parser.feed(chunk)
            except CardMultipartError as exc:
                error = exc
    if error is None:
        try:
            parser.finish()
        except CardMultipartError as exc:
            error = exc
    if error is None and complete:
        return {"fields": parser.fields, "multipart_defects": []}
    result = {
        "fields": parser.partial_fields() if parser is not None else [],
        "partial": True, "multipart_error": str(error) if error else "请求未完整接收",
        "body": {"field_name": None, "filename": None, "content_type": content_type,
                 "size": size, "sha256": digest.hexdigest(), "complete": complete,
                 "sha256_scope": "完整已缓冲请求体" if complete else "已缓冲请求前缀"},
    }
    if error is not None:
        result["rejection"] = error.details
    return result
