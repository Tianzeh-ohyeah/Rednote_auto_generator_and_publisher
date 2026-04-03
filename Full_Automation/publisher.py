# -*- coding: utf-8 -*-
import random
from datetime import datetime, timedelta
import asyncio
import os
import re
import json
from pathlib import Path
from playwright.async_api import Playwright, async_playwright, expect

# ==============================================================================
# ⚙️ 基础配置
# ==============================================================================
class Config:
    BASE_DIR = Path(__file__).resolve().parent
    CONTENT_FILE = BASE_DIR / "Today_File" / "content.txt"
    COOKIE_PATH = r"C:\Users\tianzeh\Desktop\Full_Automation\cookies\account.json"
    ERROR_SCREENSHOT = BASE_DIR / "debug_error.png"

# ==============================================================================
# 🖨️ 终端日志类 (带颜色与明确标识)
# ==============================================================================
class MockLogger:
    def __init__(self, name): self.name = name
    def info(self, msg): print(f"ℹ️ [{self.name} INFO] {datetime.now().strftime('%H:%M:%S')} | {msg}")
    def success(self, msg): print(f"✅ [{self.name} SUCCESS] {datetime.now().strftime('%H:%M:%S')} | {msg}")
    def error(self, msg): print(f"❌ [{self.name} ERROR] {datetime.now().strftime('%H:%M:%S')} | {msg}")
    def warning(self, msg): print(f"⚠️ [{self.name} WARNING] {datetime.now().strftime('%H:%M:%S')} | {msg}")

logger = MockLogger("XHS_Uploader")

# ==============================================================================
# 🤖 仿生人类行为辅助函数
# ==============================================================================
async def random_sleep(min_s=0.5, max_s=1.5):
    """模拟人类发呆、阅读、犹豫的时间"""
    delay = random.uniform(min_s, max_s)
    await asyncio.sleep(delay)

async def simulate_mouse_move(page):
    """模拟人类无聊时在页面上滑动鼠标，带轨迹(steps)"""
    v = page.viewport_size
    x = random.randint(100, v['width'] - 100)
    y = random.randint(100, v['height'] - 100)
    # steps 参数让鼠标移动变成滑动，而不是瞬间转移
    await page.mouse.move(x, y, steps=random.randint(20, 50))
    await random_sleep(0.2, 0.4)

async def click_safe_blank(page):
    """
    【修正版】点击页面最右侧的背景留白区。
    """
    v = page.viewport_size
    # 选取屏幕最右侧 2% 到 5% 的窄长区域
    safe_x = random.randint(int(v['width'] * 0.95), int(v['width'] * 0.98))
    # 避开顶部可能存在的个人信息区，点中间高度
    safe_y = random.randint(int(v['height'] * 0.3), int(v['height'] * 0.7))
    
    await page.mouse.click(safe_x, safe_y)
    logger.info(f"点击右侧背景安全区: 坐标({safe_x}, {safe_y})")
    await random_sleep(0.5, 1.0)

# ==============================================================================
# 🛠️ 核心函数: 初始化与内容解析
# ==============================================================================
async def set_init_script(context):
    """抹除 Playwright 的 webdriver 特征，防爬虫检测"""
    await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => false});")
    return context

def parse_local_content():
    """解析本地 txt 内容"""
    if not Config.CONTENT_FILE.exists():
        logger.error(f"找不到内容文件: {Config.CONTENT_FILE}")
        return None
        
    raw_text = Config.CONTENT_FILE.read_text(encoding='utf-8').strip()
    try:
        title_match = re.search(r"标题：\s*(.*?)(?:\n|$)", raw_text)
        title = title_match.group(1).strip() if title_match else "无标题"
        
        tags_match = re.search(r"标签：\s*(.*)$", raw_text, re.MULTILINE)
        tags = tags_match.group(1).strip() if tags_match else ""
        
        marker_start = "正文："
        marker_end = "标签："
        
        if marker_start in raw_text and marker_end in raw_text:
            start_idx = raw_text.find(marker_start) + len(marker_start)
            end_idx = raw_text.find(marker_end)
            body = raw_text[start_idx:end_idx].strip()
        else:
            logger.error("文中缺少‘正文：’或‘标签：’标记")
            return None
        
        logger.info(f"成功解析文案，标题: {title[:10]}...")
        return {"title": title, "body": body, "tags": tags}
    
    except Exception as e:
        logger.error(f"解析内容失败: {e}")
        return None

