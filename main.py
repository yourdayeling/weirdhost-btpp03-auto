import os
import time
import logging
from urllib.parse import unquote
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# 设置日志（更详细）
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def add_server_time(server_url="https://hub.weirdhost.xyz/server/940cf846"):
    """
    尝试登录 hub.weirdhost.xyz 并点击 "시간추가" 按钮。
    """
    remember_web_cookie_string = os.environ.get('REMEMBER_WEB_COOKIE')
    pterodactyl_email = os.environ.get('PTERODACTYL_EMAIL')
    pterodactyl_password = os.environ.get('PTERODACTYL_PASSWORD')

    if not (remember_web_cookie_string or (pterodactyl_email and pterodactyl_password)):
        logger.error("缺少登录凭据。")
        return False

    DEFAULT_DOMAIN = 'hub.weirdhost.xyz'
    DEFAULT_PATH = '/'

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # 临时改为headless=False，便于手动观察
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(90000)

        try:
            current_session_valid = False
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

                    # 改进：用networkidle等待JS加载
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

            # --- 核心操作：增强按钮查找与调试 ---
            # 1. 等待额外JS加载
            page.wait_for_load_state("networkidle")
            time.sleep(2)  # 缓冲
            
            # 2. 滚动并打印所有按钮（调试）
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)
            
            # 列出所有按钮文本（新增调试）
            all_buttons = page.query_selector_all('button, [role="button"], a[role="button"]')
            button_texts = [btn.inner_text() for btn in all_buttons if btn.inner_text().strip()]
            logger.debug(f"页面中共找到 {len(button_texts)} 个按钮/链接。文本列表: {button_texts[:20]}...")  # 打印前20个
            
            # 检查是否包含目标文本
            if any("시간추가" in text for text in button_texts):
                logger.info("检测到包含 '시간추가' 的按钮文本，继续定位。")
            else:
                logger.warning("未在按钮文本中找到 '시간추가'。可能在其他元素或需展开。")

            # 3. 多重定位策略
            button_strategies = [
                ("Role exact", page.get_by_role("button", name="시간추가", exact=True)),
                ("Role contains", page.get_by_role("button", name="시간추가")),  # 移除exact
                ("Text contains", page.get_by_text("시간추가", exact=False)),
                ("CSS text", page.locator('button:has-text("시간추가")')),
                ("XPath", page.locator('//button[contains(text(), "시간추가")] | //*[contains(@class, "btn") and contains(text(), "시간추가")]')),  # 扩展到btn类
            ]
            
            success = False
            for name, button in button_strategies:
                logger.debug(f"尝试策略: {name}")
                try:
                    button.wait_for(state='visible', timeout=10000)
                    logger.debug(f"策略 {name} 成功定位按钮。点击...")
                    button.click(force=True, timeout=5000)
                    
                    # 等待响应（e.g., 模态或更新）
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                    
                    # 验证：检查是否出现成功消息或时间变化（自定义，根据UI调整）
                    try:
                        success_toast = page.get_by_text("추가되었습니다", timeout=5000)  # 示例：韩文"已添加"
                        logger.info("检测到成功消息。")
                    except PlaywrightTimeoutError:
                        logger.info("点击执行，无明显UI反馈（检查服务器时间是否更新）。")
                    
                    success = True
                    break
                except PlaywrightTimeoutError:
                    logger.debug(f"策略 {name} 超时，继续下一个。")
                except Exception as click_err:
                    logger.debug(f"策略 {name} 点击错误: {click_err}")

            if not success:
                logger.error("所有定位策略失败。")
                # 额外调试：截图 + HTML片段
                page.screenshot(path="debug_server_page.png")
                with open("debug_page.html", "w", encoding="utf-8") as f:
                    f.write(page.content())
                logger.debug("已保存 debug_server_page.png 和 debug_page.html 用于手动检查。")
                browser.close()
                return False

            logger.info("任务完成。")
            browser.close()
            return True

        except Exception as e:
            logger.error(f"执行过程中发生未知错误: {e}")
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
