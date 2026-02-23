import asyncio
import os
import requests
from playwright.async_api import async_playwright

# 从环境变量读取配置
WEBSITE_URL = os.getenv("WEBSITE_URL")
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

async def send_telegram_message(message):
    """发送消息到 Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"Telegram 通知失败: {e}")

async def login():
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
        page = await browser.new_page()
        await page.set_user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        try:
            # 访问目标页面
            await page.goto(WEBSITE_URL, wait_until="networkidle")

            # 填写登录表单
            await page.fill("#email", USERNAME)
            await page.fill("#password", PASSWORD)

            # 点击提交按钮（此处已移除验证码处理）
            await page.click("button[type='submit']")

            # 等待导航完成
            await page.wait_for_load_state("networkidle", timeout=10000)

            # 检查是否登录成功
            current_url = page.url
            title = await page.title()
            # 简单判断：如果 URL 中不包含 '/' 且标题不含 "Login" 视为成功（可根据实际情况调整）
            if "/" in current_url and "Login" not in title:
                message = (f"*登录成功！*\n"
                           f"时间: {datetime.now().isoformat()}\n"
                           f"页面: {current_url}\n"
                           f"标题: {title}")
                await send_telegram_message(message)
                print("登录成功！当前页面：", current_url)
            else:
                raise Exception(f"登录可能失败。当前 URL: {current_url}, 标题: {title}")

            print("脚本执行完成。")

        except Exception as error:
            # 失败时截图并发送通知
            await page.screenshot(path="login-failure.png", full_page=True)
            error_message = (f"*登录失败！*\n"
                             f"时间: {datetime.now().isoformat()}\n"
                             f"错误: {str(error)}\n"
                             f"请检查 Artifacts 中的 login-debug")
            await send_telegram_message(error_message)
            print("登录失败：", error)
            print("截屏已保存为 login-failure.png")
            raise error

        finally:
            await browser.close()

if __name__ == "__main__":
    from datetime import datetime
    asyncio.run(login())