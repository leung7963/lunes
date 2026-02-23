#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cloudflare 绕过 + 自动登录（单浏览器方案 - 增强版）
==================================================
改进点：
- 更全面的验证码检测（多种选择器）
- 增加等待时间确保验证元素加载
- 支持手动指定验证框选择器（通过环境变量）
- 详细的日志输出，便于调试
"""

import os
import sys
import time
import platform
from datetime import datetime

import requests
from seleniumbase import SB

# ...（省略环境变量读取和 Telegram 函数，与之前相同）...

def detect_and_click_challenge(sb):
    """
    检测并点击 Cloudflare 验证，支持多种形式
    返回是否成功点击
    """
    # 常见验证元素选择器列表
    challenge_selectors = [
        'iframe[src*="challenges"]',        # 传统 iframe
        'iframe[title*="challenge"]', 
        'iframe[id*="cf"]',
        '#cf-please-wait',                  # 等待页面
        '#turnstile-wrapper',                # Turnstile 包裹器
        '.cf-turnstile',                      # Turnstile 类
        'div[data-sitekey]',                  # 包含 sitekey 的 div
    ]
    
    # 等待任意验证元素出现（最多10秒）
    for selector in challenge_selectors:
        try:
            if sb.is_element_visible(selector, timeout=3):
                print(f"[*] 检测到验证元素: {selector}")
                # 使用 uc_gui_click_captcha 尝试点击（通用方法）
                sb.uc_gui_click_captcha()
                time.sleep(3)
                # 检查是否点击成功（例如元素消失）
                if not sb.is_element_visible(selector, timeout=2):
                    print("[+] 验证点击成功")
                    return True
                else:
                    print("[!] 点击后验证元素仍存在，尝试备用点击")
                    # 备用：直接点击特定区域（如复选框）
                    sb.uc_click("span[role='checkbox']", timeout=3)
                    time.sleep(2)
        except Exception as e:
            print(f"[!] 尝试点击验证时出错: {e}")
            continue
    
    # 如果以上都失败，尝试执行通用的绕过方法
    print("[*] 尝试通用绕过方法...")
    try:
        sb.uc_gui_handle_captcha()  # 更高级的自动处理
        time.sleep(3)
        return True
    except:
        pass
    
    return False

def bypass_and_login():
    display = setup_linux_display()
    try:
        with SB(uc=True, test=True, locale="en") as sb:
            print("[*] 浏览器已启动，正在访问登录页...")
            sb.uc_open_with_reconnect(WEBSITE_URL, reconnect_time=5.0)
            time.sleep(3)  # 等待页面稳定

            # 检测并处理验证
            if detect_and_click_challenge(sb):
                print("[*] 验证处理完成")
            else:
                print("[*] 未检测到明显验证，继续登录流程")

            # 填写登录表单（请根据实际页面修改选择器）
            # 可以增加等待，确保输入框可交互
            sb.wait_for_element_visible("#email", timeout=10)
            sb.type("#email", USERNAME)
            sb.type("#password", PASSWORD)
            sb.click("button[type='submit']")

            # 等待登录结果（例如跳转或特定元素出现）
            sb.wait_for_element_not_present("#email", timeout=15)
            time.sleep(2)

            # 检查登录成功
            current_url = sb.get_current_url()
            title = sb.get_title()
            if "login" not in title.lower() and "signin" not in title.lower():
                msg = f"*登录成功！*\n时间: {datetime.now().isoformat()}\n页面: {current_url}\n标题: {title}"
                send_telegram_message(msg)
                print("[+] 登录成功")
            else:
                raise Exception("登录失败，页面仍处于登录状态")

    except Exception as e:
        try:
            sb.save_screenshot("login-failure.png")
            print("[*] 已保存截图: login-failure.png")
        except:
            pass
        error_msg = f"*登录失败！*\n时间: {datetime.now().isoformat()}\n错误: {str(e)}"
        send_telegram_message(error_msg)
        print(f"[-] 登录异常: {e}")
        raise
    finally:
        if display:
            display.stop()

if __name__ == "__main__":
    bypass_and_login()