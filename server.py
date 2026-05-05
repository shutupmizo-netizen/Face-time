from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import bcrypt
import secrets
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(32)
socketio = SocketIO(app, cors_allowed_origins="*")

users_db = {}
sessions_db = {}
pending_payments = []
chat_messages = []
game_data = {'boss': 0, 'enemy': 0, 'online': 0}

OWNER_USERNAME = 'boss'

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('signup')
def handle_signup(data):
    username = data['username'].strip().lower()
    password = data['password']
    if username in users_db:
        emit('auth_error', {'msg': 'Username hman a ni tawh'})
        return
    if len(username) < 3 or len(password) < 4:
        emit('auth_error', {'msg': 'Username/Password tawi lutuk'})
        return
    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    users_db[username] = {'password_hash': password_hash, 'coins': 500, 'free_claimed': True}
    session_id = secrets.token_urlsafe(32)
    sessions_db[session_id] = username
    emit('auth_success', {'session_id': session_id, 'username': username, 'coins': 500, 'is_owner': username == OWNER_USERNAME})

@socketio.on('login')
def handle_login(data):
    username = data['username'].strip().lower()
    password = data['password']
    if username not in users_db:
        emit('auth_error', {'msg': 'Account a awm lo. Sign Up rawh'})
        return
    stored_hash = users_db[username]['password_hash']
    if not bcrypt.checkpw(password.encode('utf-8'), stored_hash):
        emit('auth_error', {'msg': 'Password dik lo'})
        return
    session_id = secrets.token_urlsafe(32)
    sessions_db[session_id] = username
    emit('auth_success', {'session_id': session_id, 'username': username, 'coins': users_db[username]['coins'], 'is_owner': username == OWNER_USERNAME})

@socketio.on('verify_session')
def verify_session(data):
    session_id = data['session_id']
    if session_id in sessions_db:
        username = sessions_db[session_id]
        emit('auth_success', {'session_id': session_id, 'username': username, 'coins': users_db[username]['coins'], 'is_owner': username == OWNER_USERNAME})
        for msg in chat_messages[-20:]:
            emit('chat_message', msg)
    else:
        emit('auth_error', {'msg': 'Session expired'})

@socketio.on('vote')
def handle_vote(data):
    session_id = data['session_id']
    if session_id not in sessions_db:
        emit('vote_error', {'msg': 'Login phawt rawh'})
        return
    username = sessions_db[session_id]
    team = data['team']
    if users_db[username]['coins'] < 10:
        emit('vote_error', {'msg': 'Coins a tlem'})
        return
    users_db[username]['coins'] -= 10
    game_data += 1  # DIK TAWH ✅
    emit('update', game_data, broadcast=True)
    emit('coins_update', {'coins': users_db[username]['coins']})

@socketio.on('send_chat')
def handle_chat(data):
    session_id = data['session_id']
    if session_id not in sessions_db:
        return
    username = sessions_db[session_id]
    message = data['message'][:200].strip()
    if not message:
        return
    bad_words = ['chhe', 'hmaw', 'dawt', 'fuck', 'sex', 'chhu', 'mawng']
    msg_lower = message.lower()
    for word in bad_words:
        if word in msg_lower:
            emit('chat_error', {'msg': 'Thu mawi lo hman phal loh'})
            return
    chat_data = {'username': username, 'message': message, 'is_owner': username == OWNER_USERNAME}
    chat_messages.append(chat_data)
    if len(chat_messages) > 100:
        chat_messages.pop(0)
    emit('chat_message', chat_data, broadcast=True)

@socketio.on('payment_submit')
def handle_payment(data):
    session_id = data['session_id']
    if session_id not in sessions_db:
        return
    username = sessions_db[session_id]
    pending_payments.append({'userId': username, 'utr': data['utr'], 'coins': data['coins']})
    emit('pending_update', pending_payments, broadcast=True)

@socketio.on('owner_approve_payment')
def approve_payment(data):
    session_id = data['session_id']
    if session_id not in sessions_db or sessions_db[session_id]!= OWNER_USERNAME:
        return
    global pending_payments
    for p in pending_payments:
        if p['utr'] == data['utr']:
            users_db[p['userId']]['coins'] += int(data['coins'])
            pending_payments = [x for x in pending_payments if x['utr']!= data['utr']]
            emit('payment_approved', {'userId': p['userId'], 'coins': data['coins']}, broadcast=True)
            emit('pending_update', pending_payments, broadcast=True)
            break

@socketio.on('owner_add_coins')
def add_coins(data):
    session_id = data['session_id']
    if session_id not in sessions_db or sessions_db[session_id]!= OWNER_USERNAME:
        return
    target_user = data['userId'].lower()
    if target_user in users_db:
        users_db[target_user]['coins'] += int(data['amount'])
        emit('coins_manual_add', {'userId': target_user, 'amount': data['amount']}, broadcast=True)

@socketio.on('owner_declare_winner')
def declare_winner(data):
    session_id = data['session_id']
    if session_id not in sessions_db or sessions_db[session_id]!= OWNER_USERNAME:
        return
    emit('winner_announced', {'team': data['team']}, broadcast=True)
    add_system_chat(f"🏆 {data['team'].upper()} WINS! 🏆")

@socketio.on('owner_reset')
def reset_votes(data):
    session_id = data['session_id']
    if session_id not in sessions_db or sessions_db[session_id]!= OWNER_USERNAME:
        return
    game_data['boss'] = 0
    game_data['enemy'] = 0
    emit('update', game_data, broadcast=True)
    add_system_chat("🔄 Votes reset a ni e")

@socketio.on('get_free_coins')
def give_free_coins(data):
    session_id = data['session_id']
    if session_id not in sessions_db:
        return
    username = sessions_db[session_id]
    if users_db[username].get('free_claimed_extra'):
        return
    users_db[username]['coins'] += 500
    users_db[username]['free_claimed_extra'] = True
    emit('free_coins_success', {'coins': users_db[username]['coins']})
    emit('coins_update', {'coins': users_db[username]['coins']})

@socketio.on('start_stream')
def start_stream(data):
    session_id = data['session_id']
    if session_id not in sessions_db:
        return
    username = sessions_db[session_id]
    emit('stream_started', {'userId': username, 'team': data['team']}, broadcast=True)
    add_system_chat(f"🔴 {username} a rawn LIVE e!")

@socketio.on('stop_stream')
def stop_stream(data):
    session_id = data['session_id']
    if session_id not in sessions_db:
        return
    username = sessions_db[session_id]
    emit('stream_stopped', {'userId': username}, broadcast=True)
    add_system_chat(f"⏹️ {username} live a tawp e")

@socketio.on('join')
def handle_join(data):
    game_data['online'] += 1
    emit('update', game_data, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    game_data['online'] = max(0, game_data['online'] - 1)
    emit('update', game_data, broadcast=True)

def add_system_chat(msg):
    chat_data = {'username': 'System', 'message': msg, 'is_owner': True}
    chat_messages.append(chat_data)
    emit('chat_message', chat_data, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
