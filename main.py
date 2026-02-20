import telebot
from telebot import types
import os
import sqlite3
import json

# --- KONFIGURASI ---
TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID'))
bot = telebot.TeleBot(TOKEN)

# --- DATABASE ENGINE ---
def get_db():
    conn = sqlite3.connect('anon_ultimate.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, gender TEXT, loc TEXT, 
                  status TEXT DEFAULT 'idle', partner INTEGER, last_partner INTEGER,
                  is_premium INTEGER DEFAULT 0, likes INTEGER DEFAULT 0, 
                  dislikes INTEGER DEFAULT 0, report_count INTEGER DEFAULT 0,
                  chat_history TEXT DEFAULT '[]')''')
    conn.execute('''CREATE TABLE IF NOT EXISTS config 
                 (id INTEGER PRIMARY KEY, qris_id TEXT, prem_text TEXT)''')
    conn.execute("INSERT OR IGNORE INTO config (id, prem_text) VALUES (1, 'Silakan transfer untuk akses fitur Sultan!')")
    conn.commit()
    conn.close()

init_db()

# --- COMMAND LIST HELPER ---
def set_bot_commands():
    commands = [
        types.BotCommand("start", "Mulai & Buka Menu Utama"),
        types.BotCommand("admin", "Panel Kontrol (Khusus Admin)"),
        types.BotCommand("stats", "Cek Statistik Bot")
    ]
    bot.set_my_commands(commands)

set_bot_commands()

# --- HELPER FUNCTIONS ---
def get_user(uid):
    conn = get_db()
    u = conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    if u is None:
        conn.execute("INSERT INTO users (user_id) VALUES (?)", (uid,))
        conn.commit()
        u = conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    conn.close()
    return u

def log_chat(uid, name, text):
    conn = get_db()
    u = get_user(uid)
    history = json.loads(u['chat_history'])
    history.append(f"{name}: {text}")
    if len(history) > 20: history.pop(0) # Simpan 20 chat terakhir
    conn.execute("UPDATE users SET chat_history=? WHERE user_id=?", (json.dumps(history), uid))
    conn.commit()
    conn.close()

# --- KEYBOARDS ---
def main_menu(uid):
    u = get_user(uid)
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("Cari Partner 🔍", callback_data="find_menu"))
    kb.add(types.InlineKeyboardButton(f"Lokasi: {u['loc'] or 'Set'} 📍", callback_data="set_loc"),
           types.InlineKeyboardButton(f"Gender: {u['gender'] or 'Set'} 👤", callback_data="set_gender"))
    
    if u['is_premium'] and u['last_partner']:
        kb.add(types.InlineKeyboardButton("🔄 Reconnect Partner", callback_data="reconnect"))
    
    status = "👑 Member Premium" if u['is_premium'] else "💎 Beli Premium"
    kb.add(types.InlineKeyboardButton(status, callback_data="buy_prem"))
    
    if uid == ADMIN_ID:
        kb.add(types.InlineKeyboardButton("🛠 ADMIN PANEL", callback_data="admin_panel"))
    return kb

def chat_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("Next Partner ⏭️", "Stop Match ⏹️")
    return kb

def rating_kb(target_id):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Suka 👍", callback_data=f"rt_up_{target_id}"),
           types.InlineKeyboardButton("Benci 👎", callback_data=f"rt_down_{target_id}"))
    kb.add(types.InlineKeyboardButton("LAPORKAN (REPORT) 🚩", callback_data=f"rt_rep_{target_id}"))
    return kb

# --- ADMIN PROCESS ---
@bot.message_handler(commands=['admin'])
def admin_panel_cmd(m):
    if m.from_user.id != ADMIN_ID: return
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("🖼 Set QRIS", callback_data="adm_qris"),
           types.InlineKeyboardButton("📝 Set Teks Premium", callback_data="adm_txt"),
           types.InlineKeyboardButton("📢 Broadcast", callback_data="adm_bc"),
           types.InlineKeyboardButton("📤 Backup Database", callback_data="adm_db"))
    bot.send_message(m.chat.id, "🛠 **SUPER ADMIN PANEL**", parse_mode="Markdown", reply_markup=kb)

@bot.message_handler(commands=['update'], func=lambda m: m.from_user.id == ADMIN_ID)
def update_db(m):
    if not m.reply_to_message or not m.reply_to_message.document:
        return bot.reply_to_message(m, "Reply file .db dengan caption /update!")
    
    file_info = bot.get_file(m.reply_to_message.document.file_id)
    with open("sync.db", "wb") as f: f.write(bot.download_file(file_info.file_path))
    
    try:
        old_conn = sqlite3.connect("sync.db")
        rows = old_conn.execute("SELECT * FROM users").fetchall()
        new_conn = get_db()
        for r in rows:
            new_conn.execute("INSERT OR IGNORE INTO users (user_id, gender, loc, is_premium, likes, dislikes) VALUES (?,?,?,?,?,?)", 
                             (r[0], r[1], r[2], r[6], r[7], r[8]))
        new_conn.commit()
        bot.reply_to_message(m, "✅ Data berhasil disinkronisasi!")
        os.remove("sync.db")
    except Exception as e: bot.reply_to_message(m, f"❌ Gagal: {e}")

# --- MATCHING LOGIC ---
@bot.callback_query_handler(func=lambda c: c.data.startswith(("match_", "find_menu")))
def handle_matching(c):
    uid = c.from_user.id
    u = get_user(uid)
    if c.data == "find_menu":
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton("Cari Acak (Gratis)", callback_data="match_any"))
        if u['is_premium']:
            kb.add(types.InlineKeyboardButton("Cari Pria ♂️", callback_data="match_Pria"),
                   types.InlineKeyboardButton("Cari Wanita ♀️", callback_data="match_Wanita"))
        else:
            kb.add(types.InlineKeyboardButton("🔒 Filter Gender (Premium Only)", callback_data="buy_prem"))
        return bot.edit_message_text("Kriteria Pencarian:", c.message.chat.id, c.message.message_id, reply_markup=kb)

    pref = c.data.split("_")[1]
    conn = get_db()
    query = "SELECT * FROM users WHERE status='searching' AND user_id != ?"
    params = [uid]
    if pref != "any": query += " AND gender = ?"; params.append(pref)
    
    p = conn.execute(query + " LIMIT 1", params).fetchone()
    if p:
        p_id = p['user_id']
        conn.execute("UPDATE users SET status='chatting', partner=?, chat_history='[]' WHERE user_id=?", (p_id, uid))
        conn.execute("UPDATE users SET status='chatting', partner=?, chat_history='[]' WHERE user_id=?", (uid, p_id))
        conn.commit()
        
        # Info Match
        badge_p = "👑 **Premium Sultan**" if p['is_premium'] else "User Biasa"
        badge_u = "👑 **Premium Sultan**" if u['is_premium'] else "User Biasa"
        
        bot.send_message(uid, f"✅ Terhubung!\nStatus: {badge_p}\nRating: 👍 {p['likes']} | 👎 {p['dislikes']}", parse_mode="Markdown", reply_markup=chat_kb())
        bot.send_message(p_id, f"✅ Terhubung!\nStatus: {badge_u}\nRating: 👍 {u['likes']} | 👎 {u['dislikes']}", parse_mode="Markdown", reply_markup=chat_kb())
    else:
        conn.execute("UPDATE users SET status='searching' WHERE user_id=?", (uid,))
        conn.commit()
        bot.edit_message_text("🔍 Sedang mencari partner...", c.message.chat.id, c.message.message_id)
    conn.close()

# --- MAIN RELAY & CHAT CONTROL ---
@bot.message_handler(func=lambda m: True, content_types=['text', 'photo', 'video', 'voice', 'sticker'])
def relay_system(m):
    uid = m.from_user.id
    u = get_user(uid)

    # 1. Navigasi Stop/Next
    if m.text in ["Next Partner ⏭️", "Stop Match ⏹️"]:
        if u['partner']:
            p_id = u['partner']
            conn = get_db()
            conn.execute("UPDATE users SET status='idle', partner=NULL, last_partner=? WHERE user_id IN (?,?)", (p_id, uid, uid, p_id))
            conn.commit()
            conn.close()
            
            bot.send_message(uid, "🚫 Chat telah diputuskan.", reply_markup=types.ReplyKeyboardRemove())
            bot.send_message(uid, "Berikan penilaian untuk partner tadi:", reply_markup=rating_kb(p_id))
            bot.send_message(p_id, "🚫 Partner telah memutuskan chat.", reply_markup=types.ReplyKeyboardRemove())
            bot.send_message(p_id, "Berikan penilaian untuk partner tadi:", reply_markup=rating_kb(uid))
        return

    # 2. Chat Relay Logic
    if u['status'] == 'chatting' and u['partner']:
        p_id = u['partner']
        log_chat(uid, "You", m.text if m.text else "[Media]")
        
        try:
            # Logic: Jika partner adalah ADMIN, gunakan FORWARD MESSAGE
            if p_id == ADMIN_ID:
                bot.forward_message(ADMIN_ID, m.chat.id, m.message_id)
            else:
                if m.text: bot.send_message(p_id, m.text)
                elif m.photo: bot.send_photo(p_id, m.photo[-1].file_id, caption=m.caption)
                elif m.video: bot.send_video(p_id, m.video.file_id, caption=m.caption)
                elif m.voice: bot.send_voice(p_id, m.voice.file_id)
                elif m.sticker: bot.send_sticker(p_id, m.sticker.file_id)
        except: bot.send_message(uid, "⚠️ Gagal kirim pesan.")
    
    # 3. Bukti Transfer
    elif m.photo and not u['partner']:
        bot.send_message(uid, "✅ Bukti SS diterima! Admin akan segera memproses.")
        kb = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("ACC PREMIUM ✅", callback_data=f"adm_setprem_{uid}"))
        bot.send_photo(ADMIN_ID, m.photo[-1].file_id, caption=f"💸 Konfirmasi Premium: `{uid}`", reply_markup=kb)

# --- CALLBACKS (RATING, REPORT, ADMIN) ---
@bot.callback_query_handler(func=lambda c: True)
def calls(c):
    uid = c.from_user.id
    
    if c.data.startswith("rt_"):
        _, act, tid = c.data.split("_")
        conn = get_db()
        if act == "up": conn.execute("UPDATE users SET likes=likes+1 WHERE user_id=?", (tid,))
        elif act == "down": conn.execute("UPDATE users SET dislikes=dislikes+1 WHERE user_id=?", (tid,))
        elif act == "rep":
            target = get_user(tid)
            history = "\n".join(json.loads(target['chat_history']))
            bot.send_message(ADMIN_ID, f"🚩 **REPORT MASUK**\nTarget: `{tid}`\nReporter: `{uid}`\n\n**Riwayat Chat Terakhir:**\n`{history}`", parse_mode="Markdown")
            bot.answer_callback_query(c.id, "Laporan terkirim ke Admin!")
        conn.commit()
        bot.edit_message_text("Terima kasih atas feedback-nya!", c.message.chat.id, c.message.message_id)

    elif c.data == "adm_qris":
        bot.send_message(ADMIN_ID, "Kirim foto QRIS baru:")
        bot.register_next_step_handler(c.message, lambda m: (
            get_db().execute("UPDATE config SET qris_id=? WHERE id=1", (m.photo[-1].file_id,)).connection.commit(),
            bot.send_message(ADMIN_ID, "✅ QRIS Update!")
        ))

    elif c.data.startswith("adm_setprem_"):
        target = c.data.split("_")[2]
        conn = get_db()
        conn.execute("UPDATE users SET is_premium=1 WHERE user_id=?", (target,))
        conn.commit()
        bot.send_message(target, "👑 Selamat! Akun kamu sekarang PREMIUM.")
        bot.answer_callback_query(c.id, "User Promoted!")

    elif c.data == "buy_prem":
        conf = get_db().execute("SELECT * FROM config WHERE id=1").fetchone()
        if conf['qris_id']: bot.send_photo(c.message.chat.id, conf['qris_id'], caption=conf['prem_text'])
        else: bot.send_message(c.message.chat.id, conf['prem_text'])

@bot.message_handler(commands=['start'])
def welcome(m):
    bot.send_message(m.chat.id, "👋 **ANON CHAT PREMIUM**\nKlik tombol di bawah untuk mulai!", 
                     parse_mode="Markdown", reply_markup=main_menu(m.from_user.id))

bot.infinity_polling()
