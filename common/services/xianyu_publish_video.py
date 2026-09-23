"""
闲鱼接口发布的视频上传服务。

功能：
1. 按闲鱼媒体 SDK 的 bizConfig/init/second/complete 流程申请视频上传策略；
2. 使用 OSS 预签名地址分片上传本地视频并校验每片 ETag；
3. 将完成接口返回的 fileId、ossUrl 和视频尺寸转换为发布载荷。
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import mimetypes
import os
import re
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import aiohttp
import cv2
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA
from loguru import logger

from common.services.xianyu_mtop import mtop_call
from common.services.xianyu_publish_media import PublishMediaError, upload_publish_image_content


VIDEO_BIZ_CODE = "s_upload_xy_shequ"
VIDEO_USER_SITE = 77
VIDEO_APP_KEY = "12574478"
VIDEO_SDK_VERSION = "0.6.3"
VIDEO_CONFIG_URL = "https://upload.media.aliyun.com/api/gateway/bizConfig"
SELLER_ORIGIN = "https://seller.goofish.com"
SELLER_REFERER = "https://seller.goofish.com/?site=COMMONPRO"
VIDEO_MTOP_PARAMS = {"preventFallback": "true", "dataType": "jsonp"}
VIDEO_TIMEOUT = aiohttp.ClientTimeout(total=90)
DEFAULT_SLICE_SIZE = 2 * 1024 * 1024
MAX_PART_RETRIES = 3


class PublishVideoError(RuntimeError):
    """视频读取、授权、分片上传或完成接口异常。"""

    def __init__(self, message: str, *, account_invalid: bool = False) -> None:
        super().__init__(message)
        self.account_invalid = account_invalid


def _text(value: Any) -> str:
    """把接口字段转换为去除首尾空白的字符串。"""
    return str(value).strip() if value is not None else ""


def _resolve_video_path(value: str, static_root: Path | None) -> Path:
    """解析 /static 视频路径或本地绝对路径。"""
    normalized = value.strip()
    if normalized.startswith("/static/") or normalized.startswith("static/"):
        relative = normalized.lstrip("/").replace("static/", "", 1)
        root = static_root
        if root is None:
            root = Path(__file__).resolve().parents[2] / "backend-web" / "static"
        return root / relative
    return Path(normalized).expanduser()


async def _read_video(video: dict[str, Any], static_root: Path | None) -> tuple[bytes, str, str]:
    """读取本地或远程视频内容，并返回字节、文件名和 MIME 类型。"""
    path_value = _text(video.get("path"))
    source = path_value or _text(video.get("url"))
    if not source:
        raise PublishVideoError("视频缺少本地路径或视频地址")
    if source.lower().startswith(("http://", "https://")):
        try:
            async with aiohttp.ClientSession(timeout=VIDEO_TIMEOUT) as session:
                async with session.get(source) as response:
                    content = await response.read()
                    if response.status != 200 or not content:
                        raise PublishVideoError(f"远程视频下载失败：HTTP {response.status}")
                    content_type = (response.headers.get("Content-Type") or "").split(";", 1)[0].strip()
            name = Path(urlparse(source).path).name or "publish-video.mp4"
            return content, name, content_type or mimetypes.guess_type(name)[0] or "video/mp4"
        except PublishVideoError:
            raise
        except (aiohttp.ClientError, OSError, TimeoutError) as exc:
            raise PublishVideoError(f"远程视频下载失败：{exc}") from exc
    path = _resolve_video_path(source, static_root)
    if not path.is_file():
        raise PublishVideoError(f"视频文件不存在：{path}")
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise PublishVideoError(f"读取视频失败：{path}，{exc}") from exc
    if not content:
        raise PublishVideoError(f"视频文件为空：{path}")
    return content, path.name, mimetypes.guess_type(path.name)[0] or "video/mp4"


def _video_dimensions(content: bytes) -> tuple[int, int]:
    """从 MP4/MOV 的 tkhd 盒读取视频宽高（16.16 定点数）。"""
    marker = b"tkhd"
    start = 0
    while True:
        index = content.find(marker, start)
        if index < 0:
            return 0, 0
        box_start = index - 4
        if box_start >= 0 and index + 84 <= len(content):
            version = content[index + 4]
            width_offset = index + (80 if version == 0 else 92)
            if width_offset + 8 <= len(content):
                width = int.from_bytes(content[width_offset:width_offset + 4], "big") >> 16
                height = int.from_bytes(content[width_offset + 4:width_offset + 8], "big") >> 16
                if width > 0 and height > 0:
                    return width, height
        start = index + len(marker)


def _extract_video_cover_sync(content: bytes, suffix: str) -> tuple[bytes, int, int]:
    """从本地视频首帧生成 JPEG 封面并读取其宽高。"""
    fd, temporary_name = tempfile.mkstemp(suffix=suffix or ".mp4")
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(content)
        capture = cv2.VideoCapture(str(temporary_path))
        try:
            success, frame = capture.read()
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        finally:
            capture.release()
        if not success or frame is None or width <= 0 or height <= 0:
            raise PublishVideoError("无法读取视频首帧，请使用可正常播放的视频文件")
        encoded, cover = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        if not encoded:
            raise PublishVideoError("生成视频封面失败")
        return cover.tobytes(), width, height
    finally:
        temporary_path.unlink(missing_ok=True)


async def _extract_video_cover(content: bytes, name: str) -> tuple[bytes, int, int]:
    """在线程中提取视频首帧，避免阻塞接口事件循环。"""
    return await asyncio.to_thread(_extract_video_cover_sync, content, Path(name).suffix)


async def _upload_video_cover(content: bytes, name: str, cookie: str) -> str:
    """上传视频首帧封面并返回闲鱼图片地址。"""
    try:
        cover_item = await upload_publish_image_content(
            content,
            f"{Path(name).stem}_cover.jpg",
            cookie,
            content_type="image/jpeg",
            source=f"视频封面:{name}",
        )
    except PublishMediaError as exc:
        raise PublishVideoError(f"视频封面上传失败：{exc}") from exc
    return _text(cover_item.get("url"))


def _strategy_model(response: dict[str, Any]) -> dict[str, Any]:
    """提取 mtop 响应中的 model。"""
    raw = response.get("res") if isinstance(response, dict) else None
    model = raw.get("data", {}).get("model") if isinstance(raw, dict) else None
    if not isinstance(model, dict):
        raise PublishVideoError(f"闲鱼视频接口返回缺少 model：{response.get('error') or raw}")
    return model


def _log_mtop_response(stage: str, account_id: str, response: dict[str, Any]) -> None:
    """记录视频上传 mtop 接口的完整原始返回，不记录 Cookie。"""
    logger.info(
        f"闲鱼视频上传{stage}完整返回: account_id={account_id}, "
        f"success={response.get('success')}, response="
        f"{json.dumps(response.get('res'), ensure_ascii=False, default=str)}"
    )


def _parse_slice_size(value: Any) -> int:
    """把策略中的 MB 分片大小转换为字节。"""
    if value is None:
        return DEFAULT_SLICE_SIZE
    match = re.search(r"[0-9]+(?:\.[0-9]+)?", _text(value))
    if not match:
        return DEFAULT_SLICE_SIZE
    return max(256 * 1024, int(float(match.group()) * 1024 * 1024))


def _public_key(value: str) -> RSA.RsaKey:
    """兼容 PEM、公钥 base64 和带转义换行的 RSA 公钥。"""
    key_text = value.replace("\\n", "\n").strip()
    try:
        return RSA.import_key(key_text)
    except (ValueError, IndexError, TypeError):
        try:
            der = base64.b64decode(key_text)
            return RSA.import_key(der)
        except (ValueError, IndexError, TypeError, base64.binascii.Error) as exc:
            raise PublishVideoError("闲鱼视频上传授权返回的 RSA 公钥无效") from exc


def _encrypt_second_upload(public_key: str, content: bytes, file_size: int) -> str:
    """按官方 SDK 使用 RSA PKCS#1 v1.5 加密整体 MD5 和文件大小。"""
    plain = json.dumps(
        {"md5": hashlib.md5(content).hexdigest().upper(), "fileSize": file_size},
        separators=(",", ":"),
    ).encode("utf-8")
    cipher = PKCS1_v1_5.new(_public_key(public_key))
    encrypted = cipher.encrypt(plain)
    return base64.b64encode(encrypted).decode("ascii")


