"""
快速打包 ZIP（存储模式，不压缩）并显示进度

用法: python scripts/zip_with_progress.py <源目录> <输出zip路径>

说明: 使用 ZIP_STORED 模式（不压缩），速度极快。
      EXE/DLL/浏览器文件本身已是压缩格式，再压缩收益极小但耗时巨大。
"""
import os
import sys
import zipfile


def zip_dir_with_progress(src_dir, zip_path):
    """打包目录为 ZIP 并显示实时进度"""
    # 统计总文件数
    total = 0
    for root, dirs, files in os.walk(src_dir):
        total += len(files)

    if total == 0:
        print("  没有文件需要打包")
        return

    print(f"  Total files: {total}")

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zf:
        packed = 0
        for root, dirs, files in os.walk(src_dir):
            for f in files:
                packed += 1
                full_path = os.path.join(root, f)
                arc_name = os.path.relpath(full_path, src_dir)
                zf.write(full_path, arc_name)

                # 显示进度
                pct = int(packed * 100 / total)
                bar_len = 30
                filled = int(bar_len * packed / total)
                bar = '=' * filled + '-' * (bar_len - filled)
                sys.stdout.write(f'\r  [{bar}] {pct}% ({packed}/{total})')
                sys.stdout.flush()

    # 显示最终大小
    size_mb = os.path.getsize(zip_path) / 1024 / 1024
    sys.stdout.write('\n')
    print(f"  Done! {zip_path} ({size_mb:.1f} MB)")


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python zip_with_progress.py <src_dir> <output.zip>")
        sys.exit(1)
    zip_dir_with_progress(sys.argv[1], sys.argv[2])
