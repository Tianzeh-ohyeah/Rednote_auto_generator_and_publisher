import asyncio
import os
import sys
from pathlib import Path
from playwright.async_api import async_playwright

async def login():
    # 核心修正：锁定脚本所在目录，确保所有路径都在这里创建
    BASE_DIR = Path(__file__).resolve().parent
    cookies_dir = BASE_DIR / "cookies"
    cookies_dir.mkdir(exist_ok=True) # 只要你在桌面上运行，这里一定有权限
    account_file = cookies_dir / "account.json"
    
    print(f">>> 正在使用路径: {cookies_dir}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        await page.goto("https://creator.xiaohongshu.com/")
        print(">>> 请扫码登录，你有 180 秒时间... <<<")
        
        try:
            # 等待跳转到后台主页
            await page.wait_for_url("**/new/home**", timeout=180000)
            
            # 保存 Cookie 到绝对路径
            await context.storage_state(path=str(account_file))
            print(f">>> 登录成功，Cookie 已安全保存到: {account_file} <<<")
        except Exception as e:
            print(f">>> 登录超时或出错: {e} <<<")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(login())