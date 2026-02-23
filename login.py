import asyncio
import os
import requests
from datetime import datetime
from playwright.async_api import async_playwright
from bypass import bypass_cloudflare  # 假设该模块可用

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
        # 1. 调用 bypass_cloudflare 获取 cf_clearance 和 User-Agent
        bypass_result = bypass_cloudflare(WEBSITE_URL)
        if not bypass_result.get("success"):
            error_msg = f"Cloudflare 绕过失败: {bypass_result.get('error', '未知错误')}"
            await send_telegram_message(f"*登录失败！*\n时间: {datetime.now().isoformat()}\n错误: {error_msg}")
            raise Exception(error_msg)

        cf_clearance = bypass_result["cf_clearance"]
        user_agent = bypass_result["user_agent"]
        print(f"获取到 cf_clearance: {cf_clearance[:20]}..., User-Agent: {user_agent}")

        # 2. 启动浏览器并创建上下文，设置 User-Agent
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu"
            ]
        )
        context = await browser.new_context(user_agent=user_agent)

        # 3. 设置 cf_clearance cookie
        await context.add_cookies([{
            "name": "cf_clearance",
            "value": cf_clearance,
            "domain": ".example.com",  # 需要根据实际网站域名调整
            "path": "/",
            "httpOnly": True,
            "secure": True
        }])

        page = await context.new_page()

        try:
            # 4. 访问目标页面
            await page.goto(WEBSITE_URL, wait_until="networkidle")

            # 5. 填写登录表单
            await page.fill("#email", USERNAME)
            await page.fill("#password", PASSWORD)

            # 6. 点击提交按钮（已去除验证码处理）
            await page.click("button[type='submit']")

            # 7. 等待导航完成
            await page.wait_for_load_state("networkidle", timeout=10000)

            # 8. 检查是否登录成功
            current_url = page.url
            title = await page.title()
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
    asyncio.run(login())