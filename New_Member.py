from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
import re
import sqlite3
from datetime import datetime
from difflib import get_close_matches

# 1. 基础配置
BOT_TOKEN = "8870233140:AAGqcayS17mIUxrAI6y6ZPTi6hKXIXLAAME"
TARGET_TOPIC_ID = 6  # 锁定 New Member 话题

# 2. 初始化数据库 (持久化保存，重启不丢失)
def init_db():
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            staff TEXT,
            source TEXT,
            created_at DATE
        )
    ''')
    conn.commit()
    conn.close()

def clean_input(text):
    if not text:
        return ""
    # 去除表情符号和特殊符号，只保留英文、数字、中文及空格
    cleaned = re.sub(r'[^\w\s]', '', text).strip()
    # 统一转换为首字母大写格式 (例如 pha lin -> Pha Lin)
    return cleaned.title()

def get_existing_names(category="staff"):
    """获取数据库中已存在的所有员工或渠道列表"""
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    cursor.execute(f"SELECT DISTINCT {category} FROM records WHERE {category} IS NOT NULL AND {category} != ''")
    names = [row[0] for row in cursor.fetchall()]
    conn.close()
    return names

def match_closest_name(input_name, category="staff"):
    """如果打错字或格式微调，自动与历史记录中最相似的名称匹配 (80% 相似度阈值)"""
    if not input_name:
        return ""
    
    cleaned = clean_input(input_name)
    existing_list = get_existing_names(category)
    
    # 查找模糊匹配
    matches = get_close_matches(cleaned, existing_list, n=1, cutoff=0.8)
    if matches:
        return matches[0]  # 如果找到匹配的旧名字，直接用旧名字
    return cleaned  # 找不到就作为新名字存入

def add_record(staff_name, source_channel):
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    cursor.execute(
        "INSERT INTO records (staff, source, created_at) VALUES (?, ?, ?)",
        (staff_name, source_channel, today)
    )
    conn.commit()
    conn.close()

def generate_report():
    conn = sqlite3.connect('bot_data.db')
    cursor = conn.cursor()
    
    today = datetime.now().strftime("%Y-%m-%d")
    this_month = datetime.now().strftime("%Y-%m")

    # 查员工今日数据
    cursor.execute("SELECT staff, COUNT(*) FROM records WHERE created_at = ? AND staff IS NOT NULL AND staff != '' GROUP BY staff", (today,))
    staff_today = dict(cursor.fetchall())

    # 查员工本月数据
    cursor.execute("SELECT staff, COUNT(*) FROM records WHERE strftime('%Y-%m', created_at) = ? AND staff IS NOT NULL AND staff != '' GROUP BY staff", (this_month,))
    staff_month = dict(cursor.fetchall())

    # 查来源今日数据
    cursor.execute("SELECT source, COUNT(*) FROM records WHERE created_at = ? AND source IS NOT NULL AND source != '' GROUP BY source", (today,))
    source_today = dict(cursor.fetchall())

    # 查来源本月数据
    cursor.execute("SELECT source, COUNT(*) FROM records WHERE strftime('%Y-%m', created_at) = ? AND source IS NOT NULL AND source != '' GROUP BY source", (this_month,))
    source_month = dict(cursor.fetchall())

    conn.close()

    msg = f"📊 **【New Member Report】**\n📅 Date: `{today}`\n\n"
    
    # 员工统计
    msg += "👤 **Staff Performance**:\n"
    all_staffs = sorted(list(set(list(staff_today.keys()) + list(staff_month.keys()))))
    if not all_staffs:
        msg += "  (No Data)\n"
    else:
        for s in all_staffs:
            d_cnt = staff_today.get(s, 0)
            m_cnt = staff_month.get(s, 0)
            msg += f"• `{s}`: Today {d_cnt} | Month {m_cnt}\n"
            
    # 来源统计
    msg += "\n🌐 **Source Channels**:\n"
    all_sources = sorted(list(set(list(source_today.keys()) + list(source_month.keys()))))
    if not all_sources:
        msg += "  (No Data)\n"
    else:
        for f in all_sources:
            d_cnt = source_today.get(f, 0)
            m_cnt = source_month.get(f, 0)
            msg += f"• `{f}`: Today {d_cnt} | Month {m_cnt}\n"
            
    return msg

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    thread_id = update.message.message_thread_id
    text = update.message.text

    if thread_id != TARGET_TOPIC_ID:
        return

    lines = text.split('\n')
    staff_name = None
    source_channel = None

    for line in lines:
        if line.upper().startswith("STAFF="):
            raw_val = line.split("=", 1)[1]
            staff_name = match_closest_name(raw_val, category="staff")
        elif line.upper().startswith("FROM="):
            raw_val = line.split("=", 1)[1]
            source_channel = match_closest_name(raw_val, category="source")

    if staff_name or source_channel:
        add_record(staff_name, source_channel)
        report_msg = generate_report()

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            message_thread_id=TARGET_TOPIC_ID,
            text=report_msg,
            parse_mode="Markdown"
        )

if __name__ == "__main__":
    init_db()
    print("Bot 已启动，正在监听指定 Topic...")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.run_polling()