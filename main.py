import os
import time
import logging
from urllib.parse import unquote
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# 设置日志（DEBUG级别，便于调试）
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def add_server_time(server_url="https://hub.weirdhost.xyz/server/8899d2b7"):
    """
    尝试登录 hub.weirdhost.xyz 并点击 "시간추가" 按钮。
    """
    # 从环境变量获取登录凭据
    remember_web_cookie_string = os.environ.get('REMEMBER_WEB_COOKIE')
    pterodactyl_email = os.environ.get('PTERODACTYL_EMAIL')
    pterodactyl_password = os.environ.get('PTERODACTYL_PASSWORD')

    if not (remember_web_cookie_string or (pterodactyl_email and pterodactyl_password)):
        logger.error("缺少登录凭据。")
        return False

    # 定义通用域名和路径
    DEFAULT_DOMAIN = 'hub.weirdhost.xyz'
    DEFAULT_PATH = '/'

    with sync_playwright() as p:
        # headless=True，适合CI；本地调试改为False
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(90000)

        try:
            current_session_valid = False
            # --- 方案一：优先尝试使用 Cookie 会话登录 ---
            if remember_web_cookie_string:
                logger.debug("检测到 REMEMBER_WEB_COOKIE 字符串，尝试解析并设置 Cookie...")
                
                cookies_to_add = []
                for cookie_pair in remember_web_cookie_string.split(';'):
                    cookie_pair = cookie_pair.strip()
                    if '=' in cookie_pair:
                        if cookie_pair.startswith('"') and cookie_pair.endswith('"'):
                            cookie_pair = cookie_pair[1:-1]
                        name, value = cookie_pair.split('=', 1)
                        name = name.strip()
                        value = unquote(value.strip())
                        if name and value:
                            cookies_to_add.append({
                                'name': name,
                                'value': value,
                                'domain': DEFAULT_DOMAIN,
                                'path': DEFAULT_PATH,
                                'expires': -1,
                                'secure': True,
                                'sameSite': 'Lax'
                            })

                if cookies_to_add:
                    logger.debug(f"已解析出 {len(cookies_to_add)} 个 Cookie。正在设置...")
                    context.add_cookies(cookies_to_add)
                    logger.debug(f"已设置 Cookie。正在访问目标服务器页面: {server_url}")

                    page.goto(server_url, wait_until="networkidle", timeout=90000)
                    logger.debug(f"页面加载完成。当前URL: {page.url}, 标题: {page.title()}")
                    
                    if "login" in page.url or "auth" in page.url:
                        logger.warning("Cookie 登录失败或会话已过期，将回退到邮箱密码登录。")
                        context.clear_cookies()
                    else:
                        logger.info("Cookie 登录成功，已进入服务器页面。")
                        current_session_valid = True
                else:
                    logger.error("REMEMBER_WEB_COOKIE 环境变量解析失败或为空。")
            
            # --- 方案二：如果 Cookie 方案失败或未提供，则使用邮箱密码登录 ---
            if not current_session_valid:
                if not (pterodactyl_email and pterodactyl_password):
                    logger.error("登录凭据不足。无法继续。")
                    browser.close()
                    return False

                login_url = f"https://{DEFAULT_DOMAIN}/auth/login"
                logger.info(f"正在访问登录页面: {login_url}")
                page.goto(login_url, wait_until="networkidle", timeout=90000)

                email_selector = 'input[name="username"]'  
                password_selector = 'input[name="password"]'
                login_button_selector = 'button[type="submit"]'

                page.wait_for_selector(login_button_selector, timeout=30000)
                page.fill(email_selector, pterodactyl_email)
                page.fill(password_selector, pterodactyl_password)

                logger.info("正在点击登录按钮...")
                with page.expect_navigation(wait_until="networkidle", timeout=60000):
                    page.click(login_button_selector)

                if "login" in page.url or "auth" in page.url:
                    logger.error("邮箱密码登录失败。")
                    browser.close()
                    return False
                else:
                    logger.info("邮箱密码登录成功。")
                    page.goto(server_url, wait_until="networkidle", timeout=90000)

            # --- 核心操作：切换到 콘솔 Tab 并点击 "시간추가" 按钮 ---
            
            # 1. 加强等待：确保 DOM 完整
            page.wait_for_load_state("networkidle")
            page.wait_for_function("document.readyState === 'complete'", timeout=30000)  # JS 等待
            time.sleep(5)  # 额外缓冲，处理 SPA 渲染
            
            # 调试：总是截图和打印内容片段
            page.screenshot(path="debug_loaded_page.png")
            content_snippet = page.content()[:1000]  # 前1000字符
            logger.debug(f"页面内容片段: {content_snippet}")
            logger.debug(f"页面标题: {page.title()}")
            
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)
            
            # 2. 扩展选择器：捕获更多伪按钮
            extended_selectors = 'button, [role="button"], a[href], div[onclick], .btn, .action-btn, [class*="btn"]'
            all_buttons = page.query_selector_all(extended_selectors)
            button_texts = [btn.inner_text().strip() for btn in all_buttons if btn.inner_text().strip()]
            logger.debug(f"扩展搜索找到 {len(button_texts)} 个元素。文本列表: {button_texts[:20]}...")  # 前20个
            
            if any("시간추가" in text for text in button_texts):
                logger.info("检测到 '시간추가' 文本，继续定位。")
            else:
                logger.warning("未找到 '시간추가'。尝试切换 콘솔 Tab...")

            # 3. 新增：切换到 콘솔 Tab（Console，韩文 "콘솔"）
            console_selectors = [
                'a:has-text("콘솔")',     # 韩文 Console
                'a:has-text("Console")', # 英文备选
                '[data-tab="console"]',  # 数据属性
                'button:has-text("콘솔")',
            ]
            console_clicked = False
            for selector in console_selectors:
                try:
                    console_tab = page.locator(selector).first
                    console_tab.wait_for(state='visible', timeout=8000)
                    console_tab.click(force=True)
                    logger.info(f"点击 콘솔 Tab: {selector}")
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                    time.sleep(3)  # 等待 Console 加载
                    console_clicked = True
                    break
                except PlaywrightTimeoutError:
                    logger.debug(f"跳过 콘솔 {selector}")

            if console_clicked:
                # 4. 在 콘솔 Tab 内滚动并重搜
                page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                # 重新获取元素
                all_buttons = page.query_selector_all(extended_selectors)
                button_texts = [btn.inner_text().strip() for btn in all_buttons if btn.inner_text().strip()]
                logger.debug(f"콘솔 Tab 后元素: {len(button_texts)} 个，文本: {button_texts[:20]}...")
                
                if any("시간추가" in text for text in button_texts):
                    logger.info("콘솔 Tab 内找到 '시간추가' 文本！")

            # 5. 定位 "시간추가"（扩展 Pterodactyl 类）
            button_strategies = [
                ("Role", page.get_by_role("button", name="시간추가", exact=False)),
                ("Text", page.get_by_text("시간추가")),
                ("CSS", page.locator('button:has-text("시간추가"), .btn:has-text("시간추가")')),  # 添加 .btn
                ("XPath", page.locator('//button[contains(text(), "시간추가") or contains(@aria-label, "시간추가")]')),
                ("Modal", page.locator('div[role="dialog"] button:has-text("시간추가")')),
                ("Console btn", page.locator('.console-controls button:has-text("시간추가"), .panel-console .btn')),  # Console 特定
            ]
            
            success = False
            for name, button in button_strategies:
                logger.debug(f"尝试策略: {name}")
                try:
                    button.wait_for(state='visible', timeout=10000)
                    button.click(force=True)
                    logger.info(f"成功点击 {name}")
                    
                    # 验证
                    try:
                        page.get_by_text("추가되었습니다", timeout=5000)
                        logger.info("确认成功。")
                    except:
                        logger.info("点击完成。")
                    
                    success = True
                    break
                except PlaywrightTimeoutError:
                    logger.debug(f"{name} 超时")

            if not success:
                logger.error("所有策略失败。检查 debug 文件。")
                page.screenshot(path="debug_console_view.png")
                with open("debug_console.html", "w", encoding="utf-8") as f:
                    f.write(page.content())
                browser.close()
                return False

            logger.info("任务完成。")
            browser.close()
            return True

        except Exception as e:
            logger.error(f"未知错误: {e}")
            try:
                page.screenshot(path="general_error.png")
            except:
                pass
            browser.close()
            return False

if __name__ == "__main__":
    logger.info("开始执行添加服务器时间任务...")
    success = add_server_time()
    if success:
        logger.info("任务执行成功。")
        exit(0)
    else:
        logger.error("任务执行失败。")
        exit(1)
