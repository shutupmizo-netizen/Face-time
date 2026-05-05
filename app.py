from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import sqlite3
import hashlib
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'pk-battle-legal-safe-2026'
socketio = SocketIO(app, cors_allowed_origins="*")

# Database setup
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY,
                  username TEXT UNIQUE,
                  password TEXT,
                  coins INTEGER DEFAULT 0,
                  points INTEGER DEFAULT 0,
                  is_owner INTEGER DEFAULT 0)''')
    
    # BOSS account auto siam
    password = hashlib.sha256('BOSS123'.encode()).hexdigest()
    c.execute("INSERT OR REPLACE INTO users (username, password, coins, points, is_owner) VALUES (?,?,?,?,?)", 
              ('BOSS', password, 500, 0, 1))
    
    conn.commit()
    conn.close()
    print("Database ready ✅ BOSS account created")

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('login')
def handle_login(data):
    username = data.get('username')
    password = data.get('password')
    print(f"Login attempt: {username}")
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=?", (username,))
    user = c.fetchone()
    conn.close()
    
    if user:
        db_password = user[2] # password column
        hashed_input = hashlib.sha256(password.encode()).hexdigest()
        
        if db_password == hashed_input:
            emit('login_success', {
                'username': user[1],
                'coins': user[3],
                'points': user[4],
                'is_owner': bool(user[5])
            })
            print(f"Login success: {username} Coins: {user[3]}")
        else:
            emit('login_failed')
            print(f"Login failed: Wrong password for {username}")
    else:
        emit('login_failed')
        print(f"Login failed: User {username} not found")

if __name__ == '__main__':
    init_db() # Server start apiangin DB check + BOSS siam
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
