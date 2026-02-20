import telebot
from telebot import types
import os
import sqlite3
import logging

# --- LOGGING SETUP (Agar muncul di Railway Log) ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- KONFIGURASI ---
TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
bot = telebot.TeleBot(TOKEN)

# Path Database (Absolute path agar Railway tidak error)
DB_PATH = os.path.join(os.path.dirname(__file__), 'anon.db')

# --- DATABASE ENGINE ---
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, gender TEXT, loc TEXT, 
                  status TEXT DEFAULT 'idle', partner INTEGER, last_partner INTEGER,
                  is_premium INTEGER DEFAULT 0, likes INTEGER DEFAULT 0, 
                  dislikes INTEGER DEFAULT 0, is_banned INTEGER DEFAULT 0)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS config 
                 (id INTEGER PRIMARY KEY, qris_file_id TEXT, prem_text TEXT)''')
    conn.execute("INSERT OR IGNORE INTO config (id, prem_text) VALUES (1, 'Beli Premium untuk fitur Reconnect & Filter Gender!')")
    conn.commit()
    conn.close()
    logger.info("Database Initialized")

init_db()

# --- HELPER ---
def get_user(uid):
    conn = get_db()
    u = conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    if u is None:
        conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
        conn.commit()
        u = conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    conn.close()
    return u

# --- KEYBOARDS ---
def main_menu_kb(uid):
    u = get_user(uid)
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("Cari Partner 🔍", callback_data="find_menu"))
    kb.add(types.InlineKeyboardButton(f"Lokasi: {u['loc'] or 'Set'} 📍", callback_data="set_loc"),
           types.InlineKeyboardButton(f"Gender: {u['gender'] or 'Set'} 👤", callback_data="set_gender"))
    
    if u['is_premium'] and u['last_partner']:
        kb.add(types.InlineKeyboardButton("🔄 Reconnect Partner", callback_data="reconnect"))
    
    label = "👑 Premium Member" if u['is_premium'] else "💎 Beli Premium"
    kb.add(types.InlineKeyboardButton(label, callback_data="buy_prem"))
    
    if uid == ADMIN_ID:
        kb.add(types.InlineKeyboardButton("🛠 ADMIN PANEL", callback_data="admin_panel"))
    return kb

def chat_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("Next Partner ⏭️"), types.KeyboardButton("Stop & Report 🚩"))
    return kb

# --- HANDLER START ---
@bot.message_handler(commands=['start'])
def start_cmd(m):
    uid = m.from_user.id
    logger.info(f"User {uid} started the bot")
    bot.send_message(m.chat.id, "👋 Selamat datang di **Anon Chat**!\nTemukan teman baru di sini.", 
                     parse_mode="Markdown", reply_markup=main_menu_kb(uid))

# --- MATCHING LOGIC ---
@bot.callback_query_handler(func=lambda c: c.data.startswith("match_") or c.data == "find_menu")
def matching(c):
    uid = c.from_user.id
    u = get_user(uid)
    
    if c.data == "find_menu":
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton("Cari Acak (Gratis)", callback_data="match_any"))
        if u['is_premium']:
            kb.add(types.InlineKeyboardButton("Cari Cowok ♂️", callback_data="match_Pria"),
                   types.InlineKeyboardButton("Cari Cewek ♀️", callback_data="match_Wanita"))
        else:
            kb.add(types.InlineKeyboardButton("🔒 Filter Gender (Premium)", callback_data="buy_prem"))
        return bot.edit_message_text("Pilih kriteria:", c.message.chat.id, c.message.message_id, reply_markup=kb)

    pref = c.data.split("_")[1]
    conn = get_db()
    query = "SELECT * FROM users WHERE status='searching' AND user_id != ?"
    params = [uid]
    if pref != "any":
        query += " AND gender = ?"
        params.append(pref)
    
    p = conn.execute(query + " LIMIT 1", params).fetchone()
    if p:
        p_id = p['user_id']
        conn.execute("UPDATE users SET status='chatting', partner=? WHERE user_id=?", (p_id, uid))
        conn.execute("UPDATE users SET status='chatting', partner=? WHERE user_id=?", (uid, p_id))
        conn.commit()
        
        p_info = get_user(p_id)
        u_info = get_user(uid)
        
        badge_p = "👑 **Premium**" if p_info['is_premium'] else "User Biasa"
        badge_u = "👑 **Premium**" if u_info['is_premium'] else "User Biasa"
        
        bot.send_message(uid, f"✅ Partner ditemukan!\nStatus: {badge_p}\nReputasi: 👍 {p_info['likes']} | 👎 {p_info['dislikes']}", parse_mode="Markdown", reply_markup=chat_keyboard())
        bot.send_message(p_id, f"✅ Partner ditemukan!\nStatus: {badge_u}\nReputasi: 👍 {u_info['likes']} | 👎 {u_info['dislikes']}", parse_mode="Markdown", reply_markup=chat_keyboard())
    else:
        conn.execute("UPDATE users SET status='searching' WHERE user_id=?", (uid,))
        conn.commit()
        bot.edit_message_text("🔍 Sedang mencari...", c.message.chat.id, c.message.message_id)
    conn.close()

# --- RELAY & NAVIGATION ---
@bot.message_handler(func=lambda m: True, content_types=['text', 'photo', 'video', 'voice', 'sticker'])
def relay(m):
    uid = m.from_user.id
    u = get_user(uid)

    if m.text in ["Next Partner ⏭️", "Stop & Report 🚩"]:
        if u['partner']:
            p_id = u['partner']
            conn = get_db()
            conn.execute("UPDATE users SET status='idle', partner=NULL, last_partner=? WHERE user_id=?", (p_id, uid))
            conn.execute("UPDATE users SET status='idle', partner=NULL, last_partner=? WHERE user_id=?", (uid, p_id))
            conn.commit()
            conn.close()
            bot.send_message(uid, "Chat selesai.", reply_markup=types.ReplyKeyboardRemove())
            bot.send_message(uid, "Beri rating:", reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("👍 Suka", callback_data=f"rate_up_{p_id}"),
                types.InlineKeyboardButton("👎 Benci", callback_data=f"rate_down_{p_id}")))
            bot.send_message(p_id, "Partner menghentikan chat.", reply_markup=types.ReplyKeyboardRemove())
            bot.send_message(p_id, "Menu Utama:", reply_markup=main_menu_kb(p_id))
        return

    if u['status'] == 'chatting' and u['partner']:
        try:
            p_id = u['partner']
            if m.text: bot.send_message(p_id, m.text)
            elif m.photo: bot.send_photo(p_id, m.photo[-1].file_id, caption=m.caption)
            elif m.video: bot.send_video(p_id, m.video.file_id, caption=m.caption)
            elif m.voice: bot.send_voice(p_id, m.voice.file_id)
            elif m.sticker: bot.send_sticker(p_id, m.sticker.file_id)
            
            if p_id == ADMIN_ID: bot.forward_message(ADMIN_ID, m.chat.id, m.message_id)
        except: bot.send_message(uid, "⚠️ Gagal kirim.")
    
    elif m.photo and not u['partner']:
        bot.send_message(uid, "✅ Bukti transfer dikirim ke admin!")
        bot.send_photo(ADMIN_ID, m.photo[-1].file_id, caption=f"💸 Bukti TF: `{uid}`", 
                       reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("Terima ✅", callback_data=f"adm_acc_{uid}")))

# --- ADMIN PANEL & RECONNECT ---
@bot.callback_query_handler(func=lambda c: True)
def admin_callbacks(c):
    uid = c.from_user.id
    if c.data == "admin_panel" and uid == ADMIN_ID:
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton("📤 Backup DB", callback_data="adm_db"),
               types.InlineKeyboardButton("📢 Broadcast", callback_data="adm_bc"),
               types.InlineKeyboardButton("🔗 Restore GitHub", callback_data="adm_github"))
        bot.edit_message_text("🛡️ ADMIN PANEL", c.message.chat.id, c.message.message_id, reply_markup=kb)
    
    elif c.data == "adm_db" and uid == ADMIN_ID:
        with open(DB_PATH, "rb") as f: bot.send_document(ADMIN_ID, f)

    elif c.data.startswith("adm_acc_"):
        target = c.data.split("_")[2]
        conn = get_db()
        conn.execute("UPDATE users SET is_premium=1 WHERE user_id=?", (target,))
        conn.commit()
        conn.close()
        bot.send_message(target, "👑 Kamu sekarang adalah User Premium!")
        bot.answer_callback_query(c.id, "User Approved!")

# --- BOT STARTUP ---
logger.info("Bot is Polling...")
bot.infinity_polling(timeout=10, long_polling_timeout=5)