async def _fetch_biz_config(cookie: str) -> dict[str, Any]:
    """获取闲鱼媒体上传接口映射。"""
    params = {"bizCode": VIDEO_BIZ_CODE, "userSite": str(VIDEO_USER_SITE)}
    headers = {
        "Accept": "application/json",
        "Cookie": cookie,
        "Origin": SELLER_ORIGIN,
        "Referer": SELLER_REFERER,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/146.0.0.0 Safari/537.36",
    }
    try:
        async with aiohttp.ClientSession(timeout=VIDEO_TIMEOUT, cookie_jar=aiohttp.DummyCookieJar()) as session:
            async with session.get(VIDEO_CONFIG_URL, params=params, headers=headers) as response:
                text = await response.text()
                logger.info(f"闲鱼视频上传配置完整返回: http_status={response.status}, response={text}")
                if response.status != 200:
                    raise PublishVideoError(f"获取视频上传配置失败：HTTP {response.status}")
                body = json.loads(text)
    except PublishVideoError:
        raise
    except (aiohttp.ClientError, OSError, TimeoutError, ValueError) as exc:
        raise PublishVideoError(f"获取视频上传配置失败：{exc}") from exc
    config = body.get("data") if isinstance(body, dict) else None
    if not isinstance(config, dict) or not isinstance(config.get("apiInfo"), dict):
        raise PublishVideoError("视频上传配置缺少 API 映射")
    return config


