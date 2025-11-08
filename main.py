import os
import time
from playwright.sync_api import sync_playwright, Cookie, TimeoutError as PlaywrightTimeoutError

def add_server_time(server_url="https://hub.weirdhost.xyz/server/940cf846"):
    """
    尝试登录 hub.weirdhost.xyz 并点击 "시간 추가" 按钮。
    优先使用 REMEMBER_WEB_COOKIE 进行会话登录，如果不存在则回退到邮箱密码登录。
    此函数设计为每次GitHub Actions运行时执行一次。
    """
    # 从环境变量获取登录凭据
    # 注意：REMEMBER_WEB_COOKIE 环境变量应包含完整的 Cookie 字符串，例如: "cookie1=value1; cookie2=value2"
    remember_web_cookie_string = os.environ.get('REMEMBER_WEB_COOKIE')
    pterodactyl_email = os.environ.get('PTERODACTYL_EMAIL')
    pterodactyl_password = os.environ.get('PTERODACTYL_PASSWORD')

    # 检查是否提供了任何登录凭据
    if not (remember_web_cookie_string or (pterodactyl_email and pterodactyl_password)):
        print("错误: 缺少登录凭据。请设置 REMEMBER_WEB_COOKIE 或 PTERODACTYL_EMAIL 和 PTERODACTYL_PASSWORD 环境变量。")
        return False

    with sync_playwright() as p:
        # 在 GitHub Actions 中，使用 headless 无头模式运行
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        # 增加默认超时时间到90秒，以应对网络波动和慢加载
        page.set_default_timeout(90000)
        
        # 定义通用域名和路径
        DEFAULT_DOMAIN = 'hub.weirdhost.xyz'
        DEFAULT_PATH = '/'

        try:
            # --- 方案一：优先尝试使用 Cookie 会话登录 (已修正解析逻辑) ---
            if remember_web_cookie_string:
                print("检测到 REMEMBER_WEB_COOKIE 字符串，尝试解析并设置 Cookie...")
                
                cookies_to_add = []
                
                # 拆分并格式化 Cookie 字符串，兼容多个 Cookie
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
                        page.screenshot(path="goto_timeout_error.png")
                    
                    # 检查是否因 Cookie 无效被重定向到登录页
                    if "login" in page.url or "auth" in page.url:
                        print("Cookie 登录失败或会话已过期，将回退到邮箱密码登录。")
                        page.context.clear_cookies()
                        remember_web_cookie_string = None # 标记 Cookie 登录失败
                    else:
                        print("Cookie 登录成功，已进入服务器页面。")
                else:
                    print("错误: REMEMBER_WEB_COOKIE 环境变量解析失败或为空。将回退到邮箱密码登录。")
                    remember_web_cookie_string = None
            
            # --- 方案二：如果 Cookie 方案失败或未提供，则使用邮箱密码登录 ---
            if not remember_web_cookie_string:
                if not (pterodactyl_email and pterodactyl_password):
                    print("错误: Cookie 无效，且未提供 PTERODACTYL_EMAIL 或 PTERODACTYL_PASSWORD。无法登录。")
                    browser.close()
                    return False

                login_url = f"https://{DEFAULT_DOMAIN}/auth/login"
                print(f"正在访问登录页面: {login_url}")
                page.goto(login_url, wait_until="domcontentloaded", timeout=90000)

                # 定义选择器 (Pterodactyl 面板通用)
                email_selector = 'input[name="username"]'  
                password_selector = 'input[name="password"]'
                login_button_selector = 'button[type="submit"]'

                print("等待登录表单元素加载...")
                page.wait_for_selector(email_selector)
                page.wait_for_selector(password_selector)
                page.wait_for_selector(login_button_selector)

                print("正在填写邮箱和密码...")
                page.fill(email_selector, pterodactyl_email)
                page.fill(password_selector, pterodactyl_password)

                print("正在点击登录按钮...")
                with page.expect_navigation(wait_until="domcontentloaded", timeout=60000):
                    page.click(login_button_selector)

                # 检查登录后是否成功
                if "login" in page.url or "auth" in page.url:
                    error_text = page.locator('.alert.alert-danger').inner_text().strip() if page.locator('.alert.alert-danger').count() > 0 else "未知错误，URL仍在登录页。"
                    print(f"邮箱密码登录失败: {error_text}")
                    page.screenshot(path="login_fail_error.png")
                    browser.close()
                    return False
                else:
                    print("邮箱密码登录成功。")

            # --- 确保当前位于正确的服务器页面 ---
            if page.url != server_url:
                print(f"当前不在目标服务器页面，正在导航至: {server_url}")
                page.goto(server_url, wait_until="domcontentloaded", timeout=90000)
                if "login" in page.url:
                    print("导航失败，会话可能已失效，需要重新登录。")
                    page.screenshot(path="server_page_nav_fail.png")
                    browser.close()
                    return False

            # --- 核心操作：查找并点击 "시간 추가" 按钮 ---
            add_button_selector = 'button:has-text("시간 추가")'
            print(f"正在查找并等待 '{add_button_selector}' 按钮...")

            try:
                # 等待按钮变为可见且可点击
                add_button = page.locator(add_button_selector)
                add_button.wait_for(state='visible', timeout=30000)
                add_button.click()
                print("成功点击 '시간 추가' 按钮。")
                time.sleep(5) # 等待5秒，确保操作在服务器端生效
                print("任务完成。")
                browser.close()
                return True
            except PlaywrightTimeoutError:
                print(f"错误: 在30秒内未找到或 '시간 추가' 按钮不可见/不可点击。")
                page.screenshot(path="add_6h_button_not_found.png")
                browser.close()
                return False

        except Exception as e:
            print(f"执行过程中发生未知错误: {e}")
            # 发生任何异常时都截图，以便调试
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
