#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cloudflare 绕过 + 自动登录（单浏览器方案）
============================================
使用 SeleniumBase UC 模式，一次性完成：
1. 绕过 Cloudflare Turnstile 验证
2. 填写登录表单并提交
3. 通过 Telegram 发送成功/失败通知

环境变量：
    WEBSITE_URL           - 目标网站登录页URL
    USERNAME              - 登录用户名
    PASSWORD              - 登录密码
    TELEGRAM_BOT_TOKEN    - Telegram Bot Token
    TELEGRAM_CHAT_ID      - 接收通知的聊天ID
"""

import os
import sys
import time
import platform
from datetime import datetime

import requests
from seleniumbase import SB

# 可选：Linux 虚拟显示支持
if platform.system().lower() == "linux":
    try:
        from pyvirtualdisplay import Display
    except ImportError:
        print("[!] 请安装 pyvirtualdisplay: pip install pyvirtualdisplay")
        print("[!] 以及系统依赖: apt-get install -y xvfb")
        sys.exit(1)


# ========== 读取环境变量 ==========
WEBSITE_URL = os.getenv("WEBSITE_URL")
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# 检查必需变量
missing_vars = []
if not WEBSITE_URL:
    missing_vars.append("WEBSITE_URL")
if not USERNAME:
    missing_vars.append("USERNAME")
if not PASSWORD:
    missing_vars.append("PASSWORD")
if missing_vars:
    print(f"[!] 缺少必需的环境变量: {', '.join(missing_vars)}")
    sys.exit(1)

# Telegram 配置可选，若缺少则仅打印日志
TELEGRAM_ENABLED = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


# ========== Telegram 通知函数 ==========
def send_telegram_message(message: str) -> None:
    """发送消息到 Telegram（同步）"""
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
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print("[+] Telegram 通知发送成功")
    except Exception as e:
        print(f"[-] Telegram 通知失败: {e}")


# ========== Linux 虚拟显示设置 ==========
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


# ========== 主流程：绕过 + 登录 ==========
def bypass_and_login():
    """使用 SeleniumBase 一次性完成绕过和登录"""
    display = setup_linux_display()

    try:
        with SB(uc=True, test=True, locale="en") as sb:
            print("[*] 浏览器已启动，正在访问登录页...")
            # 1. 打开页面（自动处理 Cloudflare 重新连接）
            sb.uc_open_with_reconnect(WEBSITE_URL, reconnect_time=5.0)
            time.sleep(2)

            # 2. 检测并处理 Cloudflare 验证（如果出现）
            if sb.is_element_visible('iframe[src*="challenges"]'):
                print("[*] 检测到 Cloudflare 验证，尝试点击...")
                try:
                    sb.uc_gui_click_captcha()
                    time.sleep(3)
                except Exception as e:
                    print(f"[!] 点击验证码出错: {e}")

            # 3. 填写登录表单
            #   ⚠️ 请根据实际页面的选择器修改以下三行
            print("[*] 填写登录信息...")
            sb.type("#email", USERNAME)          # 用户名输入框选择器
            sb.type("#password", PASSWORD)       # 密码输入框选择器
            sb.click("button[type='submit']")    # 提交按钮选择器

            # 4. 等待登录完成（可根据页面变化调整等待条件）
            #    示例：等待用户名输入框消失，或等待某个登录后元素出现
            sb.wait_for_element_not_present("#email", timeout=10)
            time.sleep(2)  # 额外等待页面稳定

            # 5. 检查登录是否成功
            current_url = sb.get_current_url()
            title = sb.get_title()
            # 简单判断：URL 不含登录字样且标题不含 Login/Signin
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
        # 失败时截图并发送通知
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


if __name__ == "__main__":
    bypass_and_login()