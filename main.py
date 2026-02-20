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
    # Tabel Users: Menyimpan data gender, lokasi, status chat, premium, dan rating
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
    # Tabel Config: Menyimpan pengaturan QRIS dan Teks Premium dari Admin
    conn.execute('''CREATE TABLE IF NOT EXISTS config 
                 (id INTEGER PRIMARY KEY, qris_file_id TEXT, prem_text TEXT)''')
    conn.execute("INSERT OR IGNORE INTO config (id, prem_text) VALUES (1, 'Silakan beli Premium untuk fitur Filter Gender, Badge 👑, dan Reconnect!')")
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

# --- KEYBOARDS (UI) ---
def main_menu_kb(uid):
    u = get_user(uid)
    kb = types.InlineKeyboardMarkup(row_width=2)
    
    # Baris 1: Cari Partner
    kb.add(types.InlineKeyboardButton("Cari Partner 🔍", callback_data="find_menu"))
    
    # Baris 2: Pengaturan User
    kb.add(types.InlineKeyboardButton(f"Lokasi: {u['loc'] or 'Set'} 📍", callback_data="set_loc"),
           types.InlineKeyboardButton(f"Gender: {u['gender'] or 'Set'} 👤", callback_data="set_gender"))
    
    # Baris 3: Fitur Premium (Hanya muncul jika user premium punya history)
    if u['is_premium'] and u['last_partner']:
        kb.add(types.InlineKeyboardButton("🔄 Reconnect Partner Terakhir", callback_data="reconnect"))
    
    # Baris 4: Status Premium
    label_prem = "👑 Member Premium" if u['is_premium'] else "💎 Beli Premium"
    kb.add(types.InlineKeyboardButton(label_prem, callback_data="buy_prem"))
    
    # Baris 5: Admin Panel
    if uid == ADMIN_ID:
        kb.add(types.InlineKeyboardButton("🛠 ADMIN PANEL", callback_data="admin_panel"))
    return kb

def chat_nav_keyboard():
    # Keyboard nempel di bawah agar tidak perlu scroll
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("Next Partner ⏭️"), types.KeyboardButton("Stop & Report 🚩"))
    return kb

def rating_kb(partner_id):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Suka 👍", callback_data=f"rate_up_{partner_id}"),
           types.InlineKeyboardButton("Benci 👎", callback_data=f"rate_down_{partner_id}"))
    return kb

# --- ADMIN PANEL LOGIC ---
@bot.message_handler(commands=['admin'])
def admin_cmd(m):
    if m.from_user.id == ADMIN_ID:
        bot.send_message(m.chat.id, "🛡️ **WELCOME TO ADMIN PANEL**", parse_mode="Markdown", reply_markup=admin_kb())

def admin_kb():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("📤 Backup Database", callback_data="adm_backup"),
           types.InlineKeyboardButton("🖼 Set Foto QRIS", callback_data="adm_setqris"),
           types.InlineKeyboardButton("📝 Set Teks Premium", callback_data="adm_settext"),
           types.InlineKeyboardButton("📢 Broadcast Semua User", callback_data="adm_bc"))
    return kb

# --- MATCHING ENGINE ---
@bot.callback_query_handler(func=lambda c: c.data == "find_menu")
def find_menu(c):
    u = get_user(c.from_user.id)
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("Cari Acak (Gratis)", callback_data="match_any"))
    if u['is_premium']:
        kb.add(types.InlineKeyboardButton("Cari Cowok ♂️", callback_data="match_Pria"),
               types.InlineKeyboardButton("Cari Cewek ♀️", callback_data="match_Wanita"))
    else:
        kb.add(types.InlineKeyboardButton("🔒 Filter Gender (Hanya Premium)", callback_data="buy_prem"))
    bot.edit_message_text("Pilih kriteria pencarian:", c.message.chat.id, c.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("match_"))
def search_partner(c):
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
        
        u_info = get_user(uid)
        p_info = get_user(p_id)

        # Badge Premium di awal match
        u_badge = "👑 **Premium Sultan**" if u_info['is_premium'] else "**User Biasa**"
        p_badge = "👑 **Premium Sultan**" if p_info['is_premium'] else "**User Biasa**"

        txt_u = f"✅ **Partner Ditemukan!**\n\n👤 Status: {p_badge}\n📍 Lokasi: {p_info['loc'] or '-'}\n👍 Like: {p_info['likes']} | 👎 Dislike: {p_info['dislikes']}\n\nSilakan menyapa!"
        txt_p = f"✅ **Partner Ditemukan!**\n\n👤 Status: {u_badge}\n📍 Lokasi: {u_info['loc'] or '-'}\n👍 Like: {u_info['likes']} | 👎 Dislike: {u_info['dislikes']}\n\nSilakan menyapa!"

        bot.send_message(uid, txt_u, parse_mode="Markdown", reply_markup=chat_nav_keyboard())
        bot.send_message(p_id, txt_p, parse_mode="Markdown", reply_markup=chat_nav_keyboard())
    else:
        conn.execute("UPDATE users SET status='searching' WHERE user_id=?", (uid,))
        conn.commit()
        bot.edit_message_text("🔍 Sedang mencari partner... Mohon tunggu sebentar.", c.message.chat.id, c.message.message_id)
    conn.close()

