"""视频上传和编辑回填回归测试（仅访问本机 HTTP 服务，无需闲鱼账号）。

安装 backend-web 运行依赖后，在仓库根目录执行：
    python -m unittest discover -s tests -p test_xianyu_video.py -v
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend-web"))

from aiohttp import web

from app.services.xianyu_item_edit_mapper import _map_videos
from app.services.xianyu_item_payload_builder import build_item_payload
from app.services.xianyu_item_snapshot import snapshot_video_index
from common.services.xianyu_publish_video import _put_part


def platform_video(**identifiers):
    return {
        "type": "10000",
        "major": "true",
        "widthSize": "1920",
        "heightSize": "1080",
        "videoUrl": "https://example.invalid/video.mp4",
        "url": "https://example.invalid/cover.jpg",
        **identifiers,
    }


class VideoMappingTests(unittest.TestCase):
    def test_video_id_only_is_visible_in_edit_form(self):
        video = platform_video(videoId="123456789")

        mapped = _map_videos({"imageInfoDOList": [video]})

        self.assertEqual(len(mapped), 1)
        self.assertEqual(mapped[0]["file_id"], "123456789")
        self.assertEqual(mapped[0]["url"], video["videoUrl"])
        self.assertEqual((mapped[0]["width"], mapped[0]["height"]), (1920, 1080))

    def test_cloud_file_id_remains_supported(self):
        video = platform_video(mediaCloudFileId="cloud-file-id")

        mapped = _map_videos({"imageInfoDOList": [video]})
        index = snapshot_video_index({"imageInfoDOList": [video]})

        self.assertEqual(mapped[0]["file_id"], "cloud-file-id")
        self.assertEqual(index[mapped[0]["file_id"]]["mediaCloudFileId"], "cloud-file-id")

    def test_both_video_identifiers_reuse_the_same_snapshot(self):
        video = platform_video(mediaCloudFileId="cloud-file-id", videoId="123456789")
        original = copy.deepcopy(video)

        index = snapshot_video_index({"imageInfoDOList": [video]})

        self.assertIs(index["cloud-file-id"], index["123456789"])
        self.assertEqual(index["123456789"]["type"], 10000)
        self.assertIs(index["123456789"]["major"], True)
        self.assertEqual(video, original)


class VideoEditPayloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_video_id_is_preserved_without_upload(self):
        video = platform_video(videoId="123456789")
        image_url = "https://example.invalid/image.jpg"
        snapshot = {"imageInfoDOList": [video, {
            "type": "0", "major": "true", "url": image_url,
            "widthSize": "800", "heightSize": "600",
        }]}
        form = {
            "title": "测试商品", "description": "商品说明", "price": 9.99,
            "quantity": 2, "images": [image_url], "videos": _map_videos(snapshot),
        }
        no_upload = AsyncMock(side_effect=AssertionError("已有媒体不应重新上传"))
        with patch("app.services.xianyu_item_payload_builder._resolve_address", new=AsyncMock(return_value={})), \
             patch("app.services.xianyu_item_payload_builder.upload_publish_videos", new=no_upload), \
             patch("app.services.xianyu_item_payload_builder.upload_publish_image", new=no_upload):
            payload, _ = await build_item_payload(form, "", "test-account", None, snapshot=snapshot)

        videos = [item for item in payload["imageInfoDOList"] if item["type"] != 0]
        self.assertEqual(len(videos), 1)
        self.assertEqual(videos[0]["videoId"], "123456789")
        self.assertEqual(videos[0]["videoUrl"], video["videoUrl"])
        no_upload.assert_not_awaited()


class VideoUploadTests(unittest.IsolatedAsyncioTestCase):
    async def test_presigned_part_has_no_automatic_content_type(self):
        body = b"video upload regression fixture"
        etag = hashlib.md5(body).hexdigest().upper()
        observed = []

        async def upload_part(request):
            received = await request.read()
            observed.append((request.headers.get("Content-Type"), received))
            # OSS 拒绝签名中未包含的 Content-Type；在真实 HTTP 边界复现该条件。
            if request.headers.get("Content-Type"):
                return web.Response(status=403, text="<Error><Code>SignatureDoesNotMatch</Code></Error>")
            return web.Response(headers={"ETag": f'"{etag}"'})

        app = web.Application()
        app.router.add_put("/part", upload_part)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        try:
            port = runner.addresses[0][1]
            actual_etag = await _put_part(f"http://127.0.0.1:{port}/part", body, 1)
        finally:
            await runner.cleanup()

        self.assertEqual(observed, [(None, body)])
        self.assertEqual(actual_etag, etag)


if __name__ == "__main__":
    unittest.main()
