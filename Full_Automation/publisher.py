# -*- coding: utf-8 -*-
import asyncio
import os
import re
import json
from pathlib import Path
from datetime import datetime
from playwright.async_api import Playwright, async_playwright, expect

class Config:
    BASE_DIR = Path(__file__).resolve().parent
    CONTENT_FILE = BASE_DIR / "Today_File" / "content.txt"
    COOKIE_PATH = r"C:\Users\tianzeh\Desktop\Full_Automation\cookies\account.json"
    ERROR_SCREENSHOT = BASE_DIR / "debug_error.png"

class MockLogger:
    def __init__(self, name): self.name = name
    def info(self, msg): print(f"[{self.name} INFO] {datetime.now().strftime('%H:%M:%S')} {msg}")
    def success(self, msg): print(f"[{self.name} SUCCESS] {datetime.now().strftime('%H:%M:%S')} {msg}")
    def error(self, msg): print(f"[{self.name} ERROR] {datetime.now().strftime('%H:%M:%S')} {msg}")
    def warning(self, msg): print(f"[{self.name} WARNING] {datetime.now().strftime('%H:%M:%S')} {msg}") # 补上这一行

logger = MockLogger("XHS_Uploader")

# ==============================================================================
# 🛠️ 核心函数
# ==============================================================================

async def set_init_script(context):
    await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => false});")
    return context

def parse_local_content():
    if not Config.CONTENT_FILE.exists():
        logger.error(f"找不到内容文件: {Config.CONTENT_FILE}")
        return None
        
    raw_text = Config.CONTENT_FILE.read_text(encoding='utf-8').strip()
    try:
        # 1. 提取标题
        title_match = re.search(r"标题：\s*(.*?)(?:\n|$)", raw_text)
        title = title_match.group(1).strip() if title_match else "无标题"
        
        # 2. 提取标签 (取最后一行包含“标签：”的内容)
        tags_match = re.search(r"标签：\s*(.*)$", raw_text, re.MULTILINE)
        tags = tags_match.group(1).strip() if tags_match else ""
        
        # 3. 提取正文 [核心修改点]
        # 找到“正文：”字符串结束后的起始位置
        # 不要硬编码 +3，用 len() 更安全，并配合 strip() 自动干掉前后的换行/空格
        marker_start = "正文："
        marker_end = "标签："
        
        if marker_start in raw_text and marker_end in raw_text:
            start_idx = raw_text.find(marker_start) + len(marker_start)
            end_idx = raw_text.find(marker_end)
            # 这里的切片会保留 start_idx 到 end_idx 之间的所有原始字符（包括 emoji）
            body = raw_text[start_idx:end_idx].strip()
        else:
            logger.error("文中缺少‘正文：’或‘标签：’标记")
            return None
        
        # 打印调试，确认解析出的 body 结尾是否有 emoji
        print(f"--- 解析结果预览 ---")
        print(f"标题: {title}")
        print(f"正文末尾字符: {body[-10:]}") # 这里你可以看到 emoji 还在不在
        print(f"------------------")
        
        return {"title": title, "body": body, "tags": tags}
    
    except Exception as e:
        logger.error(f"解析内容失败: {e}")
        return None