# --- CHAT RELAY & NAV ---
@bot.message_handler(func=lambda m: True, content_types=['text', 'photo', 'video', 'voice', 'sticker'])
def relay_handler(m):
    uid = m.from_user.id
    u = get_user(uid)

    # 1. Navigasi Stop/Next
    if m.text in ["Next Partner ⏭️", "Stop & Report 🚩"]:
        if u['partner']:
            p_id = u['partner']
            conn = get_db()
            conn.execute("UPDATE users SET status='idle', partner=NULL, last_partner=? WHERE user_id=?", (p_id, uid))
            conn.execute("UPDATE users SET status='idle', partner=NULL, last_partner=? WHERE user_id=?", (uid, p_id))
            conn.commit()
            conn.close()
            bot.send_message(uid, "Chat selesai.", reply_markup=types.ReplyKeyboardRemove())
            bot.send_message(uid, "Beri penilaian untuk partner tadi:", reply_markup=rating_kb(p_id))
            bot.send_message(p_id, "Partner menghentikan chat.", reply_markup=types.ReplyKeyboardRemove())
            bot.send_message(p_id, "Beri penilaian untuk partner tadi:", reply_markup=rating_kb(uid))
        return

    # 2. Relay Chatting
    if u['status'] == 'chatting' and u['partner']:
        p_id = u['partner']
        try:
            if m.text: bot.send_message(p_id, m.text)
            elif m.photo: bot.send_photo(p_id, m.photo[-1].file_id, caption=m.caption)
            elif m.video: bot.send_video(p_id, m.video.file_id, caption=m.caption)
            elif m.voice: bot.send_voice(p_id, m.voice.file_id)
            elif m.sticker: bot.send_sticker(p_id, m.sticker.file_id)
            
            if p_id == ADMIN_ID: bot.forward_message(ADMIN_ID, m.chat.id, m.message_id)
        except:
            bot.send_message(uid, "⚠️ Pesan gagal terkirim.")
            
    # 3. Kirim Bukti Transfer (Jika tidak sedang chat)
    elif m.photo and not u['partner']:
        bot.send_message(uid, "✅ Bukti transfer telah diterima oleh sistem! Admin akan memprosesnya.")
        kb = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("Approve ✅", callback_data=f"adm_acc_{uid}"),
            types.InlineKeyboardButton("Reject ❌", callback_data=f"adm_dec_{uid}")
        )
        bot.send_photo(ADMIN_ID, m.photo[-1].file_id, caption=f"💸 Konfirmasi Premium: `{uid}`", reply_markup=kb)

# --- CALLBACK HANDLER (SEMUA CALLBACK) ---
@bot.callback_query_handler(func=lambda c: True)
def process_all_callbacks(c):
    uid = c.from_user.id
    
    if c.data.startswith("rate_"):
        _, type, tid = c.data.split("_")
        conn = get_db()
        col = "likes" if type == "up" else "dislikes"
        conn.execute(f"UPDATE users SET {col} = {col} + 1 WHERE user_id=?", (tid,))
        conn.commit()
        conn.close()
        bot.edit_message_text("Penilaian berhasil dikirim!", c.message.chat.id, c.message.message_id)

    elif c.data == "buy_prem":
        conf = get_config()
        if conf['qris_file_id']:
            bot.send_photo(c.message.chat.id, conf['qris_file_id'], caption=conf['prem_text'])
        else:
            bot.send_message(c.message.chat.id, conf['prem_text'])

    elif c.data == "admin_panel":
        bot.edit_message_text("🛡️ PANEL ADMIN", c.message.chat.id, c.message.message_id, reply_markup=admin_kb())

    elif c.data == "adm_backup" and uid == ADMIN_ID:
        with open("anon.db", "rb") as f: bot.send_document(ADMIN_ID, f, caption="Backup DB")

    elif c.data.startswith("adm_acc_"):
        target = c.data.split("_")[2]
        conn = get_db()
        conn.execute("UPDATE users SET is_premium=1 WHERE user_id=?", (target,))
        conn.commit()
        conn.close()
        bot.send_message(target, "👑 PEMBAYARAN DISETUJUI! Kamu sekarang adalah Member Premium.")
        bot.edit_message_caption("✅ Premium Aktif", c.message.chat.id, c.message.message_id)

    elif c.data == "reconnect":
        u = get_user(uid)
        bot.send_message(u['last_partner'], "🔄 Mantan partnermu ingin mengobrol lagi! Coba cari di menu 'Cari Partner'.")
        bot.answer_callback_query(c.id, "Pesan reconnect terkirim!")

# --- UPDATE DATABASE (SINKRONISASI) ---
@bot.message_handler(commands=['update'], func=lambda m: m.from_user.id == ADMIN_ID)
def update_logic(m):
    if not m.reply_to_message or not m.reply_to_message.document:
        return bot.reply_to_message(m, "Reply file database (.db) lama untuk sinkronisasi data.")
    
    file_info = bot.get_file(m.reply_to_message.document.file_id)
    with open("old_data.db", "wb") as f: f.write(bot.download_file(file_info.file_path))
    
    try:
        old_conn = sqlite3.connect("old_data.db")
        rows = old_conn.execute("SELECT * FROM users").fetchall()
        new_conn = get_db()
        count = 0
        for r in rows:
            new_conn.execute("INSERT OR IGNORE INTO users (user_id, gender, loc, is_premium, likes, dislikes) VALUES (?,?,?,?,?,?)", 
                             (r[0], r[1], r[2], r[6], r[7], r[8]))
            count += 1
        new_conn.commit()
        bot.reply_to_message(m, f"✅ Sinkronisasi Berhasil! {count} data user berhasil digabungkan.")
        os.remove("old_data.db")
    except Exception as e:
        bot.reply_to_message(m, f"❌ Error: {e}")

@bot.message_handler(commands=['start'])
def welcome(m):
    bot.send_message(m.chat.id, "✨ **ANON CHAT PREMIUM** ✨\nSilakan gunakan tombol di bawah:", 
                     parse_mode="Markdown", reply_markup=main_menu_kb(m.from_user.id))

bot.infinity_polling()
