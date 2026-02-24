# ============================================================
# Lunes Host 自动登录脚本（支持 Cloudflare Turnstile）
# 基于 SeleniumBase UC Mode
# 支持 Mac / Windows / Linux
# ============================================================

import os
import sys
import time
import json
import platform
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from seleniumbase import SB


def is_linux() -> bool:
    """检测是否为Linux系统"""
    return platform.system().lower() == "linux"


def setup_display():
    """设置Linux虚拟显示（无头服务器使用）"""
    if is_linux() and not os.environ.get("DISPLAY"):
        try:
            from pyvirtualdisplay import Display
            display = Display(visible=False, size=(1920, 1080))
            display.start()
            os.environ["DISPLAY"] = display.new_display_var
            print("[*] Linux: 已启动虚拟显示 (Xvfb)")
            return display
        except ImportError:
            print("[!] 请安装: pip install pyvirtualdisplay")
            print("[!] 以及: apt-get install -y xvfb")
            sys.exit(1)
        except Exception as e:
            print(f"[!] 启动虚拟显示失败: {e}")
            sys.exit(1)
    return None


def login_lunes(
    email: str,
    password: str,
    login_url: str = "https://betadash.lunes.host/login",  # 替换为实际登录页URL
    proxy: Optional[str] = None,
    timeout: float = 60.0,
    save_cookies: bool = True
) -> Dict[str, Any]:
    """
    登录 Lunes Host，自动绕过 Cloudflare Turnstile
    
    参数:
        email: 登录邮箱
        password: 登录密码
        login_url: 登录页面URL
        proxy: 代理地址（可选，格式: http://host:port）
        timeout: 超时时间（秒）
        save_cookies: 是否保存登录后的Cookie到文件
    
    返回:
        {
            "success": bool,
            "cookies": dict,
            "cf_clearance": str,
            "user_agent": str,
            "error": str
        }
    """
    result = {
        "success": False,
        "cookies": {},
        "cf_clearance": None,
        "user_agent": None,
        "error": None
    }

    try:
        print(f"[*] 登录目标: {login_url}")
        if proxy:
            print(f"[*] 代理: {proxy}")

        # 启动浏览器（UC模式自动处理 Cloudflare 验证）
        with SB(uc=True, test=True, locale="en", proxy=proxy) as sb:
            print("[*] 浏览器已启动，正在加载登录页面...")

            # 打开页面（带重连机制，提高稳定性）
            sb.uc_open_with_reconnect(login_url, reconnect_time=5.0)
            time.sleep(2)

            # 检测并尝试绕过 Cloudflare 验证（如果有）
            page_source = sb.get_page_source().lower()
            if "turnstile" in page_source or "challenges.cloudflare" in page_source:
                print("[*] 检测到 Cloudflare 验证，正在尝试自动处理...")
                try:
                    sb.uc_gui_click_captcha()  # 点击验证复选框（如果出现）
                    time.sleep(3)
                except Exception as e:
                    print(f"[!] 点击验证码出错: {e}")

            # 等待 Turnstile 自动填充隐藏字段（通常很快）
            print("[*] 等待 Turnstile 完成验证...")

            # 定位邮箱、密码输入框
            email_input = sb.find_element("input#email")
            pwd_input = sb.find_element("input#password")

            # 填写表单
            email_input.clear()
            email_input.send_keys(email)
            pwd_input.clear()
            pwd_input.send_keys(password)

            # 点击提交按钮
            submit_btn = sb.find_element("button[type='submit']")
            submit_btn.click()
            print("[*] 登录表单已提交，等待跳转...")

            # 等待登录成功后的页面特征（可调整）
            time.sleep(5)
            sb.wait_for_url_change(login_url, timeout=10)

            # 获取所有Cookie
            cookies_list = sb.get_cookies()
            result["cookies"] = {c["name"]: c["value"] for c in cookies_list}
            result["cf_clearance"] = result["cookies"].get("cf_clearance")
            result["user_agent"] = sb.execute_script("return navigator.userAgent")

            # 判断是否登录成功（根据实际情况修改）
            if "dashboard" in sb.get_current_url() or len(result["cookies"]) > 2:
                result["success"] = True
                print(f"[+] 登录成功！当前URL: {sb.get_current_url()}")

                # 保存Cookie
                if save_cookies:
                    save_dir = Path("output/cookies")
                    save_dir.mkdir(parents=True, exist_ok=True)
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

                    # JSON格式
                    with open(save_dir / f"lunes_cookies_{ts}.json", "w", encoding="utf-8") as f:
                        json.dump({
                            "url": login_url,
                            "cookies": result["cookies"],
                            "user_agent": result["user_agent"],
                            "timestamp": ts
                        }, f, indent=2, ensure_ascii=False)

                    # Netscape格式（可用于curl/wget）
                    with open(save_dir / f"lunes_cookies_{ts}.txt", "w") as f:
                        f.write("# Netscape HTTP Cookie File\n")
                        for c in cookies_list:
                            domain = c.get("domain", "")
                            secure = "TRUE" if c.get("secure") else "FALSE"
                            expiry = int(c.get("expiry", 0))
                            f.write(f"{domain}\tTRUE\t{c.get('path', '/')}\t{secure}\t{expiry}\t{c['name']}\t{c['value']}\n")

                    print(f"[+] Cookie已保存到: {save_dir}")
            else:
                result["error"] = "登录失败，未跳转到预期页面"
                print(f"[-] {result['error']}")

    except Exception as e:
        result["error"] = str(e)
        print(f"[-] 发生异常: {e}")

    return result


# ============================================================
# 命令行入口
# ============================================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Lunes Host 自动登录（绕过 Cloudflare Turnstile）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python lunes_login.py user@example.com yourpassword
  python lunes_login.py user@example.com yourpassword --proxy http://127.0.0.1:7890
        """
    )
    parser.add_argument("email", help="登录邮箱")
    parser.add_argument("password", help="登录密码")
    parser.add_argument("--url", default="https://example.com/login", help="登录页URL（默认为示例）")
    parser.add_argument("-p", "--proxy", help="代理地址（如 http://127.0.0.1:7890）")
    parser.add_argument("-t", "--timeout", type=float, default=60.0, help="超时时间")
    parser.add_argument("--no-save", action="store_true", help="不保存Cookie")
    args = parser.parse_args()

    # Linux虚拟显示（无头服务器必需）
    display = setup_display()

    print("\n" + "="*50)
    print("Lunes Host 自动登录脚本")
    print(f"系统: {platform.system()} {platform.release()}")
    print("="*50 + "\n")

    # 执行登录
    result = login_lunes(
        email=args.email,
        password=args.password,
        login_url=args.url,
        proxy=args.proxy,
        timeout=args.timeout,
        save_cookies=not args.no_save
    )

    # 输出结果摘要
    print("\n" + "-"*50)
    if result["success"]:
        print(f"[✓] 登录成功！获取到 {len(result['cookies'])} 个 Cookie")
        if result.get("cf_clearance"):
            print(f"[✓] cf_clearance: {result['cf_clearance'][:50]}...")
    else:
        print(f"[✗] 登录失败: {result['error']}")
    print("-"*50 + "\n")

    # 清理虚拟显示
    if display:
        display.stop()