import telebot
from telebot import types
import os
import sqlite3

# --- KONFIGURASI ---
TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
bot = telebot.TeleBot(TOKEN)

# --- DATABASE ENGINE ---
def get_db():
    conn = sqlite3.connect('anon.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, gender TEXT, loc TEXT, 
                  status TEXT DEFAULT 'idle', partner INTEGER, 
                  is_premium INTEGER DEFAULT 0, report_count INTEGER DEFAULT 0,
                  is_banned INTEGER DEFAULT 0)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS config 
                 (id INTEGER PRIMARY KEY, qris_file_id TEXT, prem_text TEXT)''')
    conn.execute("INSERT OR IGNORE INTO config (id, prem_text) VALUES (1, 'Kirim bukti transfer ke admin untuk aktivasi Premium.')")
    conn.commit()
    conn.close()

init_db()

# --- HELPER: GET USER DATA ---
def get_user_data(uid):
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
    u = get_user_data(uid)
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("Cari Partner 🔍", callback_data="find"),
           types.InlineKeyboardButton(f"Lokasi: {u['loc'] or 'Belum Set'} 📍", callback_data="set_loc"))
    
    status_prem = "👑 Member Premium" if u['is_premium'] else "Beli Premium 💎"
    kb.add(types.InlineKeyboardButton(status_prem, callback_data="buy_prem"))
    
    if uid == ADMIN_ID:
        kb.add(types.InlineKeyboardButton("🛠 ADMIN PANEL", callback_data="admin_panel"))
    return kb

def chat_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Next Partner ⏭️", callback_data="next"),
           types.InlineKeyboardButton("Laporkan 🚩", callback_data="report"))
    return kb

# --- COMMANDS ---
@bot.message_handler(commands=['start'])
def start(m):
    uid = m.from_user.id
    bot.send_message(uid, "👋 Halo! Selamat datang di Anon Chat Bot.\nSilakan atur lokasi atau langsung cari partner!", reply_markup=main_menu_kb(uid))

@bot.message_handler(commands=['update'], func=lambda m: m.from_user.id == ADMIN_ID)
def update_db(m):
    if not m.reply_to_message or not m.reply_to_message.document:
        return bot.reply_to_message(m, "Reply file .db hasil backup untuk sinkronisasi!")
    
    file_info = bot.get_file(m.reply_to_message.document.file_id)
    downloaded = bot.download_file(file_info.file_path)
    with open("temp_old.db", "wb") as f: f.write(downloaded)
    
    try:
        old_conn = sqlite3.connect("temp_old.db")
        old_users = old_conn.execute("SELECT * FROM users").fetchall()
        new_conn = get_db()
        for u in old_users:
            new_conn.execute("INSERT OR IGNORE INTO users (user_id, gender, loc, is_premium, report_count, is_banned) VALUES (?,?,?,?,?,?)", 
                             (u[0], u[1], u[2], u[5], u[6], u[7]))
        new_conn.commit()
        new_conn.close()
        old_conn.close()
        os.remove("temp_old.db")
        bot.reply_to_message(m, "✅ Database berhasil disinkronisasi!")
    except Exception as e:
        bot.reply_to_message(m, f"❌ Error: {e}")

# --- CALLBACK HANDLERS ---
@bot.callback_query_handler(func=lambda c: True)
def handle_callbacks(c):
    uid = c.from_user.id
    u = get_user_data(uid)

    if c.data == "find":
        if u['is_banned']: return bot.answer_callback_query(c.id, "Akun kamu dibanned!")
        conn = get_db()
        # Logic Cari Partner
        p = conn.execute("SELECT user_id FROM users WHERE status='searching' AND user_id != ? LIMIT 1", (uid,)).fetchone()
        if p:
            p_id = p['user_id']
            conn.execute("UPDATE users SET status='chatting', partner=? WHERE user_id=?", (p_id, uid))
            conn.execute("UPDATE users SET status='chatting', partner=? WHERE user_id=?", (uid, p_id))
            conn.commit()
            bot.send_message(uid, "Partner ditemukan! Silakan chat.", reply_markup=chat_kb())
            bot.send_message(p_id, "Partner ditemukan! Silakan chat.", reply_markup=chat_kb())
        else:
            conn.execute("UPDATE users SET status='searching' WHERE user_id=?", (uid,))
            conn.commit()
            bot.edit_message_text("🔍 Sedang mencari partner...", c.message.chat.id, c.message.message_id)
        conn.close()

    elif c.data == "next" or c.data == "report":
        conn = get_db()
        p_id = u['partner']
        if p_id:
            if c.data == "report":
                conn.execute("UPDATE users SET report_count = report_count + 1 WHERE user_id=?", (p_id,))
                bot.send_message(ADMIN_ID, f"🚩 User {p_id} dilaporkan oleh {uid}")
            
            conn.execute("UPDATE users SET status='idle', partner=NULL WHERE user_id IN (?,?)", (uid, p_id))
            conn.commit()
            bot.send_message(p_id, "Partner telah menghentikan chat.", reply_markup=main_menu_kb(p_id))
            bot.send_message(uid, "Chat dihentikan.", reply_markup=main_menu_kb(uid))
        conn.close()

    elif c.data == "set_loc":
        msg = bot.send_message(uid, "Ketik nama lokasi kamu (Contoh: Jakarta):")
        bot.register_next_step_handler(msg, save_loc)

    elif c.data == "admin_senddb":
        with open("anon.db", "rb") as f:
            bot.send_document(ADMIN_ID, f, caption="Backup Database")

    elif c.data == "admin_panel":
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📤 Backup DB", callback_data="admin_senddb"))
        bot.edit_message_text("Panel Admin Aktif", c.message.chat.id, c.message.message_id, reply_markup=kb)

def save_loc(m):
    conn = get_db()
    conn.execute("UPDATE users SET loc=? WHERE user_id=?", (m.text, m.from_user.id))
    conn.commit()
    conn.close()
    bot.send_message(m.chat.id, f"✅ Lokasi diatur ke: {m.text}", reply_markup=main_menu_kb(m.from_user.id))

# --- RELAY PESAN & STEALH ADMIN ---
@bot.message_handler(content_types=['text', 'photo', 'video', 'voice', 'sticker'])
def relay_pesan(m):
    uid = m.from_user.id
    u = get_user_data(uid)
    
    if u['status'] == 'chatting' and u['partner']:
        p_id = u['partner']
        # Admin Stealth: Admin nerima pesan terusan (forward)
        if p_id == ADMIN_ID:
            bot.send_message(ADMIN_ID, f"📩 Dari: {uid}")
            bot.forward_message(ADMIN_ID, m.chat.id, m.message_id)
        
        try:
            if m.text: bot.send_message(p_id, m.text)
            elif m.photo: bot.send_photo(p_id, m.photo[-1].file_id, caption=m.caption)
            elif m.voice: bot.send_voice(p_id, m.voice.file_id)
            elif m.sticker: bot.send_sticker(p_id, m.sticker.file_id)
            elif m.video: bot.send_video(p_id, m.video.file_id)
        except:
            bot.send_message(uid, "❌ Gagal kirim pesan.")
    
    elif m.photo and not u['partner']:
        # Kirim bukti TF ke Admin
        bot.send_photo(ADMIN_ID, m.photo[-1].file_id, caption=f"💸 Bukti TF dari {uid}\nKetik `/setpremium {uid}` untuk aktivasi.")
        bot.reply_to_message(m, "Bukti TF telah dikirim ke admin!")

@bot.message_handler(commands=['setpremium'], func=lambda m: m.from_user.id == ADMIN_ID)
def set_premium_cmd(m):
    try:
        target = m.text.split()[1]
        conn = get_db()
        conn.execute("UPDATE users SET is_premium=1 WHERE user_id=?", (target,))
        conn.commit()
        conn.close()
        bot.send_message(target, "👑 Akun kamu sekarang sudah Premium!")
        bot.reply_to_message(m, "✅ Berhasil set premium.")
    except:
        bot.reply_to_message(m, "Gunakan: `/setpremium ID_USER`")

bot.infinity_polling()
