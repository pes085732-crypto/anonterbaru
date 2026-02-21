import os
import telebot
import sqlite3
from telebot import types

# Ambil variable dari Railway Environment
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = os.getenv('ADMIN_ID') 

bot = telebot.TeleBot(BOT_TOKEN)

# --- DATABASE SETUP ---
def get_db():
    conn = sqlite3.connect('database.db', check_same_thread=False)
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    # Tambah kolom last_partner untuk fitur hubungkan kembali nanti
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        partner_id INTEGER DEFAULT 0,
        status TEXT DEFAULT 'idle',
        last_partner INTEGER DEFAULT 0
    )''')
    conn.commit()
    conn.close()

init_db()

# --- KEYBOARD UI ---
def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🚀 Find a partner")
    return markup

def chat_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    # Tombol Next dan Stop sejajar di bawah
    markup.row("➡️ Next", "🛑 Stop")
    return markup

# --- FUNGSI MENCARI PARTNER ---
def do_search(uid):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("UPDATE users SET status = 'searching', partner_id = 0 WHERE user_id = ?", (uid,))
    conn.commit()
    
    # Cari partner yang sedang searching
    cursor.execute("SELECT user_id FROM users WHERE status = 'searching' AND user_id != ? LIMIT 1", (uid,))
    partner = cursor.fetchone()
    
    if partner:
        p_id = partner[0]
        cursor.execute("UPDATE users SET status = 'chatting', partner_id = ? WHERE user_id = ?", (p_id, uid))
        cursor.execute("UPDATE users SET status = 'chatting', partner_id = ? WHERE user_id = ?", (uid, p_id))
        conn.commit()
        
        bot.send_message(uid, "Partner ditemukan! Selamat mengobrol 😸", reply_markup=chat_menu())
        bot.send_message(p_id, "Partner ditemukan! Selamat mengobrol 😸", reply_markup=chat_menu())
    else:
        bot.send_message(uid, "🔍 Mencari partner... mohon tunggu.")
    conn.close()

# --- HANDLERS ---

@bot.message_handler(commands=['start'])
def start(message):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.chat.id,))
    conn.commit()
    conn.close()
    bot.send_message(message.chat.id, "Bot Aktif! Klik tombol di bawah.", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "🚀 Find a partner")
def handle_find(message):
    do_search(message.chat.id)

@bot.message_handler(func=lambda m: m.text == "➡️ Next")
def handle_next(message):
    uid = message.chat.id
    conn = get_db()
    cursor = conn.cursor()
    
    # Cek partner saat ini
    cursor.execute("SELECT partner_id FROM users WHERE user_id = ?", (uid,))
    res = cursor.fetchone()
    
    if res and res[0] != 0:
        p_id = res[0]
        # Beritahu partner lama
        bot.send_message(p_id, "Partner kamu telah pergi meninggalkan obrolan.", reply_markup=main_menu())
        # Update status dua-duanya jadi idle dulu
        cursor.execute("UPDATE users SET status = 'idle', partner_id = 0, last_partner = ? WHERE user_id = ?", (p_id, uid))
        cursor.execute("UPDATE users SET status = 'idle', partner_id = 0, last_partner = ? WHERE user_id = ?", (uid, p_id))
        conn.commit()
    
    conn.close()
    # Langsung cari partner baru
    do_search(uid)

@bot.message_handler(func=lambda m: m.text == "🛑 Stop")
def handle_stop(message):
    uid = message.chat.id
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT partner_id FROM users WHERE user_id = ?", (uid,))
    res = cursor.fetchone()
    
    if res and res[0] != 0:
        p_id = res[0]
        bot.send_message(p_id, "Partner menghentikan obrolan.", reply_markup=main_menu())
        cursor.execute("UPDATE users SET status = 'idle', partner_id = 0, last_partner = ? WHERE user_id = ?", (p_id, uid))
        cursor.execute("UPDATE users SET status = 'idle', partner_id = 0, last_partner = ? WHERE user_id = ?", (uid, p_id))
    else:
        cursor.execute("UPDATE users SET status = 'idle', partner_id = 0 WHERE user_id = ?", (uid,))
    
    conn.commit()
    conn.close()
    bot.send_message(uid, "Obrolan dihentikan.", reply_markup=main_menu())

@bot.message_handler(content_types=['text', 'photo', 'video', 'voice', 'sticker'])
def chatting(message):
    uid = message.chat.id
    # Abaikan jika pesan berupa tombol menu
    if message.text in ["🚀 Find a partner", "➡️ Next", "🛑 Stop"]:
        return

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT partner_id, status FROM users WHERE user_id = ?", (uid,))
    res = cursor.fetchone()
    
    if res and res[1] == 'chatting':
        # Copy message tanpa identitas pengirim (anonim)
        try:
            bot.copy_message(res[0], uid, message.message_id)
        except:
            pass
    conn.close()

bot.infinity_polling()
