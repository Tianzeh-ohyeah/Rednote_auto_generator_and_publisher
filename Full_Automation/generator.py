import os
import time
import random
import sys
import shutil
import requests
from google import genai
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# --- 1. 初始化与日志系统 ---
load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

class SimpleLogger:
    def info(self, msg): print(f"  [INFO] {datetime.now().strftime('%H:%M:%S')} - {msg}")
    def error(self, msg): print(f"  [ERROR] {datetime.now().strftime('%H:%M:%S')} - {msg}")
    def success(self, msg): print(f"  [SUCCESS] {datetime.now().strftime('%H:%M:%S')} - {msg}")
    # [NEW] 增加一个专门用于播报热点抓取的格式
    def fetch(self, msg): print(f"  [FETCH] {datetime.now().strftime('%H:%M:%S')} - 📡 {msg}")

logger = SimpleLogger()

# 强制锁定基础工作目录
BASE_DIR = r"C:\Users\tianzeh\Desktop\Full_Automation"
TODAY_DIR = os.path.join(BASE_DIR, "Today_File")
HISTORY_DIR = os.path.join(BASE_DIR, "History_File")

# ==========================================
# [NEW MODULE] 抓热点感知层 (Information Fetcher)
# ==========================================
TIMEOUT = 10
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

def fetch_weibo() -> list[dict]:
    logger.fetch("正在扫描 [微博] 实时热搜榜单...")
    try:
        resp = requests.get("https://weibo.com/ajax/side/hotSearch", headers={**HEADERS, "Referer": "https://weibo.com/"}, timeout=TIMEOUT)
        data = resp.json()
        items = []
        for entry in data.get("data", {}).get("realtime", []):
            note = entry.get("note", "")
            if note: items.append({"title": note, "source": "微博", "hot": entry.get("num", 0)})
        logger.fetch(f"[微博] 扫描完成，捕获 {len(items)} 条数据。")
        return items
    except Exception as e:
        logger.error(f"微博热搜抓取失败: {e}")
        return []

def fetch_toutiao() -> list[dict]:
    logger.fetch("正在扫描 [今日头条] 实时热榜...")
    try:
        resp = requests.get("https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc", headers=HEADERS, timeout=TIMEOUT)
        data = resp.json()
        items = []
        for entry in data.get("data", []):
            title = entry.get("Title", "")
            if title: items.append({"title": title, "source": "今日头条", "hot": int(entry.get("HotValue", 0) or 0)})
        logger.fetch(f"[今日头条] 扫描完成，捕获 {len(items)} 条数据。")
        return items
    except Exception as e:
        logger.error(f"头条热榜抓取失败: {e}")
        return []

def fetch_baidu() -> list[dict]:
    logger.fetch("正在扫描 [百度] 实时热搜...")
    try:
        resp = requests.get("https://top.baidu.com/api/board?platform=wise&tab=realtime", headers=HEADERS, timeout=TIMEOUT)
        data = resp.json()
        items = []
        for card in data.get("data", {}).get("cards", []):
            top_content = card.get("content", [])
            if not top_content: continue
            entries = top_content[0].get("content", []) if isinstance(top_content[0], dict) else top_content
            for entry in entries:
                word = entry.get("word", "")
                if word: items.append({"title": word, "source": "百度", "hot": int(entry.get("hotScore", 0) or 0)})
        logger.fetch(f"[百度] 扫描完成，捕获 {len(items)} 条数据。")
        return items
    except Exception as e:
        logger.error(f"百度热搜抓取失败: {e}")
        return []

def deduplicate(items: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for item in items:
        title = item["title"].strip()
        if title and title not in seen:
            seen.add(title)
            result.append(item)
    return result

def get_trending_context(limit=5) -> str:
    """整合各大平台热搜，并格式化为一段文本，准备喂给大模型"""
    logger.info("启动全网热点感知矩阵...")
    all_items = []
    
    # 串行/并行抓取
    all_items.extend(fetch_weibo())
    all_items.extend(fetch_toutiao())
    all_items.extend(fetch_baidu())
    
    all_items = deduplicate(all_items)
    
    if not all_items:
        logger.error("所有感知节点均失效，将使用空的热点上下文。")
        return "今日暂无特别的全网热点。"

    # 按原始热度粗略排序，并取前 limit 条
    all_items.sort(key=lambda x: int(x.get("hot", 0) or 0), reverse=True)
    top_items = all_items[:limit]
    
    # 格式化为 Prompt 可读的字符串
    context_str = "以下是今天全网最新的热门话题：\n"
    for idx, item in enumerate(top_items, 1):
        context_str += f"{idx}. [{item['source']}] {item['title']} \n"
    
    logger.success(f"已成功凝练 {len(top_items)} 条核心热点情报，准备注入创作中枢。")
    return context_str

# ==========================================
# [ORIGINAL MODULE] 内容生成与引擎控制 (Core Logic)
# ==========================================

def get_intelligent_model_pool():
    """探测可用模型并按性能排序"""
    try:
        models = client.models.list()
        pool = []
        black_list = ["computer-use", "embedding", "tts", "imagen", "aqa", "vision"]
        for m in models:
            m_name = m.name.lower()
            if "gemini" in m_name and not any(x in m_name for x in black_list):
                if any(v in m_name for v in ["flash", "pro"]):
                    full_name = m.name if m.name.startswith("models/") else f"models/{m.name}"
                    pool.append(full_name)
        
        def model_priority(name):
            n = name.lower()
            if "3-flash" in n: return 10
            if "2.0-flash" in n: return 8
            if "1.5-pro" in n: return 6
            if "1.5-flash" in n: return 4
            return 0
            
        pool.sort(key=model_priority, reverse=True)
        return pool[:3] if pool else ["models/gemini-1.5-flash"]
    except:
        return ["models/gemini-1.5-flash"]

def safe_generate_with_fallback(prompt):
    model_pool = get_intelligent_model_pool()
    
    for model_name in model_pool:
        try:
            logger.info(f"正在尝试调用算力节点: {model_name}")
            res = client.models.generate_content(model=model_name, contents=prompt)
            if res and res.text:
                return res.text, model_name
        except Exception as e:
            if "429" in str(e): time.sleep(1.5)
            continue 
    return None, None

def load_prompt_template(file_name="daily_novel_template.txt"):
    template_path = os.path.join(BASE_DIR, file_name)
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"找不到 Prompt 模板文件: {template_path}")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()

