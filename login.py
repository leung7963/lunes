#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cloudflare Turnstile 绕过 + 自动登录工具
============================================
功能：
1. 使用 SeleniumBase UC 模式绕过 Cloudflare 验证，获取 cf_clearance Cookie
2. 使用 Playwright 执行网站登录（携带绕过后的 Cookie）
3. 通过 Telegram Bot 发送成功/失败通知
4. 支持 Linux 虚拟显示（Xvfb）

环境变量：
    WEBSITE_URL           - 目标网站登录页URL
    USERNAME              - 登录用户名
    PASSWORD              - 登录密码
    TELEGRAM_BOT_TOKEN    - Telegram Bot Token
    TELEGRAM_CHAT_ID      - 接收通知的聊天ID

可选代理：
    通过命令行参数 --proxy 传递给绕过模块

运行模式：
    --bypass-only  : 仅绕过 Cloudflare 并保存 Cookie
    --login-only   : 仅执行 Playwright 登录（不绕过）
    （默认）       : 先绕过，再登录
"""

import asyncio
import os
import sys
import time
import json
import platform
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import requests
from playwright.async_api import async_playwright

# SeleniumBase（需安装：pip install seleniumbase）
try:
    from seleniumbase import SB
except ImportError:
    print("[!] 请安装 seleniumbase: pip install seleniumbase")
    sys.exit(1)

# Linux 虚拟显示（可选）
if platform.system().lower() == "linux":
    try:
        from pyvirtualdisplay import Display
    except ImportError:
        print("[!] 请安装 pyvirtualdisplay: pip install pyvirtualdisplay")
        print("[!] 以及系统依赖: apt-get install -y xvfb")
        sys.exit(1)


# ========== 环境变量读取 ==========
WEBSITE_URL = os.getenv("WEBSITE_URL")
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 检查必需的环境变量（不同模式可能需要不同变量，后续函数内再具体检查）
if not WEBSITE_URL:
    print("[!] 环境变量 WEBSITE_URL 未设置")
    sys.exit(1)


# ========== 工具函数 ==========
def send_telegram_message(message: str) -> None:
    """发送消息到 Telegram（同步）"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[!] Telegram 环境变量未配置，无法发送通知")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print("[+] Telegram 通知发送成功")
    except Exception as e:
        print(f"[-] Telegram 通知失败: {e}")


def setup_linux_display():
    """为 Linux 系统启动虚拟显示（Xvfb）"""
    if platform.system().lower() != "linux":
        return None
    if os.environ.get("DISPLAY"):
        return None  # 已有显示
    display = Display(visible=False, size=(1920, 1080))
    display.start()
    os.environ["DISPLAY"] = display.new_display_var
    print("[*] Linux: 已启动虚拟显示 (Xvfb)")
    return display


# ========== Cloudflare 绕过模块（SeleniumBase） ==========
def bypass_cloudflare(
    url: str,
    proxy: Optional[str] = None,
    timeout: float = 60.0,
    save_cookies: bool = True
) -> Dict[str, Any]:
    """
    绕过 Cloudflare 验证并获取 Cookie（同步）
    返回:
        {
            "success": bool,
            "cookies_dict": dict,      # name -> value
            "cookies_list": list,       # Playwright 可用的原始格式
            "cf_clearance": str,
            "user_agent": str,
            "error": str
        }
    """
    result = {
        "success": False,
        "cookies_dict": {},
        "cookies_list": [],
        "cf_clearance": None,
        "user_agent": None,
        "error": None
    }

    print(f"[*] 绕过 Cloudflare: {url}")
    if proxy:
        print(f"[*] 使用代理: {proxy}")

    try:
        # 启动浏览器（UC模式）
        with SB(uc=True, test=True, locale="en", proxy=proxy) as sb:
            print("[*] 浏览器已启动，正在加载页面...")
            sb.uc_open_with_reconnect(url, reconnect_time=5.0)
            time.sleep(2)

            # 检测 Cloudflare 验证
            page_source = sb.get_page_source().lower()
            cf_indicators = ["turnstile", "challenges.cloudflare", "just a moment", "verify you are human"]
            if any(x in page_source for x in cf_indicators):
                print("[*] 检测到 Cloudflare 验证，尝试点击...")
                try:
                    sb.uc_gui_click_captcha()
                    time.sleep(3)
                except Exception as e:
                    print(f"[!] 点击验证码出错: {e}")

            # 获取所有 Cookie
            cookies_list = sb.get_cookies()  # 返回列表，每个元素含 name, value, domain, path, secure, expiry, httpOnly
            cookies_dict = {c["name"]: c["value"] for c in cookies_list}
            cf_clearance = cookies_dict.get("cf_clearance")
            user_agent = sb.execute_script("return navigator.userAgent")

            result["cookies_dict"] = cookies_dict
            result["cookies_list"] = cookies_list
            result["cf_clearance"] = cf_clearance
            result["user_agent"] = user_agent

            if cf_clearance:
                result["success"] = True
                print(f"[+] 成功获取 cf_clearance: {cf_clearance[:50]}...")

                if save_cookies:
                    save_dir = Path("output/cookies")
                    save_dir.mkdir(parents=True, exist_ok=True)
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

                    # JSON 格式
                    with open(save_dir / f"cookies_{ts}.json", "w", encoding="utf-8") as f:
                        json.dump({
                            "url": url,
                            "cookies": cookies_dict,
                            "user_agent": user_agent,
                            "timestamp": ts
                        }, f, indent=2, ensure_ascii=False)

                    # Netscape 格式（用于 curl/wget）
                    with open(save_dir / f"cookies_{ts}.txt", "w") as f:
                        f.write("# Netscape HTTP Cookie File\n")
                        for c in cookies_list:
                            domain = c.get("domain", "")
                            secure = "TRUE" if c.get("secure") else "FALSE"
                            expiry = int(c.get("expiry", 0))
                            f.write(f"{domain}\tTRUE\t{c.get('path', '/')}\t{secure}\t{expiry}\t{c['name']}\t{c['value']}\n")

                    print(f"[+] Cookie 已保存到: {save_dir}")
            else:
                result["error"] = "未获取到 cf_clearance"
                print(f"[-] {result['error']}")

    except Exception as e:
        result["error"] = str(e)
        print(f"[-] 绕过过程异常: {e}")

    return result


