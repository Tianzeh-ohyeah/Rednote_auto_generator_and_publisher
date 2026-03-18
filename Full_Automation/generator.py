import os
import time
import random
import re
from google import genai
from datetime import datetime
from dotenv import load_dotenv

# --- 1. 初始化与算力探测 ---
load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

class SimpleLogger:
    def info(self, msg): print(f"  [INFO] {msg}")
    def error(self, msg): print(f"  [ERROR] {msg}")
    def success(self, msg): print(f"  [SUCCESS] {msg}")

logger = SimpleLogger()

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
            res = client.models.generate_content(model=model_name, contents=prompt)
            if res and res.text:
                return res.text, model_name
        except Exception as e:
            # 如果是频率限制，稍作等待并尝试下一个模型
            if "429" in str(e):
                time.sleep(1.5)
            continue 
    return None, None

def load_prompt_template(file_name="anti_pua_template.txt"):
    """从本地文件加载 Prompt 模板"""
    # 获取当前脚本所在目录
    base_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(base_dir, file_name)
    
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"找不到 Prompt 模板文件: {template_path}")
        
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()

def generate_healing_content():
    # 1. 准备变量
    random_seed = f"{datetime.now().strftime('%Y%m%d%H%M')}_{random.randint(1000, 9999)}"
    
    # 2. 【核心修改】：从外部文件加载模板并注入变量
    try:
        template = load_prompt_template("anti_pua_template.txt")
        # 使用 .format() 将文件里的 {random_seed} 替换掉
        prompt = template.format(random_seed=random_seed)
    except Exception as e:
        logger.error(f"加载模板失败，使用内置兜底 Prompt: {e}")
        prompt = f"请生成一段职场反PUA内容，种子是{random_seed}" # 这里写个简单的兜底

    content, used_model = safe_generate_with_fallback(prompt)
    if content:
        # 【额外保险】：去掉 AI 可能习惯性加上的 Markdown 加粗符号
        content = content.replace("**标题：**", "标题：").replace("**正文：**", "正文：").replace("**标签：**", "标签：")
        content = content.replace("### 标题", "标题：").replace("### 正文", "正文：").replace("### 标签", "标签：")
        
        print(f"✨ 算力节点 [{used_model}] 推演成功")
        return content.strip()
    else:
        raise Exception("所有算力节点均已耗尽或未响应")
        
# --- 3. 执行入口 ---
if __name__ == "__main__":
    try:
        # 获取当前脚本所在文件夹的绝对路径 (Full_Automation)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        # 拼接目标路径
        target_dir = os.path.join(base_dir, "Today_File")
        file_path = os.path.join(target_dir, "content.txt")
        # 核心修复：检查并创建文件夹
        if os.path.isfile(target_dir):
            # 如果 Today_File 居然是个文件，先把它删了，否则没法建文件夹
            os.remove(target_dir)
        os.makedirs(target_dir, exist_ok=True)

        # 生成内容
        content = generate_healing_content()
        
        # 写入文件
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ 内容已写入: {file_path}")  

    except Exception as e:
        print(f"❌ 运行失败: {e}")