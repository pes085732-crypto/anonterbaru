import os
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import random
import json

# ================= Konfigurasi & Setup =================
# Pastikan kamu set variable ini di Railway (Variables tab)
BOT_TOKEN = os.getenv('BOT_TOKEN', 'TOKEN_KAMU_DI_SINI')
ADMIN_ID = int(os.getenv('ADMIN_ID', 'ID_TELEGRAM_ADMIN'))

bot = telebot.TeleBot(BOT_TOKEN)

# Setup Database
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY, 
                    gender TEXT, age INTEGER, location TEXT, 
                    is_vip INTEGER DEFAULT 0, karma INTEGER DEFAULT 100,
                    state TEXT DEFAULT 'idle', partner_id INTEGER, 
                    last_partner INTEGER, topic TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY, value TEXT)''')
    conn.commit()
    conn.close()

init_db()

# Temporary Memory untuk Chat History (Biar pas report admin bisa baca)
# Format: { 'id_sesi': ['user1: halo', 'user2: hai'] }
chat_logs = {}

# ================= UI & Keyboards =================
def main_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("🚀 Find a partner"), KeyboardButton("➡️ Next"))
    markup.row(KeyboardButton("⚙️ Settings"), KeyboardButton("👑 VIP"))
    return markup

def chat_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("🛑 Stop"), KeyboardButton("➡️ Next"))
    markup.row(KeyboardButton("🎮 Game Suit"), KeyboardButton("🔗 Share Profil"))
    return markup

def feedback_keyboard(partner_id):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("👍", callback_data=f"rate_up_{partner_id}"),
        InlineKeyboardButton("👎", callback_data=f"rate_down_{partner_id}")
    )
    markup.row(InlineKeyboardButton("⚠️ Laporkan", callback_data=f"report_{partner_id}"))
    return markup

# ================= Fitur Utama & Navigasi =================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.chat.id,))
    conn.commit()
    conn.close()
    
    bot.send_message(message.chat.id, 
                     "Selamat datang di Chat Anon! Gunakan tombol di bawah atau ketik /search untuk mencari partner.",
                     reply_markup=main_keyboard())

# --- Logika Matchmaking (Mencari Partner) ---
@bot.message_handler(func=lambda msg: msg.text in ["🚀 Find a partner", "➡️ Next", "/search", "/next"])
def search_partner(message):
    uid = message.chat.id
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # Putuskan obrolan sebelumnya jika ada
    c.execute("SELECT partner_id, is_vip FROM users WHERE user_id=?", (uid,))
    user_data = c.fetchone()
    if user_data and user_data[0]:
        partner_id = user_data[0]
        c.execute("UPDATE users SET partner_id=NULL, state='idle', last_partner=? WHERE user_id IN (?, ?)", (partner_id, uid, partner_id))
        bot.send_message(partner_id, "Partner kamu telah meninggalkan obrolan 😔", reply_markup=main_keyboard())
        bot.send_message(partner_id, "Tinggalkan feedback untuk partnermu:", reply_markup=feedback_keyboard(uid))
    
    # Set status jadi searching
    c.execute("UPDATE users SET state='searching', partner_id=NULL WHERE user_id=?", (uid,))
    bot.send_message(uid, "🔍 Sedang mencari partner...", reply_markup=main_keyboard())
    
    # Logika Pencarian (VIP Prioritas & Hashtag/Topic, dsb)
    is_vip = user_data[1] if user_data else 0
    
    # Cari kandidat yang juga 'searching'
    c.execute("SELECT user_id, is_vip FROM users WHERE state='searching' AND user_id != ?", (uid,))
    candidates = c.fetchall()
    
    if candidates:
        # Prioritaskan VIP jika kandidat ada yang VIP
        candidates.sort(key=lambda x: x[1], reverse=True) 
        partner_id = candidates[0][0]
        partner_vip = candidates[0][1]
        
        # Matchkan mereka
        c.execute("UPDATE users SET state='chatting', partner_id=? WHERE user_id=?", (partner_id, uid))
        c.execute("UPDATE users SET state='chatting', partner_id=? WHERE user_id=?", (uid, partner_id))
        
        # Buat sesi chat log baru
        chat_logs[f"{uid}_{partner_id}"] = []
        
        # Notifikasi Match
        vip_notice = "\n👑 Partner kamu adalah member VIP!" if partner_vip else ""
        bot.send_message(uid, f"Partner found! 😸{vip_notice}", reply_markup=chat_keyboard())
        bot.send_message(partner_id, "Partner found! 😸", reply_markup=chat_keyboard())
    
    conn.commit()
    conn.close()

# ================= Engine Chatting & Media Sharing =================
@bot.message_handler(content_types=['text', 'photo', 'video', 'voice', 'sticker', 'document'])
def handle_chat(message):
    uid = message.chat.id
    
    # Tangani Stop
    if message.text in ["🛑 Stop", "/stop"]:
        # (Logika stop mirip dengan next, mengubah state jadi idle)
        bot.send_message(uid, "Kamu menghentikan pencarian/obrolan.", reply_markup=main_keyboard())
        return

    # Cek apakah sedang punya partner
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT partner_id FROM users WHERE user_id=?", (uid,))
    res = c.fetchone()
    
    if res and res[0]:
        partner_id = res[0]
        
        # Simpan History Chat untuk Report
        session_key = f"{uid}_{partner_id}" if f"{uid}_{partner_id}" in chat_logs else f"{partner_id}_{uid}"
        if session_key in chat_logs:
            chat_logs[session_key].append(f"{uid}: {message.text if message.text else '[Media/File]'}")
            if len(chat_logs[session_key]) > 50: # Simpan 50 pesan terakhir saja
                chat_logs[session_key].pop(0)

        # -- ADMIN GOD MODE LOGIC --
        if partner_id == ADMIN_ID:
            # Jika partnernya admin, kirim pesan sebagai "Forward" agar admin bisa klik profil user
            bot.forward_message(partner_id, uid, message.message_id)
        else:
            # Mode anonim biasa (Copy message, hapus identitas pengirim)
            bot.copy_message(partner_id, uid, message.message_id)
    else:
        # Jika bukan chat dan bukan perintah admin
        if message.text and not message.text.startswith('/'):
            bot.send_message(uid, "Kamu sedang tidak berada dalam obrolan. Klik '🚀 Find a partner'")
            
    conn.close()

# ================= Fitur Game Suit & Share Link =================
@bot.message_handler(func=lambda msg: msg.text == "🎮 Game Suit")
def game_suit(message):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("✊ Batu", callback_data="suit_batu"),
        InlineKeyboardButton("🖐 Kertas", callback_data="suit_kertas"),
        InlineKeyboardButton("✌️ Gunting", callback_data="suit_gunting")
    )
    bot.send_message(message.chat.id, "Pilih senjatamu:", reply_markup=markup)
    # (Logika callback-nya dibuat di bot.callback_query_handler untuk mengecek siapa yang menang)

@bot.message_handler(func=lambda msg: msg.text == "🔗 Share Profil")
def share_link(message):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT partner_id FROM users WHERE user_id=?", (message.chat.id,))
    res = c.fetchone()
    if res and res[0]:
        username = message.from_user.username
        link = f"https://t.me/{username}" if username else "User ini tidak punya username Telegram."
        bot.send_message(res[0], f"Partner kamu membagikan profilnya:\n{link}")
        bot.send_message(message.chat.id, "Link profil berhasil dikirim!")
    conn.close()

# ================= Inline Feedback & Report =================
@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    data = call.data
    uid = call.message.chat.id
    
    if data.startswith("rate_"):
        # Logika sistem Karma
        partner_id = int(data.split("_")[2])
        action = data.split("_")[1]
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        if action == "up":
            c.execute("UPDATE users SET karma = karma + 2 WHERE user_id=?", (partner_id,))
            bot.answer_callback_query(call.id, "Terima kasih atas feedback positifmu!")
        else:
            c.execute("UPDATE users SET karma = karma - 5 WHERE user_id=?", (partner_id,))
            bot.answer_callback_query(call.id, "Feedback negatif dicatat.")
        conn.commit()
        bot.edit_message_reply_markup(uid, call.message.message_id, reply_markup=None) # hapus tombol
        conn.close()

    elif data.startswith("report_"):
        partner_id = int(data.split("_")[1])
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("VCS/Sange", callback_data=f"rep_vcs_{partner_id}"),
                   InlineKeyboardButton("Spam/Scam", callback_data=f"rep_spam_{partner_id}"))
        bot.edit_message_reply_markup(uid, call.message.message_id, reply_markup=markup)

    elif data.startswith("rep_"):
        # Lapor ke Admin beserta histori chat
        reason = data.split("_")[1]
        partner_id = int(data.split("_")[2])
        bot.answer_callback_query(call.id, "Laporan dikirim ke Admin. Terima kasih.")
        bot.edit_message_reply_markup(uid, call.message.message_id, reply_markup=None)
        
        # Cari histori chat
        session_key = f"{uid}_{partner_id}" if f"{uid}_{partner_id}" in chat_logs else f"{partner_id}_{uid}"
        history = "\n".join(chat_logs.get(session_key, ["Tidak ada histori chat."]))
        
        admin_msg = f"⚠️ **LAPORAN BARU**\nReporter: {uid}\nReported: {partner_id}\nAlasan: {reason}\n\n**Histori Chat:**\n{history}"
        bot.send_message(ADMIN_ID, admin_msg)

# ================= Fitur Khusus Admin =================
@bot.message_handler(commands=['senddb'])
def admin_send_db(message):
    if message.chat.id == ADMIN_ID:
        with open('database.db', 'rb') as doc:
            bot.send_document(ADMIN_ID, doc, caption="Ini file database terbaru.")

@bot.message_handler(func=lambda msg: msg.reply_to_message and msg.reply_to_message.document and msg.text.lower() == 'update')
def admin_update_db(message):
    if message.chat.id == ADMIN_ID:
        file_info = bot.get_file(message.reply_to_message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # Simpan file yang dikirim admin sebagai temp.db
        with open('temp.db', 'wb') as new_file:
            new_file.write(downloaded_file)
        
        # Logika UPDATE DB (Nambahin tanpa me-replace yang lama)
        try:
            conn = sqlite3.connect('database.db')
            # Attach db baru
            conn.execute("ATTACH DATABASE 'temp.db' AS tempdb")
            # Masukkan data baru yang belum ada
            conn.execute("INSERT OR IGNORE INTO users SELECT * FROM tempdb.users")
            conn.commit()
            conn.close()
            os.remove('temp.db')
            bot.reply_to(message, "✅ Database berhasil di-update/digabungkan!")
        except Exception as e:
            bot.reply_to(message, f"❌ Gagal update DB: {e}")

@bot.message_handler(commands=['setvip'])
def admin_set_vip(message):
    if message.chat.id == ADMIN_ID:
        try:
            target_id = int(message.text.split()[1])
            conn = sqlite3.connect('database.db')
            c = conn.cursor()
            c.execute("UPDATE users SET is_vip=1 WHERE user_id=?", (target_id,))
            conn.commit()
            conn.close()
            bot.reply_to(message, f"Berhasil set VIP untuk user {target_id}")
        except:
            bot.reply_to(message, "Format salah. Gunakan: /setvip <user_id>")

# Jalankan Bot
print("Bot sedang berjalan...")
bot.infinity_polling()