async def _put_part(url: str, content: bytes, part_number: int) -> str:
    """上传一个 OSS 分片并返回 ETag/本地 MD5。"""
    local_md5 = hashlib.md5(content).hexdigest().upper()
    headers = {
        "Accept": "*/*",
        "Origin": SELLER_ORIGIN,
        "Referer": SELLER_REFERER,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/146.0.0.0 Safari/537.36",
    }
    last_error = ""
    for attempt in range(1, MAX_PART_RETRIES + 1):
        try:
            async with aiohttp.ClientSession(timeout=VIDEO_TIMEOUT, cookie_jar=aiohttp.DummyCookieJar()) as session:
                async with session.put(url, data=content, headers=headers) as response:
                    response_text = await response.text()
                    logger.info(
                        f"闲鱼视频分片上传完整返回: part={part_number}, attempt={attempt}, "
                        f"http_status={response.status}, etag={response.headers.get('ETag')}, response={response_text}"
                    )
                    if 200 <= response.status < 300:
                        etag = _text(response.headers.get("ETag")).strip('"')
                        return etag or local_md5
                    last_error = f"HTTP {response.status}"
        except (aiohttp.ClientError, OSError, TimeoutError) as exc:
            last_error = str(exc)
        if attempt < MAX_PART_RETRIES:
            await asyncio.sleep(0.5 * attempt)
    raise PublishVideoError(f"第 {part_number} 个视频分片上传失败：{last_error}")