# ========== Playwright 登录模块 ==========
async def login_with_playwright(
    url: str = WEBSITE_URL,
    username: str = USERNAME,
    password: str = PASSWORD,
    initial_cookies: Optional[List[Dict]] = None  # Playwright 格式的 Cookie 列表
) -> bool:
    """
    使用 Playwright 执行登录，可预先注入 Cookie（例如 cf_clearance）
    返回是否成功
    """
    if not url or not username or not password:
        print("[!] 登录所需信息不完整（URL/用户名/密码）")
        return False

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu"
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # 如果提供了初始 Cookie，则注入
        if initial_cookies:
            await context.add_cookies(initial_cookies)
            print(f"[*] 已注入 {len(initial_cookies)} 个 Cookie")

        try:
            print(f"[*] 正在访问登录页: {url}")
            await page.goto(url, wait_until="networkidle", timeout=30000)

            # 填写登录表单
            await page.fill("#email", username)
            await page.fill("#password", password)
            await page.click("button[type='submit']")
            await page.wait_for_load_state("networkidle", timeout=10000)

            # 简单检查登录是否成功
            current_url = page.url
            title = await page.title()
            if "/" in current_url and "Login" not in title:
                msg = (f"*登录成功！*\n"
                       f"时间: {datetime.now().isoformat()}\n"
                       f"页面: {current_url}\n"
                       f"标题: {title}")
                await send_telegram_message(msg)
                print("[+] 登录成功")
                return True
            else:
                raise Exception(f"登录可能失败 (URL: {current_url}, Title: {title})")

        except Exception as e:
            # 截图并发送失败通知
            await page.screenshot(path="login-failure.png", full_page=True)
            error_msg = (f"*登录失败！*\n"
                         f"时间: {datetime.now().isoformat()}\n"
                         f"错误: {str(e)}\n"
                         f"截图已保存为 login-failure.png")
            await send_telegram_message(error_msg)
            print(f"[-] 登录异常: {e}")
            return False

        finally:
            await browser.close()


# ========== 组合流程：先绕过再登录 ==========
async def bypass_and_login(proxy: Optional[str] = None) -> bool:
    """绕过 Cloudflare，然后使用获得的 Cookie 登录"""
    # 1. 绕过 Cloudflare
    print("\n=== 步骤1: 绕过 Cloudflare ===")
    bypass_result = bypass_cloudflare(url=WEBSITE_URL, proxy=proxy, save_cookies=True)
    if not bypass_result["success"]:
        error = bypass_result.get("error", "未知错误")
        await send_telegram_message(f"*绕过 Cloudflare 失败*\n时间: {datetime.now().isoformat()}\n错误: {error}")
        print("[-] 绕过失败，终止流程")
        return False

    # 2. 使用获取的 Cookie 登录
    print("\n=== 步骤2: 执行 Playwright 登录 ===")
    cookies_for_playwright = bypass_result["cookies_list"]  # 直接使用原始格式
    login_success = await login_with_playwright(
        url=WEBSITE_URL,
        username=USERNAME,
        password=PASSWORD,
        initial_cookies=cookies_for_playwright
    )
    return login_success


# ========== 主程序入口 ==========
def main():
    parser = argparse.ArgumentParser(
        description="Cloudflare 绕过 + 自动登录工具",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--proxy", help="代理地址 (格式: http://host:port)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--bypass-only", action="store_true", help="仅绕过 Cloudflare，不登录")
    group.add_argument("--login-only", action="store_true", help="仅执行 Playwright 登录（不绕过）")
    args = parser.parse_args()

    # 启动 Linux 虚拟显示（仅在需要浏览器时）
    display = None
    if not args.login_only:  # 绕过模式需要图形界面
        display = setup_linux_display()

    try:
        if args.bypass_only:
            print("\n=== 仅绕过 Cloudflare ===")
            result = bypass_cloudflare(url=WEBSITE_URL, proxy=args.proxy, save_cookies=True)
            if result["success"]:
                print("[OK] 绕过成功")
            else:
                print(f"[FAIL] {result['error']}")
                sys.exit(1)

        elif args.login_only:
            print("\n=== 仅执行 Playwright 登录 ===")
            if not USERNAME or not PASSWORD:
                print("[!] 未设置 USERNAME 或 PASSWORD 环境变量")
                sys.exit(1)
            success = asyncio.run(login_with_playwright())
            if not success:
                sys.exit(1)

        else:
            # 默认：完整流程
            print("\n=== 完整流程：绕过 + 登录 ===")
            if not USERNAME or not PASSWORD:
                print("[!] 未设置 USERNAME 或 PASSWORD 环境变量")
                sys.exit(1)
            success = asyncio.run(bypass_and_login(proxy=args.proxy))
            if not success:
                sys.exit(1)

    finally:
        if display:
            display.stop()


if __name__ == "__main__":
    main()