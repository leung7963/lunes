#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cloudflare 绕过 + 自动登录（单浏览器方案 - 增强版）
==================================================
功能：
1. 使用 SeleniumBase UC 模式打开登录页
2. 自动检测并处理 Cloudflare 各种形式的验证（iframe、Turnstile等）
3. 填写登录表单并提交
4. 通过 Telegram 发送成功/失败通知

环境变量：
    WEBSITE_URL           - 目标网站登录页URL
    USERNAME              - 登录用户名
    PASSWORD              - 登录密码
    TELEGRAM_BOT_TOKEN    - Telegram Bot Token
    TELEGRAM_CHAT_ID      - 接收通知的聊天ID

支持 Linux 无头服务器（自动启动 Xvfb）
"""

import os
import sys
import time
import platform
from datetime import datetime

import requests

# SeleniumBase 核心
try:
    from seleniumbase import SB
except ImportError:
    print("[!] 请安装 seleniumbase: pip install seleniumbase")
    sys.exit(1)

# Linux 虚拟显示支持
if platform.system().lower() == "linux":
    try:
        from pyvirtualdisplay import Display
    except ImportError:
        print("[!] 请安装 pyvirtualdisplay: pip install pyvirtualdisplay")
        print("[!] 并安装系统依赖: sudo apt-get install -y xvfb")
        sys.exit(1)


# ========== 读取环境变量 ==========
WEBSITE_URL = os.getenv("WEBSITE_URL")
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 必需变量检查
missing = []
if not WEBSITE_URL:
    missing.append("WEBSITE_URL")
if not USERNAME:
    missing.append("USERNAME")
if not PASSWORD:
    missing.append("PASSWORD")
if missing:
    print(f"[!] 缺少必需的环境变量: {', '.join(missing)}")
    sys.exit(1)

# Telegram 可选
TELEGRAM_ENABLED = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


# ========== Telegram 通知 ==========
def send_telegram_message(message: str) -> None:
    """发送 Markdown 格式消息到 Telegram"""
    if not TELEGRAM_ENABLED:
        print("[通知]", message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        print("[+] Telegram 通知发送成功")
    except Exception as e:
        print(f"[-] Telegram 通知失败: {e}")


# ========== Linux 虚拟显示 ==========
def setup_linux_display():
    """为 Linux 无头服务器启动虚拟显示"""
    if platform.system().lower() != "linux":
        return None
    if os.environ.get("DISPLAY"):
        return None  # 已有显示
    display = Display(visible=False, size=(1920, 1080))
    display.start()
    os.environ["DISPLAY"] = display.new_display_var
    print("[*] Linux: 已启动虚拟显示 (Xvfb)")
    return display


# ========== 增强的验证检测与点击 ==========
def detect_and_click_challenge(sb) -> bool:
    """
    检测页面上的 Cloudflare 验证元素，并尝试点击通过
    返回 True 表示至少一次尝试成功（或未检测到验证）
    """
    # 常见的验证元素选择器（按优先级）
    challenge_selectors = [
        'iframe[src*="challenges"]',
        'iframe[title*="challenge"]',
        'iframe[id*="cf"]',
        '#cf-please-wait',
        '#turnstile-wrapper',
        '.cf-turnstile',
        'div[data-sitekey]',
        'span[role="checkbox"]',  # Turnstile 复选框
    ]

    # 等待并检测
    for selector in challenge_selectors:
        try:
            if sb.is_element_visible(selector, timeout=3):
                print(f"[*] 检测到验证元素: {selector}")
                # 尝试通用点击方法
                sb.uc_gui_click_captcha()
                time.sleep(3)
                # 检查元素是否消失
                if not sb.is_element_visible(selector, timeout=2):
                    print("[+] 验证点击成功")
                    return True
                else:
                    print("[!] 通用点击后元素仍存在，尝试备用点击")
                    # 备用：直接点击复选框区域
                    sb.uc_click("span[role='checkbox']", timeout=3)
                    time.sleep(2)
                    if not sb.is_element_visible(selector, timeout=2):
                        print("[+] 备用点击成功")
                        return True
        except Exception as e:
            print(f"[!] 处理 {selector} 时异常: {e}")
            continue

    # 如果以上都未成功，尝试高级自动处理
    try:
        print("[*] 尝试高级自动处理 (uc_gui_handle_captcha)")
        sb.uc_gui_handle_captcha()
        time.sleep(3)
        return True
    except:
        pass

    print("[*] 未检测到需要点击的验证元素，继续流程")
    return False  # 没有检测到或无法处理


# ========== 主流程：绕过 + 登录 ==========
def bypass_and_login():
    """执行 Cloudflare 绕过和登录"""
    display = setup_linux_display()

    try:
        # 启动浏览器（UC 模式）
        with SB(uc=True, test=True, locale="en") as sb:
            print("[*] 浏览器已启动，正在访问登录页...")
            sb.uc_open_with_reconnect(WEBSITE_URL, reconnect_time=5.0)
            time.sleep(3)  # 等待页面初步加载

            # 检测并处理验证
            detect_and_click_challenge(sb)

            # 填写登录表单（请根据实际页面修改选择器）
            print("[*] 等待登录表单加载...")
            sb.wait_for_element_visible("#email", timeout=10)
            sb.type("#email", USERNAME)
            sb.type("#password", PASSWORD)
            sb.click("button[type='submit']")

            # 等待登录结果（例如用户名输入框消失，或出现欢迎信息）
            sb.wait_for_element_not_present("#email", timeout=15)
            time.sleep(2)  # 额外等待页面稳定

            # 检查登录是否成功
            current_url = sb.get_current_url()
            title = sb.get_title()
            if "login" not in title.lower() and "signin" not in title.lower():
                msg = (f"*登录成功！*\n"
                       f"时间: {datetime.now().isoformat()}\n"
                       f"页面: {current_url}\n"
                       f"标题: {title}")
                send_telegram_message(msg)
                print("[+] 登录成功")
            else:
                raise Exception("登录失败，页面仍处于登录状态")

    except Exception as e:
        # 失败截图
        try:
            sb.save_screenshot("login-failure.png")
            print("[*] 已保存截图: login-failure.png")
        except:
            pass

        error_msg = (f"*登录失败！*\n"
                     f"时间: {datetime.now().isoformat()}\n"
                     f"错误: {str(e)}")
        send_telegram_message(error_msg)
        print(f"[-] 登录异常: {e}")
        raise

    finally:
        if display:
            display.stop()


# ========== 程序入口 ==========
if __name__ == "__main__":
    bypass_and_login()