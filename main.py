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
    # Default config
    conn.execute("INSERT OR IGNORE INTO config (id, prem_text) VALUES (1, 'Silakan transfer untuk jadi Premium.')")
    conn.commit()
    conn.close()

init_db()

# --- HELPER FUNCTIONS ---
def get_user_data(uid):
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
    res = conn.execute("SELECT * FROM config WHERE id=1").fetchone()
    conn.close()
    return res

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

# --- ADMIN PANEL HANDLERS ---
@bot.callback_query_handler(func=lambda c: c.data.startswith('admin_'))
def admin_callbacks(c):
    if c.from_user.id != ADMIN_ID: return
    
    if c.data == "admin_panel":
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton("📤 Backup DB (Send File)", callback_data="admin_senddb"),
               types.InlineKeyboardButton("🖼 Set QRIS", callback_data="admin_setqris"),
               types.InlineKeyboardButton("📝 Set Teks Premium", callback_data="admin_settext"),
               types.InlineKeyboardButton("📢 Broadcast", callback_data="admin_bc"))
        bot.edit_message_text("⚙️ PANEL KONTROL ADMIN", c.message.chat.id, c.message.message_id, reply_markup=kb)

    elif c.data == "admin_senddb":
        with open("anon.db", "rb") as f:
            bot.send_document(ADMIN_ID, f, caption="Backup Database untuk /update")
            
    elif c.data == "admin_setqris":
        msg = bot.send_message(ADMIN_ID, "Kirimkan foto QRIS terbaru kamu:")
        bot.register_next_step_handler(msg, save_qris)

    elif c.data == "admin_settext":
        msg = bot.send_message(ADMIN_ID, "Ketikkan teks deskripsi premium baru:")
        bot.register_next_step_handler(msg, save_prem_text)

    elif c.data == "admin_bc":
        msg = bot.send_message(ADMIN_ID, "Ketik pesan broadcast (Teks saja):")
        bot.register_next_step_handler(msg, start_broadcast)

# --- SAVE SETTINGS LOGIC ---
def save_qris(m):
    if not m.photo: return bot.send_message(ADMIN_ID, "Gagal. Harus berupa foto!")
    fid = m.photo[-1].file_id
    conn = get_db()
    conn.execute("UPDATE config SET qris_file_id=? WHERE id=1", (fid,))
    conn.commit()
    conn.close()
    bot.send_message(ADMIN_ID, "✅ Foto QRIS berhasil diupdate!")

def save_prem_text(m):
    conn = get_db()
    conn.execute("UPDATE config SET prem_text=? WHERE id=1", (m.text,))
    conn.commit()
    conn.close()
    bot.send_message(ADMIN_ID, "✅ Teks Premium berhasil diupdate!")

def start_broadcast(m):
    conn = get_db()
    users = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    count = 0
    for u in users:
        try:
            bot.send_message(u['user_id'], f"📢 **PENGUMUMAN**\n\n{m.text}", parse_mode="Markdown")
            count += 1
        except: pass
    bot.send_message(ADMIN_ID, f"✅ Broadcast selesai ke {count} user.")

# --- USER FLOW ---
@bot.callback_query_handler(func=lambda c: c.data == "buy_prem")
def buy_prem_ui(c):
    conf = get_config()
    if conf['qris_file_id']:
        bot.send_photo(c.message.chat.id, conf['qris_file_id'], caption=conf['prem_text'])
    else:
        bot.send_message(c.message.chat.id, conf['prem_text'])
    bot.send_message(c.message.chat.id, "Setelah bayar, **KIRIM FOTO BUKTI TRANSFER** ke sini.")

