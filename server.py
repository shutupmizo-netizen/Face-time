from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import bcrypt
import secrets
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(32)
socketio = SocketIO(app, cors_allowed_origins="*")

# Database
users_db = {} # {username: {password_hash, coins, free_claimed}}
sessions_db = {} # {session_id: username}
pending_payments = []
chat_messages = []
game_data = {
    'boss': 0,
    'enemy': 0,
    'online': 0
}

# Owner config - Hei hi thlak rawh
OWNER_HASH = bcrypt.hashpw('boss2026'.encode('utf-8'), bcrypt.gensalt())
OWNER_USERNAME = 'boss'

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('signup')
def handle_signup(data):
    username = data['username'].strip().lower()
    password = data['password']

    if username in users_db:
        emit('auth_error', {'msg': 'Username hman a ni tawh. Dang thlang rawh'})
        return

    if len(username) < 3:
        emit('auth_error', {'msg': 'Username 3 characters ai a tawi thei lo'})
        return

    if len(password) < 4:
        emit('auth_error', {'msg': 'Password 4 characters ai a tawi thei lo'})
        return

    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    users_db[username] = {
        'password_hash': password_hash,
        'coins': 50,
        'free_claimed': True
    }

    session_id = secrets.token_urlsafe(32)
    sessions_db[session_id] = username

    emit('auth_success', {
        'session_id': session_id,
        'username': username,
        'coins': 50,
        'is_owner': username == OWNER_USERNAME
    })

@socketio.on('login')
def handle_login(data):
    username = data['username'].strip().lower()
    password = data['password']

    if username not in users_db:
        emit('auth_error', {'msg': 'Account a awm lo. Sign Up phawt rawh'})
        return

    stored_hash = users_db[username]['password_hash']
    if not bcrypt.checkpw
