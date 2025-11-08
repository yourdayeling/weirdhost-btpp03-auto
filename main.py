import os
import time
from playwright.sync_api import sync_playwright, Cookie, TimeoutError as PlaywrightTimeoutError

def add_server_time(server_url="https://hub.weirdhost.xyz/server/940cf846"):
    """
    尝试登录 hub.weirdhost.xyz 并点击 "시간추가" 按钮。
    """
    # 从环境变量获取登录凭据
    remember_web_cookie_string = os.environ.get('REMEMBER_WEB_COOKIE')
    pterodactyl_email = os.environ.get('PTERODACTYL_EMAIL')
    pterodactyl_password = os.environ.get('PTERODACTYL_PASSWORD')

    if not (remember_web_cookie_string or (pterodactyl_email and pterodactyl_password)):
        print("错误: 缺少登录凭据。")
        return False

    # 定义通用域名和路径
    DEFAULT_DOMAIN = 'hub.weirdhost.xyz'
    DEFAULT_PATH = '/'

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(90000)

        try:
            current_session_valid = False
            # --- 方案一：优先尝试使用 Cookie 会话登录 ---
            if remember_web_cookie_string:
                print("检测到 REMEMBER_WEB_COOKIE 字符串，尝试解析并设置 Cookie...")
                
                cookies_to_add = []
                for cookie_pair in remember_web_cookie_string.split('; '):
                    if '=' in cookie_pair:
                        name, value = cookie_pair.split('=', 1)
                        if name and value:
                            cookies_to_add.append({
                                'name': name.strip(),
                                'value': value.strip(),
                                'domain': DEFAULT_DOMAIN,
                                'path': DEFAULT_PATH,
                                'expires': int(time.time()) + 3600 * 24 * 365,
                                'secure': True,
                                'sameSite': 'Lax'
                            })

                if cookies_to_add:
                    print(f"已解析出 {len(cookies_to_add)} 个 Cookie。正在设置...")
                    page.context.add_cookies(cookies_to_add)
                    print(f"已设置 Cookie。正在访问目标服务器页面: {server_url}")

                    try:
                        page.goto(server_url, wait_until="domcontentloaded", timeout=90000)
                    except PlaywrightTimeoutError:
                        print(f"页面加载超时（90秒）。")
                    
                    if "login" in page.url or "auth" in page.url:
                        print("Cookie 登录失败或会话已过期，将回退到邮箱密码登录。")
                        page.context.clear_cookies()
                    else:
                        print("Cookie 登录成功，已进入服务器页面。")
                        current_session_valid = True
                else:
                    print("错误: REMEMBER_WEB_COOKIE 环境变量解析失败或为空。")
            
            # --- 方案二：如果 Cookie 方案失败或未提供，则使用邮箱密码登录 ---
            if not current_session_valid:
                if not (pterodactyl_email and pterodactyl_password):
                    print("错误: 登录凭据不足。无法继续。")
                    browser.close()
                    return False

                login_url = f"https://{DEFAULT_DOMAIN}/auth/login"
                print(f"正在访问登录页面: {login_url}")
                page.goto(login_url, wait_until="domcontentloaded", timeout=90000)

                email_selector = 'input[name="username"]'  
                password_selector = 'input[name="password"]'
                login_button_selector = 'button[type="submit"]'

                page.wait_for_selector(login_button_selector)
                page.fill(email_selector, pterodactyl_email)
                page.fill(password_selector, pterodactyl_password)

                print("正在点击登录按钮...")
                with page.expect_navigation(wait_until="domcontentloaded", timeout=60000):
                    page.click(login_button_selector)

                if "login" in page.url or "auth" in page.url:
                    print("邮箱密码登录失败。")
                    browser.close()
                    return False
                else:
                    print("邮箱密码登录成功。")
                    # 登录成功后，导航至服务器页面
                    page.goto(server_url, wait_until="domcontentloaded", timeout=90000)

            # --- 核心操作：查找并点击 "시간추가" 按钮 (最终修正) ---
            
            # 1. 尝试滚动到底部以确保所有元素加载
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1) 
            
            # 2. 使用 Playwright 推荐的 get_by_role 结合 name (文本) 定位
            # name 参数使用 exact=True 确保精确匹配 "시간추가" (无空格)
            print("尝试使用 get_by_role 查找 '시간추가' 按钮...")
            add_button = page.get_by_role("button", name="시간추가", exact=True)

            try:
                add_button.wait_for(state='visible', timeout=30000)
                add_button.click(force=True)
                
                print("成功点击 '시간추가' 按钮。")
                time.sleep(5) 
                print("任务完成。")
                browser.close()
                return True
            except PlaywrightTimeoutError:
                print(f"错误: 在30秒内未找到 '시간추가' 按钮。")
                page.screenshot(path="add_time_button_not_found.png")
                browser.close()
                return False

        except Exception as e:
            print(f"执行过程中发生未知错误: {e}")
            page.screenshot(path="general_error.png")
            browser.close()
            return False

if __name__ == "__main__":
    print("开始执行添加服务器时间任务...")
    success = add_server_time()
    if success:
        print("任务执行成功。")
        exit(0)
    else:
        print("任务执行失败。")
        exit(1)
