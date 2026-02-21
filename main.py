import os
import telebot
import sqlite3
from telebot import types

# Ambil variable dari Railway Environment
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = os.getenv('ADMIN_ID') # ID Telegram kamu

bot = telebot.TeleBot(BOT_TOKEN)

# --- DATABASE SETUP ---
def get_db():
    conn = sqlite3.connect('database.db', check_same_thread=False)
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        partner_id INTEGER DEFAULT 0,
        status TEXT DEFAULT 'idle'
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
    markup.row("➡️ Next", "🛑 Stop")
    return markup

# --- LOGIC ---
@bot.message_handler(commands=['start'])
def start(message):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.chat.id,))
    conn.commit()
    conn.close()
    bot.send_message(message.chat.id, "Selamat datang! Klik tombol di bawah buat cari temen.", reply_markup=main_menu())

@bot.message_handler(func=lambda m: m.text == "🚀 Find a partner" or m.text == "/search")
def search(message):
    uid = message.chat.id
    conn = get_db()
    cursor = conn.cursor()
    
    # Set status diri sendiri jadi nyari
    cursor.execute("UPDATE users SET status = 'searching', partner_id = 0 WHERE user_id = ?", (uid,))
    conn.commit()
    
    # Cari orang lain yang lagi searching
    cursor.execute("SELECT user_id FROM users WHERE status = 'searching' AND user_id != ? LIMIT 1", (uid,))
    partner = cursor.fetchone()
    
    if partner:
        p_id = partner[0]
        # Update dua-duanya jadi chatting
        cursor.execute("UPDATE users SET status = 'chatting', partner_id = ? WHERE user_id = ?", (p_id, uid))
        cursor.execute("UPDATE users SET status = 'chatting', partner_id = ? WHERE user_id = ?", (uid, p_id))
        conn.commit()
        
        bot.send_message(uid, "Partner found! 😸", reply_markup=chat_menu())
        bot.send_message(p_id, "Partner found! 😸", reply_markup=chat_menu())
    else:
        bot.send_message(uid, "🔍 Mencari partner... tunggu bentar ya.")
    conn.close()

@bot.message_handler(func=lambda m: m.text == "🛑 Stop" or m.text == "/stop")
def stop(message):
    uid = message.chat.id
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT partner_id FROM users WHERE user_id = ?", (uid,))
    res = cursor.fetchone()
    
    if res and res[0] != 0:
        p_id = res[0]
        cursor.execute("UPDATE users SET status = 'idle', partner_id = 0 WHERE user_id IN (?,?)", (uid, p_id))
        conn.commit()
        bot.send_message(uid, "Chat dihentikan.", reply_markup=main_menu())
        bot.send_message(p_id, "Partner menghentikan chat.", reply_markup=main_menu())
    else:
        cursor.execute("UPDATE users SET status = 'idle' WHERE user_id = ?", (uid,))
        conn.commit()
        bot.send_message(uid, "Pencarian dibatalkan.", reply_markup=main_menu())
    conn.close()

# Handle Pesan Masuk
@bot.message_handler(content_types=['text', 'photo', 'video', 'voice', 'sticker'])
def chatting(message):
    uid = message.chat.id
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT partner_id, status FROM users WHERE user_id = ?", (uid,))
    res = cursor.fetchone()
    
    if res and res[1] == 'chatting':
        # Kirim ke partner
        bot.copy_message(res[0], uid, message.message_id)
    conn.close()

print("Bot Running...")
bot.infinity_polling()