async def upload_publish_video(
    video: dict[str, Any],
    cookie: str,
    account_id: str,
    owner_id: int | None = None,
    *,
    static_root: str | Path | None = None,
) -> tuple[dict[str, Any], str]:
    """上传一个视频并返回发布载荷及可能刷新后的 Cookie。"""
    root = Path(static_root) if static_root else None
    content, name, mime_type = await _read_video(video, root)
    try:
        width = int(video.get("width") or 0)
        height = int(video.get("height") or 0)
    except (TypeError, ValueError):
        width, height = 0, 0
    if not width or not height:
        width, height = _video_dimensions(content)
    cover_content, cover_width, cover_height = await _extract_video_cover(content, name)
    width = width or cover_width
    height = height or cover_height

    config = await _fetch_biz_config(cookie)
    api_info = config["apiInfo"]
    init_api = _text(api_info.get("init")) or "mtop.video.upload.init.xianyu"
    init_result = await mtop_call(
        account_id=account_id,
        cookies_str=cookie,
        api=init_api,
        version="1.0",
        app_key=VIDEO_APP_KEY,
        data={
            "bizCode": VIDEO_BIZ_CODE,
            "fileSize": len(content),
            "mimeType": mime_type,
            "localFileName": name,
            "sdkVersion": VIDEO_SDK_VERSION,
            "userSite": VIDEO_USER_SITE,
        },
        owner_id=owner_id,
        origin=SELLER_ORIGIN,
        referer=SELLER_REFERER,
        extra_params=VIDEO_MTOP_PARAMS,
        extra_headers={"idle_site_biz_code": "COMMONPRO"},
        request_method="GET",
    )
    _log_mtop_response("初始化", account_id, init_result)
    if not init_result.get("success"):
        raise PublishVideoError(
            f"视频上传初始化失败：{init_result.get('error') or '未知错误'}",
            account_invalid=bool(init_result.get("account_invalid")),
        )
    cookie = init_result.get("cookies_str") or cookie
    strategy = _strategy_model(init_result)
    nested_strategy = strategy.get("uploadStrategy")
    upload_strategy = {**strategy, **nested_strategy} if isinstance(nested_strategy, dict) else strategy
    upload_id = _text(upload_strategy.get("uploadId"))
    upload_urls = upload_strategy.get("uploadUrlList")
    policy = upload_strategy.get("videoUploadPolicy") if isinstance(upload_strategy.get("videoUploadPolicy"), dict) else {}
    if not upload_id or not isinstance(upload_urls, list) or not upload_urls:
        raise PublishVideoError("视频上传初始化未返回 uploadId 或分片地址")

    support_second = str(policy.get("supportSecondTransfer", "false")).lower() == "true" or policy.get("supportSecondTransfer") is True
    if support_second and _text(upload_strategy.get("publicKey")) and _text(upload_strategy.get("requestId")):
        second_result = await mtop_call(
            account_id=account_id,
            cookies_str=cookie,
            api=_text(api_info.get("second")) or "mtop.video.second.upload.xianyu",
            version="1.0",
            app_key=VIDEO_APP_KEY,
            data={
                "bizCode": VIDEO_BIZ_CODE,
                "authorization": _encrypt_second_upload(_text(upload_strategy["publicKey"]), content, len(content)),
                "requestId": _text(upload_strategy["requestId"]),
                "uploadId": upload_id,
                "sdkVersion": VIDEO_SDK_VERSION,
                "userSite": VIDEO_USER_SITE,
            },
            owner_id=owner_id,
            origin=SELLER_ORIGIN,
            referer=SELLER_REFERER,
            extra_params=VIDEO_MTOP_PARAMS,
        )
        _log_mtop_response("秒传检查", account_id, second_result)
        cookie = second_result.get("cookies_str") or cookie
        if second_result.get("success"):
            second_model = _strategy_model(second_result)
            if second_model.get("secondUpload") is True:
                file_id = _text(second_model.get("fileId"))
                oss_url = _text(second_model.get("ossUrl"))
                if file_id and oss_url:
                    cover_url = await _upload_video_cover(cover_content, name, cookie)
                    return _video_payload(video, file_id, oss_url, width, height, cover_url), cookie
        else:
            logger.warning(f"闲鱼视频秒传检查失败，继续分片上传：account_id={account_id}, error={second_result.get('error')}")

    slice_size = _parse_slice_size(policy.get("sliceSize"))
    chunks = [content[offset:offset + slice_size] for offset in range(0, len(content), slice_size)]
    if len(chunks) > len(upload_urls):
        raise PublishVideoError(f"视频分片数量超过授权上限：需要 {len(chunks)} 片，仅返回 {len(upload_urls)} 个地址")

    try:
        max_parallel = max(1, min(int(policy.get("concurrentSliceNum") or 3), 8))
    except (TypeError, ValueError):
        max_parallel = 3
    semaphore = asyncio.Semaphore(max_parallel)

    async def upload_one(index: int) -> tuple[int, str]:
        entry = upload_urls[index]
        url = _text(entry.get("url") if isinstance(entry, dict) else entry)
        if not url:
            raise PublishVideoError(f"第 {index + 1} 个视频分片地址为空")
        async with semaphore:
            return index + 1, await _put_part(url, chunks[index], index + 1)

    started = asyncio.get_running_loop().time()
    results = await asyncio.gather(*(upload_one(index) for index in range(len(chunks))))
    part_list = json.dumps(
        [json.dumps({"partNumber": number, "md5": md5}, separators=(",", ":")) for number, md5 in sorted(results)],
        separators=(",", ":"),
    )
    elapsed = max(asyncio.get_running_loop().time() - started, 0.001)
    net_speed = len(content) / 1024 / elapsed
    keep_alive_api = _text(api_info.get("keepAlive"))
    if keep_alive_api:
        keep_alive_result = await mtop_call(
            account_id=account_id,
            cookies_str=cookie,
            api=keep_alive_api,
            version="1.0",
            app_key=VIDEO_APP_KEY,
            data={"userSite": VIDEO_USER_SITE},
            owner_id=owner_id,
            origin=SELLER_ORIGIN,
            referer=SELLER_REFERER,
            extra_params=VIDEO_MTOP_PARAMS,
            request_method="GET",
        )
        _log_mtop_response("会话保活", account_id, keep_alive_result)
        cookie = keep_alive_result.get("cookies_str") or cookie
        if not keep_alive_result.get("success"):
            logger.warning(
                f"闲鱼视频上传会话保活失败，继续调用完成接口："
                f"account_id={account_id}, error={keep_alive_result.get('error')}"
            )
    complete_result = await mtop_call(
        account_id=account_id,
        cookies_str=cookie,
        api=_text(api_info.get("complete")) or "mtop.video.upload.complete.xianyu",
        version="1.0",
        app_key=VIDEO_APP_KEY,
        data={
            "bizCode": VIDEO_BIZ_CODE,
            "uploadId": upload_id,
            "partList": part_list,
            "netSpeed": net_speed,
            "sdkVersion": VIDEO_SDK_VERSION,
            "userSite": VIDEO_USER_SITE,
        },
        owner_id=owner_id,
        origin=SELLER_ORIGIN,
        referer=SELLER_REFERER,
        extra_params=VIDEO_MTOP_PARAMS,
    )
    _log_mtop_response("完成", account_id, complete_result)
    cookie = complete_result.get("cookies_str") or cookie
    if not complete_result.get("success"):
        raise PublishVideoError(
            f"视频上传完成接口失败：{complete_result.get('error') or '未知错误'}",
            account_invalid=bool(complete_result.get("account_invalid")),
        )
    model = _strategy_model(complete_result)
    file_id = _text(model.get("fileId"))
    oss_url = _text(model.get("ossUrl"))
    if not file_id or not oss_url:
        raise PublishVideoError("视频上传完成接口未返回 fileId 或 ossUrl")
    cover_url = await _upload_video_cover(cover_content, name, cookie)
    return _video_payload(video, file_id, oss_url, width, height, cover_url), cookie