# ==============================================================================
# 📝 发布类 (核心流程)
# ==============================================================================
class XiaoHongShuPublisher:
    def __init__(self, data: dict, location: str = "中国戏曲学院"):
        self.title = data['title']
        self.body = data['body']
        self.tags_raw = data['tags']
        self.location = location
        
        # 定时发布时间计算：当天下午6点 + 随机分钟/秒
        today_6pm = datetime.now().replace(hour=18, minute=0, second=0, microsecond=0)
        random_minutes = random.randint(0, 59)
        random_seconds = random.randint(0, 59)
        
        publish_time = today_6pm + timedelta(minutes=random_minutes, seconds=random_seconds)

        # 如果当前时间已经过了计算出的时间，顺延到明天
        if datetime.now() >= publish_time:
            publish_time += timedelta(days=1)
            
        self.publish_time = publish_time.strftime("%Y-%m-%d %H:%M:%S")
        logger.info(f"生成随机定时发布时间: {self.publish_time}")

    async def upload(self, playwright: Playwright):
        # 1. 加载 Cookie 并启动浏览器
        with open(Config.COOKIE_PATH, 'r', encoding='utf-8') as f:
            cookie_data = json.load(f)
        
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context(permissions=["geolocation"])
        await context.add_cookies(cookie_data["cookies"])
        context = await set_init_script(context)
        page = await context.new_page()
        page.set_default_timeout(60000)

        try:
            logger.info("开始访问小红书创作者中心...")
            await page.goto("https://creator.xiaohongshu.com/publish/publish")

            # 初始仿生缓冲
            await simulate_mouse_move(page)
            await click_safe_blank(page)

            # 打开下拉菜单
            await page.locator(".dropdownBtn").click()
            await random_sleep(0.8, 1.5)

            # 点击写长文
            try:
                await page.locator("div").filter(has_text=re.compile(r"^写长文$")).nth(1).click(timeout=5000)
            except:
                logger.warning("首选定位‘写长文’失败，使用备用方案...")
                await page.get_by_text("写长文").click()
            
            # 【优化点1：页面跳转等待】确保长文弹窗/页面真正加载完毕再继续
            logger.info("等待进入‘写长文’创作界面...")
            await page.wait_for_load_state("domcontentloaded")
            await random_sleep(1.0, 2.0)
            
            try:
                new_work_btn = page.get_by_role("button", name="新的创作")
                await new_work_btn.wait_for(state="visible", timeout=10000)
                await simulate_mouse_move(page) 
                await new_work_btn.click()
            except Exception as e:
                logger.warning("未检测到‘新的创作’按钮，可能已直接处于编辑状态")

            # ================= 第一阶段：编辑器排版 =================
            logger.info("进入第一阶段编辑器，准备填入初步正文...")
            await random_sleep(1.0, 2.0) 
            await page.get_by_role("textbox", name="输入标题").fill(self.title)
            await random_sleep(0.5, 1.2) 
            
            await page.locator(".tiptap").fill(self.body)
            await random_sleep(1.5, 3.0) # 假装检查错别字

            logger.info("点击一键排版，生成 AI 封面...")
            await simulate_mouse_move(page)
            await page.get_by_role("button", name="一键排版").click()
            
            try:
                cover_container = page.locator(".template-cover-container")
                await cover_container.first.wait_for(state="visible", timeout=15000)
                
                await random_sleep(2.0, 4.0) # 假装挑选封面
                logger.info("正在选择第 2 个生成的 AI 封面...")
                await cover_container.nth(1).locator("img").first.click()
                await asyncio.sleep(0.5) 
            except Exception as e:
                logger.warning("自动选择特定封面失败，将兜底点击第一个")
                await page.locator(".template-cover-container img").first.click()

            await random_sleep(50.0, 60.0) # 重点缓冲，防狂点检测
                
            await page.get_by_role("button", name="下一步").click()

            # 【优化点1：页面跳转等待】点击下一步后，跳转到正式发布页需要时间
            logger.info("等待跳转到最终发布详情页...")
            # 等待网络空闲或等待目标页面的标志性元素出现
            await page.wait_for_load_state("domcontentloaded")
            await random_sleep(10.0, 15.0) # 重点缓冲，防狂点检测
            await click_safe_blank(page)

            # ================= 第二阶段：正式发布页 =================
            logger.info("开始第二阶段：最终正文与标签填充...")
            
            # 激活编辑区
            desc_area = page.get_by_role("paragraph")
            try:
                await desc_area.first.wait_for(state="visible", timeout=10000)
                await desc_area.first.click()
                await asyncio.sleep(0.5)
                await desc_area.first.click()
            except Exception as e:
                logger.warning("双击 paragraph 激活失败，尝试直接定位 textbox")

            final_desc_box = page.get_by_role("textbox").nth(1)

            # 清空并重新填入最终正文
            await final_desc_box.click()
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await final_desc_box.fill(self.body)
            
            await random_sleep(2.0, 3.0) 
            logger.success("第二次正文填充成功，等待渲染...")

            # 移动光标到末尾
            await final_desc_box.click() 
            await page.keyboard.press("Control+End")
            
            # 防止光标卡在 Emoji 前，补几下右方向键（带停顿模拟手敲）
            for _ in range(3):
                await page.keyboard.press("ArrowRight")
                await random_sleep(0.1, 0.3) 

            # 【优化点2：修复连续空行敲击被检测】
            # 不要连续无间隔地发送 Enter。用明显的延迟模拟人类换行行为
            logger.info("准备插入标签区换行...")
            await page.keyboard.press("Enter")
            await random_sleep(0.6, 1.2) # 停顿至少半秒以上
            await page.keyboard.press("Enter") # 如果必须留空行，这样间隔敲击才是安全的
            await random_sleep(0.5, 1.0)
            logger.info("光标已安全移至新行")

            # 提取并逐个输入标签
            tags = re.findall(r'#([^\s#]+)', self.tags_raw)
            for t in tags:
                logger.info(f"正在输入标签: #{t}")
                await final_desc_box.type(f"#{t}")
                await random_sleep(0.8, 1.5) # 等待后端弹出联想列表
                
                first_suggestion = page.locator(".tag-item").first
                try:
                    await first_suggestion.wait_for(state="visible", timeout=8000)
                    await simulate_mouse_move(page) 
                    await first_suggestion.click()
                    logger.success(f"成功绑定下拉推荐标签: #{t}")
                except:
                    logger.warning(f"未找到联想标签，使用普通文本: #{t}")
                    await page.keyboard.press("Space")
                
                # 标签与标签之间的打字思考间隔
                await page.keyboard.press("Space")
                await random_sleep(0.4, 0.9) 

            await page.keyboard.press("Enter")

            # 添加地点
            try:
                logger.info(f"正在搜索地点: {self.location}")
                await simulate_mouse_move(page)
                await page.get_by_text("添加地点").click(timeout=3000)
                location_input = page.get_by_role("textbox").nth(2)
                
                # 模拟缓慢输入
                await location_input.press_sequentially(self.location, delay=random.randint(60, 150))
                await random_sleep(1.0, 2.0) # 等待接口返回列表
                
                await page.locator("div").filter(has_text=re.compile(f"^{self.location}$")).first.click()
                logger.success("地点添加成功")
            except Exception as e:
                logger.error("地点添加未成功跳过，继续执行")

            # 设置定时发布
            logger.info("正在配置定时发布...")
            timer_container = page.locator(".post-time-switch-container")
            await timer_container.scroll_into_view_if_needed()
            await random_sleep(0.5, 1.5) 
            
            switch = timer_container.locator(".d-switch-simulator")
            is_on = await switch.evaluate("el => el.parentElement.classList.contains('checked')")
            if not is_on:
                await switch.click()
                await random_sleep(0.8, 1.2)
            
            time_input_container = page.locator("div").filter(has_text=re.compile(r"^定时发布"))
            time_input = time_input_container.get_by_role("textbox").first
            
            await time_input.wait_for(state="visible")
            await time_input.click()
            await random_sleep(0.2, 0.5)
            
            await page.keyboard.press("Home")
            await time_input.press_sequentially(self.publish_time, delay=random.randint(40, 100))
            await asyncio.sleep(0.5)
            
            for _ in range(20):
                await page.keyboard.press("Delete")
            
            # 点击边缘收起时间控件
            await click_safe_blank(page)
            await random_sleep(1.0, 2.0)

            # 最终发布
            logger.info("准备最终提交...")
            pub_btn = page.get_by_role("button", name="定时发布")
            await expect(pub_btn).to_have_text(re.compile("定时发布"), timeout=10000)
            
            await simulate_mouse_move(page) 
            logger.info("深呼吸，点击发布！")
            await random_sleep(1.0, 2.0) # 最后的犹豫时间
            await pub_btn.click()
            
            # 等待成功标识出现
            await page.get_by_role("button", name="立即返回").wait_for(state="visible", timeout=15000)
            logger.success("🎉 定时发布任务已成功提交！")

        except Exception as e:
            logger.error(f"发生异常中断: {e}")
            await page.screenshot(path=str(Config.ERROR_SCREENSHOT))
            logger.warning(f"已保存错误截图至: {Config.ERROR_SCREENSHOT}")
        finally:
            await browser.close()
            logger.info("浏览器已关闭，任务结束。")

# ==============================================================================
# 🚀 启动入口
# ==============================================================================
async def main():
    print("\n" + "="*50)
    print("🚀 小红书自动化发布脚本启动")
    print("="*50 + "\n")

    if not os.path.exists(Config.COOKIE_PATH):
        logger.error("找不到 Cookie 文件，请检查路径是否正确。")
        return

    content_data = parse_local_content()
    if not content_data: 
        logger.error("内容提取失败，中止流程。")
        return
    
    async with async_playwright() as playwright:
        publisher = XiaoHongShuPublisher(content_data)
        await publisher.upload(playwright)

if __name__ == "__main__":
    asyncio.run(main())