def get_previous_context(file_path):
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            return content[:800]
    return "这是日记的第一篇。今天是我回国入职现在的公司的第N天，昨晚猫跑酷没睡好，今天又要去面对工作的牛马日常。"

# [MODIFIED] 传入热点参数 trending_context
def generate_healing_content(previous_context, trending_context):
    random_seed = f"{datetime.now().strftime('%Y%m%d%H%M')}_{random.randint(1000, 9999)}"
    
    # [NEW] 核心指令：要求科普，禁止负面吐槽
    intel_guidance = """
    指令增强：
    1. 必须聚焦于“即将发生”或“最近发生”的事件。
    2. 严禁写成“避雷贴”，请将分析转化为“参与攻略”或“技术科普”。
    3. 如果提到明星或电影，请科普其背后的专业知识（如：IMAX规格、舞台工程、票务分发逻辑）。
    4. 确保数据真实（如：北京各大影院的均价、展会的人均消费）。
    """

    try:
        template = load_prompt_template("xiaoshuo.txt")
        # 注入逻辑
        prompt = template.replace("{random_seed}", random_seed)\
                         .replace("{previous_context}", previous_context)\
                         .replace("{trending_context}", trending_context + "\n" + intel_guidance)
    except Exception as e:
        logger.error(f"加载模板失败: {e}")
        prompt = f"请针对以下热点写一篇硬核科普帖，要求事实准确，禁止避雷：{trending_context}，今日话题不可以和昨天的一样：{previous_context}"

    logger.info("引擎正在分析事实并构建科普逻辑...")
    content, used_model = safe_generate_with_fallback(prompt)

    if content:
        # 【格式保险】：严格清理 AI 可能加上的 Markdown 符号，确保下游脚本不报错
        content = content.replace("**标题：**", "标题：").replace("**正文：**", "正文：").replace("**标签：**", "标签：")
        content = content.replace("### 标题", "标题：").replace("### 正文", "正文：").replace("### 标签", "标签：")
        content = content.replace("**", "") # 清理正文里偶发的加粗 
        
    if "标题：" in content and "正文：" in content and "标签：" in content:  
        logger.success(f"算力节点 [{used_model}] 推演成功")
        return content.strip()
    else:
        raise Exception("所有算力节点均已耗尽或未响应")

# --- 3. 执行入口 ---
if __name__ == "__main__":
    print("\n" + "="*50)
    print("🚀 启动 [自动生成日记] 全自动化连载引擎 (Agentic Version)")
    print("="*50 + "\n")
    try:
        os.makedirs(TODAY_DIR, exist_ok=True)
        os.makedirs(HISTORY_DIR, exist_ok=True)
        
        today_file_path = os.path.join(TODAY_DIR, "content.txt")
        history_file_path = os.path.join(HISTORY_DIR, f"content_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")

        # [STEP 1] 获取实时外部世界数据 (热点感知)
        trends_text = get_trending_context(limit=15) # 抓取前6条热点

        # [STEP 2] 读取内部历史记忆 (前情提要)
        logger.info(f"正在从 {today_file_path} 读取前情提要...")
        prev_context = get_previous_context(today_file_path)
        
        # [STEP 3] 融合生成新内容
        content = generate_healing_content(prev_context, trends_text)
        
        # [STEP 4] 文件归档流转
        if os.path.exists(today_file_path):
            shutil.move(today_file_path, history_file_path)
            logger.info(f"昨日内容已安全归档至: {history_file_path}")
            
        with open(today_file_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.success(f"今日连载内容已写入目标文件: {today_file_path}")  

    except Exception as e:
        logger.error(f"引擎运行失败: {e}")