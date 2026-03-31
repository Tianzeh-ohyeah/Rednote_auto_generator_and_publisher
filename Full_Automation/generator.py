import os
import time
import random
import re
import shutil
from google import genai
from datetime import datetime
from dotenv import load_dotenv

# --- 1. 初始化与算力探测 ---
load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

class SimpleLogger:
    def info(self, msg): print(f"  [INFO] {datetime.now().strftime('%H:%M:%S')} - {msg}")
    def error(self, msg): print(f"  [ERROR] {datetime.now().strftime('%H:%M:%S')} - {msg}")
    def success(self, msg): print(f"  [SUCCESS] {datetime.now().strftime('%H:%M:%S')} - {msg}")

logger = SimpleLogger()

# 强制锁定基础工作目录 (根据你的要求)
BASE_DIR = r"C:\Users\tianzeh\Desktop\Full_Automation"
TODAY_DIR = os.path.join(BASE_DIR, "Today_File")
HISTORY_DIR = os.path.join(BASE_DIR, "History_File")

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

# --- 2. 核心调度逻辑：带 Fallback 的生成器 ---
def safe_generate_with_fallback(prompt):
    model_pool = get_intelligent_model_pool()
    
    for model_name in model_pool:
        try:
            logger.info(f"正在尝试调用算力节点: {model_name}")
            res = client.models.generate_content(model=model_name, contents=prompt)
            if res and res.text:
                return res.text, model_name
        except Exception as e:
            # 如果是频率限制，稍作等待并尝试下一个模型
            if "429" in str(e):
                time.sleep(1.5)
            continue 
    return None, None

def load_prompt_template(file_name="daily_novel_template.txt"):
    """从绝对路径加载 Prompt 模板"""
    template_path = os.path.join(BASE_DIR, file_name)
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"找不到 Prompt 模板文件: {template_path}")
        
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()

def get_previous_context(file_path):
    """读取前一天的日记作为连载上下文"""
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            # 截取前 800 字，避免上下文过长导致 Token 浪费或偏题
            return content[:800]
    return "这是日记的第一篇。今天是我回国入职现在的公司的第N天，昨晚猫跑酷没睡好，今天又要去面对工作的牛马日常。"

def generate_healing_content(previous_context):
    # 1. 准备变量
    random_seed = f"{datetime.now().strftime('%Y%m%d%H%M')}_{random.randint(1000, 9999)}"
    
    # 2. 从外部文件加载模板并注入变量
    try:
        template = load_prompt_template("xiaoshuo.txt")
        # 注入随机种子和昨天的记忆
        prompt = template.replace("{random_seed}", random_seed).replace("{previous_context}", previous_context)
    except Exception as e:
        logger.error(f"加载模板失败，使用内置兜底 Prompt: {e}")
        prompt = f"请以海归佛系打工人第一人称写一篇日记，接续昨天的内容：{previous_context}。包含标题、正文、标签格式。"

    content, used_model = safe_generate_with_fallback(prompt)
    if content:
        # 【格式保险】：严格清理 AI 可能加上的 Markdown 符号，确保下游脚本不报错
        content = content.replace("**标题：**", "标题：").replace("**正文：**", "正文：").replace("**标签：**", "标签：")
        content = content.replace("### 标题", "标题：").replace("### 正文", "正文：").replace("### 标签", "标签：")
        content = content.replace("**", "") # 清理正文里偶发的加粗
        
        logger.success(f"算力节点 [{used_model}] 推演成功")
        return content.strip()
    else:
        raise Exception("所有算力节点均已耗尽或未响应")

# --- 3. 执行入口 ---
if __name__ == "__main__":
    print("\n" + "="*50)
    print("🚀 启动 [楚门打工日记] 全自动化连载引擎")
    print("="*50 + "\n")
    try:
        # 核心目录初始化
        os.makedirs(TODAY_DIR, exist_ok=True)
        os.makedirs(HISTORY_DIR, exist_ok=True)
        
        today_file_path = os.path.join(TODAY_DIR, "content.txt")
        history_file_path = os.path.join(HISTORY_DIR, f"content_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")

        # 读取前情提要
        logger.info(f"正在从 {today_file_path} 读取前情提要...")
        prev_context = get_previous_context(today_file_path)
        
        # 核心生成逻辑
        content = generate_healing_content(prev_context)
        
        # 文件归档流转
        if os.path.exists(today_file_path):
            shutil.move(today_file_path, history_file_path)
            logger.info(f"昨日内容已安全归档至: {history_file_path}")
            
        # 写入今日新内容
        with open(today_file_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.success(f"今日连载内容已写入目标文件: {today_file_path}")  

    except Exception as e:
        logger.error(f"引擎运行失败: {e}")