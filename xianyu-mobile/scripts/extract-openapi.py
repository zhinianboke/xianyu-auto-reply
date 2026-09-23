"""从 xianyu-auto-reply 后端提取 OpenAPI spec 到 JSON 文件。

用法:
  python scripts/extract-openapi.py [--url URL] [--output PATH]

默认尝试直接导入 FastAPI app 对象提取（无需数据库）。
如果导入失败，可用 --url 从运行中的后端拉取。
"""
import json
import sys
import urllib.request
from pathlib import Path

DEFAULT_URL = "http://localhost:8089/openapi.json"
DEFAULT_OUTPUT = str(Path(__file__).parent.parent / "api" / "generated" / "openapi.json")


def fetch_from_url(url: str) -> dict:
    """从运行中的后端拉取 OpenAPI spec。"""
    print(f"从 {url} 拉取 OpenAPI spec...")
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read())


def extract_from_app() -> dict:
    """直接导入 FastAPI app 对象提取 spec（无需数据库连接）。"""
    print("尝试直接导入 FastAPI app 提取 OpenAPI spec...")
    backend_dir = Path(__file__).parent.parent.parent / "xianyu-auto-reply" / "backend-web"
    project_root = backend_dir.parent
    sys.path.insert(0, str(backend_dir))
    sys.path.insert(0, str(project_root))

    # 设置最小环境变量，避免配置读取失败
    import os
    os.environ.setdefault("MYSQL_HOST", "localhost")
    os.environ.setdefault("MYSQL_PORT", "3306")
    os.environ.setdefault("MYSQL_DATABASE", "xianyu")
    os.environ.setdefault("MYSQL_USER", "root")
    os.environ.setdefault("MYSQL_PASSWORD", "dummy")
    os.environ.setdefault("REDIS_HOST", "localhost")
    os.environ.setdefault("REDIS_PORT", "6379")
    os.environ.setdefault("SECRET_KEY", "dummy-secret-for-openapi-extraction")

    from _bootstrap import app
    spec = app.openapi()
    print(f"成功提取 OpenAPI spec ({len(spec.get('paths', {}))} 个路径)")
    return spec


def main():
    import argparse
    parser = argparse.ArgumentParser(description="提取 OpenAPI spec")
    parser.add_argument("--url", default=None, help="运行中的后端 openapi.json URL")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="输出文件路径")
    args = parser.parse_args()

    spec = None

    # 优先从 URL 拉取（如果指定了 --url）
    if args.url:
        try:
            spec = fetch_from_url(args.url)
        except Exception as e:
            print(f"从 URL 拉取失败: {e}", file=sys.stderr)

    # 如果没有 URL 或 URL 拉取失败，尝试直接导入
    if spec is None:
        try:
            spec = extract_from_app()
        except Exception as e:
            print(f"直接导入提取失败: {e}", file=sys.stderr)
            if not args.url:
                print("\n提示: 后端未运行，可以指定 --url 从运行中的后端拉取:", file=sys.stderr)
                print(f"  python scripts/extract-openapi.py --url http://your-server:port/openapi.json", file=sys.stderr)
            sys.exit(1)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"OpenAPI spec 已保存到 {output}")


if __name__ == "__main__":
    main()
