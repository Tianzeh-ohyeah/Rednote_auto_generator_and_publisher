import asyncio
import edge_tts
import os
import re
import sys
import textwrap
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# =================================================================
# SECTION 1: 导入 (兼容 MoviePy 2.x)
# =================================================================
try:
    from moviepy import VideoFileClip, AudioFileClip, ImageClip, CompositeVideoClip, concatenate_videoclips
except ImportError:
    print("❌ 错误：请运行 pip install moviepy --pre (确保是v2版本)")
    sys.exit()

# --- 路径锁定 ---
ROOT_DIR = r"C:\Users\tianzeh\Desktop\Full_Automation"
TARGET_DIR = os.path.join(ROOT_DIR, "Today_File")

if not os.path.exists(TARGET_DIR):
    os.makedirs(TARGET_DIR, exist_ok=True)
os.chdir(TARGET_DIR)

# --- 文件配置 ---
CONTENT_FILE = "content.txt"
TEMPLATE_VIDEO = "aivideo.mp4"
TEMP_VOICE = "temp_voice.mp3"
OUTPUT_VIDEO = "Final_Pua_Judgment.mp4"
FONT_PATH = "C:/Windows/Fonts/simhei.ttf" 

# =================================================================
# SECTION 2: 动态字幕生成核心引擎
# =================================================================
def create_single_subtitle_image(text, size=(704, 1248)):
    """
    生成单句字幕的透明图层，确保文字居中并在画面下方黄金分割点（Lower Third）
    """
    img = Image.new('RGBA', size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(FONT_PATH, 42)
    except:
        font = ImageFont.load_default()

    # 自动换行处理（防止单句过长）
    wrapped_lines = textwrap.wrap(text, width=22, break_long_words=False)
    
    x_center = size[0] // 2
    # 将字幕基准线设在画面的中下方 (约 75% 处)
    y_cursor = int(size[1] * 0.75) 

    for line in wrapped_lines:
        # 绘制黑色描边 (提高对比度，防止背景过亮看不清)
        for off in [(-3,-3), (3,-3), (-3,3), (3,3), (-3,0), (3,0), (0,-3), (0,3)]:
            draw.text((x_center+off[0], y_cursor+off[1]), line, font=font, fill="black", anchor="mm")
        # 绘制主字幕 (主色为亮金黄)
        draw.text((x_center, y_cursor), line, font=font, fill="#FFD700", anchor="mm")
        y_cursor += 60 # 多行间距
        
    return np.array(img)

def generate_dynamic_subtitles(text, total_audio_duration, video_size):
    """
    【核心逻辑】：将长文本按标点符号切片，根据字数占比，智能估算每句话出现的时间。
    这就是“伪时间轴”，让字幕能随时间流动，不再是死板的一坨。
    """
    # 1. 文本切片 (按标点切分，保留标点)
    raw_chunks = re.split(r'([。！？.!?,\n])', text)
    chunks = []
    current_chunk = ""
    for item in raw_chunks:
        current_chunk += item
        if re.match(r'[。！？.!?,\n]', item) or item == raw_chunks[-1]:
            clean_chunk = current_chunk.strip()
            if clean_chunk:
                chunks.append(clean_chunk)
            current_chunk = ""

    # 2. 计算每个字符分配到的时间
    total_chars = sum(len(c) for c in chunks)
    time_per_char = total_audio_duration / max(total_chars, 1)

    print(f"   -> 预估字幕总字数: {total_chars} | 每个字符分配时间: {time_per_char:.3f}s")

    # 3. 生成对应的 ImageClip 序列
    subtitle_clips = []
    current_time = 0.0

    for chunk in chunks:
        chunk_duration = len(chunk) * time_per_char
        end_time = current_time + chunk_duration
        
        # 容错：确保不超过总音频时长
        if end_time > total_audio_duration:
            end_time = total_audio_duration

        img_array = create_single_subtitle_image(chunk, size=video_size)
        
        # MoviePy 2.x API: 设定持续时间、出现时间、消失时间、位置
        clip = (ImageClip(img_array)
                .with_duration(chunk_duration)
                .with_start(current_time)
                .with_end(end_time)
                .with_position(('center', 'center'))) # Image内部已排版到底部，这里设为center即可
        
        subtitle_clips.append(clip)
        current_time = end_time

    return subtitle_clips

# =================================================================
# SECTION 3: 主流程
# =================================================================
async def main():
    print("==================================================")
    print("🚀 [职场判官] 完美重构版工作流启动...")
    print("==================================================")
    
    # ---------------------------------------------------------
    # 步骤 1: 解析文案
    # ---------------------------------------------------------
    print("\n[1/5] 📄 正在解析文案...")
    if not os.path.exists(CONTENT_FILE):
        print(f"❌ 找不到文件: {CONTENT_FILE}")
        return
        
    text = Path(CONTENT_FILE).read_text(encoding='utf-8').strip()
    cn = re.search(r"今日反击金句：\s*(.*?)\n", text).group(1).strip()
    en_raw = re.search(r"英文翻译：\s*(.*?)\n", text).group(1).strip()
    
    cn_clean = re.sub(r'[^\w\s，！。？!?,]', '', cn).strip()
    en_clean = re.sub(r'（.*?）', '', en_raw)
    en_clean = re.sub(r'[^\w\s,!?\']', '', en_clean).strip()
    
    # 将中文和英文合并用于字幕分割
    full_display_text = f"{cn_clean}\n{en_clean}"
    # 语音文本加入停顿
    voice_script = f"{cn_clean} 。。。 {en_clean}" 
    print(f"   -> 提取中文: {cn_clean[:15]}...")
    print(f"   -> 提取英文: {en_clean[:15]}...")

    # ---------------------------------------------------------
    # 步骤 2: 生成自然语速配音
    # ---------------------------------------------------------
    print("\n[2/5] 🎙️ 正在生成AI语音...")
    # 修复语速问题：移除 rate="+25%"，改回自然语速（或+5%微调），增加爆发力和清晰度
    communicate = edge_tts.Communicate(voice_script, "zh-CN-YunxiNeural", pitch="+10Hz", rate="+0%", volume="+30%")
    await communicate.save(TEMP_VOICE)
    
    audio = AudioFileClip(TEMP_VOICE)
    audio_dur = audio.duration
    print(f"   -> 语音生成完毕。总时长: {audio_dur:.2f}秒 (已恢复自然语速)")

    # ---------------------------------------------------------
    # 步骤 3: 视频逻辑匹配与时间轴对齐 (拒绝0.5倍速)
    # ---------------------------------------------------------
    print("\n[3/5] 🎬 正在处理背景视频与时间轴...")
    base_clip = VideoFileClip(TEMPLATE_VIDEO)
    
    # 核心修复：获取并尊重原视频的FPS，不再无脑强压60帧
    native_fps = base_clip.fps if base_clip.fps else 30
    v_dur = base_clip.duration
    print(f"   -> 原视频时长: {v_dur:.2f}秒 | 原生帧率: {native_fps} FPS")

    # 处理时长：如果语音长，通过物理循环堆叠视频
    if audio_dur > v_dur:
        num_loops = int(np.ceil(audio_dur / v_dur))
        print(f"   -> 语音较长，背景视频需无缝循环 {num_loops} 次。")
        clips_to_concat = [base_clip] * num_loops
        full_video = concatenate_videoclips(clips_to_concat)
    else:
        print(f"   -> 语音较短，将直接裁剪原视频以对齐音频。")
        full_video = base_clip

    # 截断以完美贴合音频（兼容 v2 API）
    final_background = full_video.subclipped(0, audio_dur)

    # ---------------------------------------------------------
    # 步骤 4: 生成流动字幕与视频合成
    # ---------------------------------------------------------
    print("\n[4/5] 📝 正在生成流动字幕图层...")
    subtitle_clips = generate_dynamic_subtitles(full_display_text, audio_dur, base_clip.size)
    print(f"   -> 成功生成 {len(subtitle_clips)} 段流动字幕。")

    # 将背景和所有字幕片段打包合并
    final_video = CompositeVideoClip([final_background] + subtitle_clips)
    # 注入音频
    final_video = final_video.with_audio(audio)

    # ---------------------------------------------------------
    # 步骤 5: 高画质渲染导出
    # ---------------------------------------------------------
    print(f"\n[5/5] 💻 开始高画质渲染 (采用 {native_fps} FPS, 8000k 码率)...")
    try:
        final_video.write_videofile(
            OUTPUT_VIDEO,
            fps=native_fps,              # 核心修复：使用原生帧率，拒绝慢动作
            codec="libx264",
            audio_codec="aac",
            preset="fast",               # 核心修复：放弃 ultrafast，使用 fast 保证画质
            bitrate="8000k",             # 核心修复：强行锁死高码率，拒绝像素马赛克
            threads=4,
            logger="bar"                 # 开启终端进度条
        )
        print(f"\n✨ 渲染大功告成！完美解决字幕、语速、画质问题！")
        print(f"📁 文件保存在: {os.path.join(TARGET_DIR, OUTPUT_VIDEO)}")
    except Exception as e:
        print(f"\n❌ 渲染报错: {e}")
    finally:
        # 内存释放，养成好习惯
        final_video.close()
        audio.close()
        base_clip.close()
        if os.path.exists(TEMP_VOICE): 
            os.remove(TEMP_VOICE)
            print("   -> 已清理临时音频文件。")

if __name__ == "__main__":
    asyncio.run(main())