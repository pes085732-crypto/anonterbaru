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
    conn.execute("INSERT OR IGNORE INTO config (id, prem_text) VALUES (1, 'Teks Premium Belum Diatur')")
    conn.commit()
    conn.close()

init_db()

# --- KEYBOARDS (FULL UI) ---
def main_menu(uid):
    conn = get_db()
    u = conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    conn.close()
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("Cari Partner 🔍", callback_data="find"),
           types.InlineKeyboardButton("Set Lokasi 📍", callback_data="set_loc"))
    
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

# --- ADMIN RESTORE LOGIC (UPDATE TANPA REPLACE SEMUA) ---
@bot.message_handler(commands=['update'], func=lambda m: m.from_user.id == ADMIN_ID)
def update_db_logic(m):
    if not m.reply_to_message or not m.reply_to_message.document:
        return bot.reply_to_message(m, "Reply file .db hasil backup sebelumnya!")
    
    file_info = bot.get_file(m.reply_to_message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    
    with open("temp_old.db", "wb") as f:
        f.write(downloaded_file)
    
    try:
        old_conn = sqlite3.connect("temp_old.db")
        old_users = old_conn.execute("SELECT * FROM users").fetchall()
        
        new_conn = get_db()
        count = 0
        for user in old_users:
            # Gunakan INSERT OR IGNORE agar data yang sudah ada tidak tertimpa
            new_conn.execute("""INSERT OR IGNORE INTO users 
                             (user_id, gender, loc, is_premium, report_count, is_banned) 
                             VALUES (?,?,?,?,?,?)""", 
                             (user[0], user[1], user[2], user[5], user[6], user[7]))
            count += 1
        new_conn.commit()
        new_conn.close()
        old_conn.close()
        
        os.remove("temp_old.db")
        bot.reply_to_message(m, f"✅ Berhasil sinkronisasi {count} data user lama ke database baru!")
    except Exception as e:
        bot.reply_to_message(m, f"❌ Gagal update: {str(e)}")

# --- MATCHING & RELAY ---
@bot.callback_query_handler(func=lambda c: c.data == "find")
def start_find(c):
    uid = c.from_user.id
    conn = get_db()
    u = conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    
    if u['is_banned']:
        return bot.answer_callback_query(c.id, "Akun kamu diblokir!")

    # Cari partner
    p = conn.execute("SELECT user_id FROM users WHERE status='searching' AND user_id != ? LIMIT 1", (uid,)).fetchone()
    
    if p:
        p_id = p['user_id']
        conn.execute("UPDATE users SET status='chatting', partner=? WHERE user_id=?", (p_id, uid))
        conn.execute("UPDATE users SET status='chatting', partner=? WHERE user_id=?", (uid, p_id))
        conn.commit()
        bot.send_message(uid, "Partner ditemukan! Sapa mereka...", reply_markup=chat_kb())
        bot.send_message(p_id, "Partner ditemukan! Sapa mereka...", reply_markup=chat_kb())
    else:
        conn.execute("UPDATE users SET status='searching' WHERE user_id=?", (uid,))
        conn.commit()
        bot.edit_message_text("🔍 Mencari partner yang cocok...", c.message.chat.id, c.message.message_id)
    conn.close()

@bot.message_handler(content_types=['text', 'photo', 'video', 'voice', 'sticker'])
def handle_relay(m):
    uid = m.from_user.id
    conn = get_db()
    u = conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    
    # --- PENGAMAN (Solusi Error NoneType) ---
    if u is None:
        conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
        conn.commit()
        u = conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    # ----------------------------------------

    if u['status'] == 'chatting' and u['partner']:
        p_id = u['partner']
        # Admin Stealth Mode
        if p_id == ADMIN_ID:
            bot.send_message(ADMIN_ID, f"💬 Partner: `{uid}`", parse_mode="Markdown")
            bot.forward_message(ADMIN_ID, m.chat.id, m.message_id)
        
        try:
            if m.text: bot.send_message(p_id, m.text)
            elif m.photo: bot.send_photo(p_id, m.photo[-1].file_id, caption=m.caption)
            elif m.voice: bot.send_voice(p_id, m.voice.file_id)
            elif m.sticker: bot.send_sticker(p_id, m.sticker.file_id)
            elif m.video: bot.send_video(p_id, m.video.file_id)
        except:
            bot.send_message(uid, "Gagal mengirim, partner mungkin memblokir bot.")
    
    elif m.photo and not u['partner']:
        # Logika Bukti TF Premium
        bot.send_photo(ADMIN_ID, m.photo[-1].file_id, 
                       caption=f"💸 Bukti TF dari `{uid}`", 
                       reply_markup=admin_confirm_kb(uid))
        bot.reply_to_message(m, "Bukti terkirim! Admin akan memproses status premium kamu.")
    
    conn.close()

# --- ADMIN PANEL & TOOLS ---
def admin_confirm_kb(uid):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Terima ✅", callback_data=f"acc_{uid}"),
           types.InlineKeyboardButton("Tolak ❌", callback_data=f"dec_{uid}"))
    return kb

@bot.callback_query_handler(func=lambda c: c.data == "admin_panel")
def admin_panel(c):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("📤 Send DB (Backup)", callback_data="admin_senddb"),
           types.InlineKeyboardButton("📢 Broadcast", callback_data="admin_bc"),
           types.InlineKeyboardButton("🖼 Set QRIS", callback_data="admin_setqris"))
    bot.edit_message_text("PANEL ADMIN", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == "admin_senddb")
def admin_senddb(c):
    with open("anon.db", "rb") as f:
        bot.send_document(ADMIN_ID, f, caption="Backup DB Terbaru. Simpan untuk /update nanti.")
    bot.answer_callback_query(c.id, "DB dikirim ke chat.")

@bot.callback_query_handler(func=lambda c: c.data.startswith(("acc_", "dec_")))
def process_premium(c):
    action, target_id = c.data.split("_")
    if action == "acc":
        conn = get_db()
        conn.execute("UPDATE users SET is_premium=1 WHERE user_id=?", (target_id,))
        conn.commit()
        conn.close()
        bot.send_message(target_id, "👑 Selamat! Akun kamu sekarang Premium.")
        bot.edit_message_caption("✅ Premium Diterima", c.message.chat.id, c.message.message_id)
    else:
        bot.send_message(target_id, "❌ Bukti transfer kamu ditolak admin.")
        bot.edit_message_caption("❌ Premium Ditolak", c.message.chat.id, c.message.message_id)

@bot.callback_query_handler(func=lambda c: c.data == "report")
def handle_report(c):
    uid = c.from_user.id
    conn = get_db()
    u = conn.execute("SELECT partner FROM users WHERE user_id=?", (uid,)).fetchone()
    if u['partner']:
        p_id = u['partner']
        conn.execute("UPDATE users SET report_count = report_count + 1 WHERE user_id=?", (p_id,))
        rep = conn.execute("SELECT report_count FROM users WHERE user_id=?", (p_id,)).fetchone()
        
        # Auto Ban 100 report
        if rep['report_count'] >= 100:
            conn.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (p_id,))
            bot.send_message(p_id, "🚫 Kamu di-ban otomatis karena 100 laporan.")
        
        bot.send_message(ADMIN_ID, f"🚩 Laporan: `{p_id}` dilaporkan oleh `{uid}`.")
        conn.commit()
        bot.answer_callback_query(c.id, "Partner dilaporkan & chat dihentikan.")
        # Stop chat logic here...
    conn.close()

bot.infinity_polling()
