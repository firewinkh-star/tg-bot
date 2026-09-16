import os
import re
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

# ==================== 1. Render 免费层端口保活（防 Timeout 关停） ====================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is alive and running!")

    def log_message(self, format, *args):
        # 屏蔽 HTTP 请求日志，保持控制台整洁
        return

def run_health_check_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

# 后台异步启动 Web 服务，专门给 Render 扫描端口用
threading.Thread(target=run_health_check_server, daemon=True).start()


# ==================== 2. 数据库配置与初始化 ====================
DB_NAME = "bot_data.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            staff TEXT,
            code TEXT,
            game TEXT,
            deposit REAL,
            source TEXT,
            bonus TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()


# ==================== 3. 报单解析与统计逻辑 ====================
def parse_report(text: str):
    patterns = {
        "staff": r"STAFF\s*=\s*([^\r\n]+)",
        "code": r"CODE\s*=\s*([^\r\n]+)",
        "game": r"GAME\s*=\s*([^\r\n]+)",
        "deposit": r"DEPOSIT\s*=\s*([0-9.]+)",
        "source": r"FROM\s*=\s*([^\r\n]+)",
        "bonus": r"BONUS\s*=\s*([^\r\n]+)"
    }
    
    data = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # strip() 会自动清除名字前后多余的空格、表情或回车
            data[key] = match.group(1).strip()
        else:
            return None  # 格式不符则忽略
            
    try:
        data["deposit"] = float(data["deposit"].replace("$", ""))
    except ValueError:
        data["deposit"] = 0.0

    return data

def save_report(data):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO reports (staff, code, game, deposit, source, bonus)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (data["staff"], data["code"], data["game"], data["deposit"], data["source"], data["bonus"]))
    conn.commit()
    conn.close()

def get_stats(staff_name, source_name):
    today_str = datetime.now().strftime("%Y-%m-%d")
    month_str = datetime.now().strftime("%Y-%m")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Staff 统计
    cursor.execute("SELECT COUNT(*) FROM reports WHERE LOWER(staff) = LOWER(?) AND DATE(created_at) = DATE(?)", (staff_name, today_str))
    staff_today = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM reports WHERE LOWER(staff) = LOWER(?) AND strftime('%Y-%m', created_at) = ?", (staff_name, month_str))
    staff_month = cursor.fetchone()[0]

    # Source 统计
    cursor.execute("SELECT COUNT(*) FROM reports WHERE LOWER(source) = LOWER(?) AND DATE(created_at) = DATE(?)", (source_name, today_str))
    source_today = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM reports WHERE LOWER(source) = LOWER(?) AND strftime('%Y-%m', created_at) = ?", (source_name, month_str))
    source_month = cursor.fetchone()[0]

    conn.close()

    return {
        "staff_today": staff_today,
        "staff_month": staff_month,
        "source_today": source_today,
        "source_month": source_month
    }


# ==================== 4. Telegram 消息处理Handler ====================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text
    data = parse_report(text)

    if data:
        save_report(data)
        stats = get_stats(data["staff"], data["source"])
        today_date = datetime.now().strftime("%Y-%m-%d")

        reply_text = (
            f"📊【New Member Report】\n"
            f"📅 Date: {today_date}\n\n"
            f"👤 Staff Performance:\n"
            f"• {data['staff']}: Today {stats['staff_today']} | Month {stats['staff_month']}\n\n"
            f"🌐 Source Channels:\n"
            f"• {data['source']}: Today {stats['source_today']} | Month {stats['source_month']}"
        )

        await update.message.reply_text(reply_text)


# ==================== 5. Bot 启动入口 ====================
if __name__ == "__main__":
    # 请确认此处填写的是正确的 Telegram Bot Token
    BOT_TOKEN = "8870233140:AAHZWDK1dc687M577ExmDCb17Iq2rVzspDA" 
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    print("Bot 已启动，正在监听指定 Topic...")
    app.run_polling()