def _video_payload(
    video: dict[str, Any],
    file_id: str,
    oss_url: str,
    width: int,
    height: int,
    uploaded_cover_url: str | None = None,
) -> dict[str, Any]:
    """构造 idleitem.publish 所需的视频对象。"""
    poster = _text(video.get("thumbnail_url") or video.get("cover_url") or uploaded_cover_url)
    if not poster.lower().startswith(("http://", "https://")):
        poster = oss_url
    return {
        "heightSize": height,
        "widthSize": width,
        "major": True,
        "mediaCloudFileId": file_id,
        "type": 10000,
        "url": poster,
        "videoMD5": "0000",
        "videoObject": "",
        "videoUrl": oss_url,
    }


async def upload_publish_videos(
    videos: list[Any],
    cookie: str,
    account_id: str,
    owner_id: int | None = None,
    *,
    static_root: str | Path | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """按顺序上传视频，返回视频发布对象和刷新后的 Cookie。"""
    payloads: list[dict[str, Any]] = []
    current_cookie = cookie
    for index, video in enumerate(videos[:3], 1):
        if not isinstance(video, dict):
            raise PublishVideoError(f"第 {index} 个视频格式不正确")
        payload, current_cookie = await upload_publish_video(
            video,
            current_cookie,
            account_id,
            owner_id,
            static_root=static_root,
        )
        payload["major"] = index == 1
        payloads.append(payload)
    return payloads, current_cookie


__all__ = ["PublishVideoError", "upload_publish_video", "upload_publish_videos"]
