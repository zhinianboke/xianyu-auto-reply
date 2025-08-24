#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动安装Playwright依赖的脚本
"""

import subprocess
import sys
import os

def run_command(command, description):
    """运行命令并显示结果"""
    print(f"🔄 {description}...")
    print(f"执行命令: {command}")
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300  # 5分钟超时
        )
        
        if result.returncode == 0:
            print(f"✅ {description}成功")
            if result.stdout:
                print(f"输出: {result.stdout.strip()}")
        else:
            print(f"❌ {description}失败")
            print(f"错误: {result.stderr.strip()}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"⏰ {description}超时")
        return False
    except Exception as e:
        print(f"💥 {description}异常: {e}")
        return False
    
    return True

def check_playwright_installed():
    """检查Playwright是否已安装"""
    try:
        import playwright
        print(f"✅ Playwright已安装，版本: {playwright.__version__}")
        return True
    except ImportError:
        print("❌ Playwright未安装")
        return False

def check_browser_installed():
    """检查浏览器是否已安装"""
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
                browser.close()
                print("✅ Chromium浏览器已安装并可用")
                return True
            except Exception as e:
                print(f"❌ Chromium浏览器不可用: {e}")
                return False
                
    except ImportError:
        print("❌ 无法检查浏览器状态（Playwright未安装）")
        return False

def install_playwright():
    """安装Playwright"""
    print("🚀 开始安装Playwright...")
    
    # 1. 检查Python版本
    python_version = sys.version_info
    print(f"Python版本: {python_version.major}.{python_version.minor}.{python_version.micro}")
    
    if python_version < (3, 7):
        print("❌ Playwright需要Python 3.7或更高版本")
        return False
    
    # 2. 安装Playwright包
    if not run_command(
        f"{sys.executable} -m pip install playwright",
        "安装Playwright包"
    ):
        return False
    
    # 3. 安装浏览器
    if not run_command(
        f"{sys.executable} -m playwright install chromium",
        "安装Chromium浏览器"
    ):
        return False
    
    # 4. 安装系统依赖（Linux）
    if os.name == 'posix':  # Linux/macOS
        run_command(
            f"{sys.executable} -m playwright install-deps",
            "安装系统依赖"
        )
    
    return True

def test_playwright():
    """测试Playwright功能"""
    print("🧪 测试Playwright功能...")
    
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            # 启动浏览器
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # 访问测试页面
            page.goto("https://www.baidu.com")
            title = page.title()
            
            # 关闭浏览器
            browser.close()
            
            print(f"✅ Playwright测试成功，访问页面标题: {title}")
            return True
            
    except Exception as e:
        print(f"❌ Playwright测试失败: {e}")
        return False

def main():
    """主函数"""
    print("🎭 Playwright安装和测试工具")
    print("=" * 50)
    
    # 检查当前状态
    playwright_installed = check_playwright_installed()
    browser_available = False
    
    if playwright_installed:
        browser_available = check_browser_installed()
    
    # 根据状态决定操作
    if playwright_installed and browser_available:
        print("✅ Playwright和浏览器都已正确安装")
        
        # 询问是否要测试
        test_choice = input("是否要运行测试? (y/N): ").strip().lower()
        if test_choice in ['y', 'yes']:
            test_playwright()
    else:
        print("需要安装Playwright或浏览器")
        
        # 询问是否要安装
        install_choice = input("是否要自动安装? (Y/n): ").strip().lower()
        if install_choice not in ['n', 'no']:
            if install_playwright():
                print("🎉 安装完成！")
                
                # 验证安装
                if check_playwright_installed() and check_browser_installed():
                    print("✅ 安装验证成功")
                    
                    # 运行测试
                    test_playwright()
                else:
                    print("❌ 安装验证失败，请检查错误信息")
            else:
                print("❌ 安装失败")
        else:
            print("取消安装")
    
    print("\n" + "=" * 50)
    print("🏁 完成")
    
    # 显示使用提示
    print("\n💡 使用提示:")
    print("1. 确保Python版本 >= 3.7")
    print("2. 如果安装失败，尝试升级pip: python -m pip install --upgrade pip")
    print("3. 在某些Linux系统上可能需要安装额外的系统依赖")
    print("4. 如果网络较慢，安装过程可能需要几分钟")
    
    print("\n🔗 相关命令:")
    print("手动安装: pip install playwright && playwright install chromium")
    print("测试安装: python -c \"from playwright.sync_api import sync_playwright; print('OK')\"")

if __name__ == "__main__":
    main()
