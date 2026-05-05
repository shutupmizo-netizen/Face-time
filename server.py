from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sqlite3
import os

app = Flask(__name__)
CORS(app)

def init_db():
    conn = sqlite3.connect('pk_live.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id TEXT PRIMARY KEY, coins INTEGER, my_votes INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS votes
                 (id INTEGER PRIMARY KEY, boss INTEGER, enemy INTEGER)''')
    c.execute("INSERT OR IGNORE INTO votes (id, boss, enemy) VALUES (1, 0, 0)")
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/data')
def get_data():
    user_id = request.args.get('user_id', 'guest')
    conn = sqlite3.connect('pk_live.db')
    c = conn.cursor()
    c.execute("SELECT coins, my_votes FROM users WHERE user_id=?", (user_id,))
    user = c.fetchone()
    if not user:
        c.execute("INSERT INTO users VALUES (?, 100, 0)", (user_id,))
        conn.commit()
        coins, my_votes = 100, 0
    else:
        coins, my_votes = user
    c.execute("SELECT boss, enemy FROM votes WHERE id=1")
    boss, enemy = c.fetchone()
    conn.close()
    return jsonify({"coins": coins, "my_votes": my_votes, "votes": {"boss": boss, "enemy": enemy}})

@app.route('/api/vote', methods=['POST'])
def vote():
    data = request.json
    user_id = data['user_id']
    team = data['team']
    conn = sqlite3.connect('pk_live.db')
    c = conn.cursor()
    c.execute("SELECT coins FROM users WHERE user_id=?", (user_id,))
    coins = c.fetchone()[0]
    if coins < 10:
        conn.close()
        return jsonify({"error": "Coin a zo"}), 400
    c.execute("UPDATE users SET coins=coins-10, my_votes=my_votes+1 WHERE user_id=?", (user_id,))
    c.execute(f"UPDATE votes SET {team}={team}+1 WHERE id=1")
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/free_coins', methods=['POST'])
def free_coins():
    user_id = request.json['user_id']
    conn = sqlite3.connect('pk_live.db')
    c = conn.cursor()
    c.execute("UPDATE users SET coins=coins+50 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/owner/add_coins', methods=['POST'])
def add_coins():
    data = request.json
    if data['password']!= 'boss2026':
        return jsonify({"error": "Wrong password"}), 403
    user_id = data['user_id']
    amount = int(data['amount'])
    conn = sqlite3.connect('pk_live.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users VALUES (?, 0, 0)", (user_id,))
    c.execute("UPDATE users SET coins=coins+? WHERE user_id=?", (amount, user_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