# ==============================================================================
# 📝 发布类 (手动注入 Cookie 核心)
# ==============================================================================
class XiaoHongShuPublisher:
    def __init__(self, data: dict, location: str = "中国戏曲学院"):
        self.title = data['title']
        self.body = data['body']
        self.tags_raw = data['tags']
        self.location = location
        
        # [修改点：严格生成英文冒号时间格式]
        from datetime import datetime, timedelta
        today_6pm = datetime.now().replace(hour=18, minute=0, second=0, microsecond=0)
        if datetime.now() >= today_6pm:
            today_6pm += timedelta(days=1)
        self.publish_time = today_6pm.strftime("%Y-%m-%d %H:%M")
    
    async def _clear_popups(self, page):
        selectors = ["img[alt='Close']", "text=我知道了", "text=关闭", "div[role='dialog'] button[aria-label='Close']"]
        for sel in selectors:
            try:
                if await page.locator(sel).first.is_visible(timeout=500):
                    await page.locator(sel).first.click()
            except: continue

    async def upload(self, playwright: Playwright):
        with open(Config.COOKIE_PATH, 'r', encoding='utf-8') as f:
            cookie_data = json.load(f)
        
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context(permissions=["geolocation"])
        await context.add_cookies(cookie_data["cookies"])
        context = await set_init_script(context)
        page = await context.new_page()
        page.set_default_timeout(60000)

        try:
            logger.info(f"[-] 开始发布: {self.title}")
            await page.goto("https://creator.xiaohongshu.com/publish/publish")

            await page.locator(".dropdownBtn").click()
            await asyncio.sleep(1)
            try:
                # [修改点：完全同步 codegen 路径，利用正则精确定位“写长文”]
                await page.locator("div").filter(has_text=re.compile(r"^写长文$")).nth(1).click(timeout=5000)
            except:
                logger.error("无法定位‘写长文’按钮，尝试备用坐标点击...")
                await page.get_by_text("写长文").click()
            
            logger.info("[-] 等待进入创作界面...")
            
            try:
                new_work_btn = page.get_by_role("button", name="新的创作")
                await new_work_btn.wait_for(state="visible", timeout=10000)
                await new_work_btn.click()
            except Exception as e:
                logger.error("未能找到“新的创作”按钮，尝试直接填入内容...")

            # ================= 第一阶段：编辑器排版 =================
            await page.get_by_role("textbox", name="输入标题").fill(self.title)
            # [修改点：第一次填入正文，不把标签写进这里]
            await page.locator(".tiptap").fill(self.body)

            logger.info("[-] 点击一键排版，生成 AI 封面...")
            await page.get_by_role("button", name="一键排版").click()
            try:
                # 等待封面模板容器出现
                cover_container = page.locator(".template-cover-container")
                await cover_container.first.wait_for(state="visible", timeout=15000)
                
                # 你抓取的代码里 2, 5, 7 都可以。
                # nth(1) 代表第 2 个，nth(4) 代表第 5 个，nth(6) 代表第 7 个。
                # 这里我们选第 2 个，因为它最稳。
                logger.info("[-] 正在选择第 2 个生成的 AI 封面...")
                await cover_container.nth(1).locator("img").first.click()
                
                # 稍微停半秒，确保选中态切换
                await asyncio.sleep(0.5) 
            except Exception as e:
                logger.warning(f"[-] 自动选择封面失败，将使用默认首选: {e}")
                # 如果自动选失败了，兜底点击第一个
                await page.locator(".template-cover-container img").first.click()
            await page.get_by_role("button", name="下一步").click()

            # ================= 第二阶段：正式发布页 =================
            logger.info("[-] 进入发布详情页，准备录入正文和标签...")

            desc_area = page.get_by_role("paragraph")
            try:
                await desc_area.first.wait_for(state="visible", timeout=10000)
                # 复刻录制器的操作：双击或点击两次以确保激活
                await desc_area.first.click()
                await asyncio.sleep(0.5)
                await desc_area.first.click()
                logger.info("[-] 已通过点击段落元素激活编辑区")
            except Exception as e:
                logger.warning(f"[-] 未能通过 paragraph 激活，尝试直接定位 textbox: {e}")

            # 1. 重新精确定位描述框
            # 小红书发布页通常有两个 textbox，第一个是标题（继承来的），第二个是正文
            final_desc_box = page.get_by_role("textbox").nth(1)

            await final_desc_box.click()
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            
            # 录制器里直接 fill 成功了，我们也用 fill
            await final_desc_box.fill(self.body)
            await asyncio.sleep(1.5) 
            logger.info("[-] 正文已填入，等待 Emoji 节点渲染稳定...")
            logger.success("[-] 第二次正文填充成功！")

            # --- 关键修复 2：连环击确保光标在绝对末尾 ---
            # 有时候 Control+End 会停在 Emoji 前面，补两次 ArrowRight 强制向后移
            await final_desc_box.click() # 重新获取焦点
            await page.keyboard.press("Control+End")
            for _ in range(3):
                await page.keyboard.press("ArrowRight")

            # 4. 移动光标到末尾，准备打标签
            await page.keyboard.press("Control+End")
            await page.keyboard.press("Enter")
            await page.keyboard.press("Enter")
            logger.success("[-] 光标已锁定在正文最下方")

            # 5. 逐个打标签，这里改用 page.keyboard.type，比 locator.press_sequentially 更底层
            # [修改点：精准打标签逻辑 - 彻底锁定正文末尾]
            tags = re.findall(r'#([^\s#]+)', self.tags_raw)

            # 强制将光标移到文本末尾，并确保与正文空开一行
            await final_desc_box.click()
            await page.keyboard.press("Control+End") 
            await page.keyboard.press("Enter")

            for t in tags:
                logger.info(f"[-] 正在模糊匹配标签: #{t}")
                
                # 1. 输入 # 和标签名
                await final_desc_box.type(f"#{t}")
                # 稍微等一下让后端查询列表浮出
                await asyncio.sleep(1.0)
                
                # 2. 核心优化：模糊匹配
                # 不再匹配精确文字，而是匹配标签列表里的第一个容器(通常第一个就是最相关的)
                # 使用 CSS 选择器定位标签列表项的第一个元素
                first_suggestion = page.locator(".tag-item").first
                
                try:
                    # 等待下拉列表容器出现
                    await first_suggestion.wait_for(state="visible", timeout=10000)
                    # 点击第一个匹配项，通常小红书会把最相似的放第一个
                    await first_suggestion.click()
                    logger.success(f"  [+] 成功通过模糊匹配绑定: #{t}")
                except:
                    # 如果连下拉列表都没出来，说明该词太冷门，直接按空格跳过
                    logger.warning(f"  [!] 未找到 #{t} 的相关联标签，执行默认空格跳过")
                    await page.keyboard.press("Space")
                
                # 3. 每个标签后紧跟一个空格，保证视觉独立
                await page.keyboard.press("Space")
                await asyncio.sleep(0.5)

            # 6. 检查一下：如果最后还是没变色，补一记“Enter”
            await page.keyboard.press("Enter")

            # [修改点：完美同步 codegen 的添加地点逻辑]
            try:
                logger.info("[-] 开始添加地点...")
                await page.get_by_text("添加地点").click(timeout=3000)
                location_input = page.get_by_role("textbox").nth(2)
                await location_input.fill(self.location)
                await asyncio.sleep(1.5) 
                await page.locator("div").filter(has_text=re.compile(f"^{self.location}$")).first.click()
            except Exception as e:
                logger.error(f"地点添加异常: {e}")

            # 【修复 3：定时发布时间格式与注入问题】
            timer_container = page.locator(".post-time-switch-container")
            await timer_container.scroll_into_view_if_needed()
            
            # 点击开启定时发布开关
            switch = timer_container.locator(".d-switch-simulator")
            is_on = await switch.evaluate("el => el.parentElement.classList.contains('checked')")
            if not is_on:
                await switch.click()
                await asyncio.sleep(1)
            
            # 基于 codegen 定位输入框
            time_input_container = page.locator("div").filter(has_text=re.compile(r"^定时发布"))
            time_input = time_input_container.get_by_role("textbox").first
            
            await time_input.wait_for(state="visible")
            await time_input.click()
            
            # ======== 核心修复：先填入，后删除，全程保持非空 ========
            
            # 1. 强制将光标移动到输入框最开头
            await page.keyboard.press("Home")
            
            # 2. 慢慢填入新时间。
            # 假设旧时间是 "2026-03-16 18:40"，填完后会变成 "2026-03-16 21:002026-03-16 18:40"
            await time_input.press_sequentially(self.publish_time, delay=50)
            await asyncio.sleep(0.5)
            
            # 3. 此时光标正好夹在新时间和旧时间的中间。
            # 直接按 Delete 键向右侧删除旧时间。时间格式固定是 16 个字符，保险起见我们循环按 20 次。
            for _ in range(20):
                await page.keyboard.press("Delete")
            
            # 模拟点击页面空白处（你的 codegen 里的 .publish-page click），让日历控件完全收起，保存数值
            await page.locator(".publish-page").click(position={"x": 0, "y": 0})
            await asyncio.sleep(1)

            # 6. 最后确认按钮并点击
            pub_btn = page.get_by_role("button", name="定时发布")
            await expect(pub_btn).to_have_text(re.compile("定时发布"), timeout=10000)
            await pub_btn.click()
            
            # 确认发布成功跳转
            await page.get_by_role("button", name="立即返回").wait_for(state="visible", timeout=10000)
            logger.success("🚀 恭喜，定时发布任务已成功提交！")

        except Exception as e:
            logger.error(f"流程异常: {e}")
            await page.screenshot(path=str(Config.ERROR_SCREENSHOT))
        finally:
            await browser.close()

async def main():
    if not os.path.exists(Config.COOKIE_PATH):
        logger.error("❌ 找不到 Cookie 文件，请检查路径")
        return

    content_data = parse_local_content()
    if not content_data: 
        logger.error("❌ 内容解析为空，请检查 content.txt 格式")
        return
    
    async with async_playwright() as playwright:
        publisher = XiaoHongShuPublisher(content_data)
        await publisher.upload(playwright)

if __name__ == "__main__":
    asyncio.run(main())