@bot.callback_query_handler(func=lambda c: c.data.startswith('acc_') or c.data.startswith('dec_'))
def handle_payment_approval(c):
    action, target_id = c.data.split('_')
    if action == "acc":
        conn = get_db()
        conn.execute("UPDATE users SET is_premium=1 WHERE user_id=?", (target_id,))
        conn.commit()
        conn.close()
        bot.send_message(target_id, "👑 PEMBAYARAN DITERIMA! Kamu sekarang adalah Member Premium.")
        bot.edit_message_caption("✅ Bukti TF Diterima", c.message.chat.id, c.message.message_id)
    else:
        bot.send_message(target_id, "❌ Maaf, bukti transfer kamu ditolak oleh Admin.")
        bot.edit_message_caption("❌ Bukti TF Ditolak", c.message.chat.id, c.message.message_id)

# --- CORE LOGIC (START, FIND, NEXT, RELAY) ---
@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, "Selamat datang di Anon Chat!", reply_markup=main_menu_kb(m.from_user.id))

@bot.callback_query_handler(func=lambda c: c.data in ["find", "next", "report"])
def matching_logic(c):
    uid = c.from_user.id
    u = get_user_data(uid)
    conn = get_db()
    
    if c.data == "find":
        p = conn.execute("SELECT user_id FROM users WHERE status='searching' AND user_id != ? LIMIT 1", (uid,)).fetchone()
        if p:
            p_id = p['user_id']
            conn.execute("UPDATE users SET status='chatting', partner=? WHERE user_id=?", (p_id, uid))
            conn.execute("UPDATE users SET status='chatting', partner=? WHERE user_id=?", (uid, p_id))
            conn.commit()
            bot.send_message(uid, "Partner ditemukan!", reply_markup=chat_kb())
            bot.send_message(p_id, "Partner ditemukan!", reply_markup=chat_kb())
        else:
            conn.execute("UPDATE users SET status='searching' WHERE user_id=?", (uid,))
            conn.commit()
            bot.edit_message_text("🔍 Mencari...", c.message.chat.id, c.message.message_id)
    
    elif c.data in ["next", "report"]:
        p_id = u['partner']
        if p_id:
            if c.data == "report":
                conn.execute("UPDATE users SET report_count = report_count + 1 WHERE user_id=?", (p_id,))
                bot.send_message(ADMIN_ID, f"🚩 Report on {p_id}")
            conn.execute("UPDATE users SET status='idle', partner=NULL WHERE user_id IN (?,?)", (uid, p_id))
            conn.commit()
            bot.send_message(p_id, "Chat selesai.", reply_markup=main_menu_kb(p_id))
            bot.send_message(uid, "Chat selesai.", reply_markup=main_menu_kb(uid))
    conn.close()

@bot.message_handler(content_types=['text', 'photo', 'video', 'voice', 'sticker'])
def main_relay(m):
    u = get_user_data(m.from_user.id)
    if u['status'] == 'chatting' and u['partner']:
        p_id = u['partner']
        if p_id == ADMIN_ID: bot.forward_message(ADMIN_ID, m.chat.id, m.message_id)
        
        try:
            if m.text: bot.send_message(p_id, m.text)
            elif m.photo: bot.send_photo(p_id, m.photo[-1].file_id, caption=m.caption)
            elif m.voice: bot.send_voice(p_id, m.voice.file_id)
            elif m.sticker: bot.send_sticker(p_id, m.sticker.file_id)
            elif m.video: bot.send_video(p_id, m.video.file_id)
        except: bot.send_message(m.from_user.id, "Gagal kirim.")
    
    elif m.photo and not u['partner']:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("Terima ✅", callback_data=f"acc_{m.from_user.id}"),
               types.InlineKeyboardButton("Tolak ❌", callback_data=f"dec_{m.from_user.id}"))
        bot.send_photo(ADMIN_ID, m.photo[-1].file_id, caption=f"💸 Bukti TF dari {m.from_user.id}", reply_markup=kb)
        bot.reply_to_message(m, "Bukti TF terkirim ke admin!")

# Tambahkan fungsi update db yang tadi di sini...
@bot.message_handler(commands=['update'], func=lambda m: m.from_user.id == ADMIN_ID)
def update_logic(m):
    # (Gunakan logika update yang saya kirim sebelumnya)
    pass

bot.infinity_polling()
