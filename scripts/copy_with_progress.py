"""
带进度显示的目录复制工具

用法: python scripts/copy_with_progress.py <源目录> <目标目录>
"""
import os
import sys
import shutil


def copy_dir_with_progress(src, dst):
    """复制目录并实时显示进度"""
    # 先统计总文件数
    total = 0
    for root, dirs, files in os.walk(src):
        total += len(files)

    if total == 0:
        print("  没有文件需要复制")
        return

    # 清理目标目录
    if os.path.exists(dst):
        shutil.rmtree(dst)

    # 逐文件复制并显示进度
    copied = 0
    for root, dirs, files in os.walk(src):
        rel_dir = os.path.relpath(root, src)
        dst_dir = os.path.join(dst, rel_dir)
        os.makedirs(dst_dir, exist_ok=True)

        for f in files:
            copied += 1
            src_file = os.path.join(root, f)
            dst_file = os.path.join(dst_dir, f)
            shutil.copy2(src_file, dst_file)

            # 显示进度
            pct = int(copied * 100 / total)
            bar_len = 30
            filled = int(bar_len * copied / total)
            bar = '=' * filled + '-' * (bar_len - filled)
            short_name = os.path.relpath(src_file, src)
            if len(short_name) > 50:
                short_name = '...' + short_name[-47:]
            sys.stdout.write(f'\r  [{bar}] {pct}% ({copied}/{total}) {short_name:<50}')
            sys.stdout.flush()

    sys.stdout.write('\n')
    print(f"  Done! Copied {copied} files.")


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python copy_with_progress.py <src> <dst>")
        sys.exit(1)
    copy_dir_with_progress(sys.argv[1], sys.argv[2])
