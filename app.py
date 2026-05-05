from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import sqlite3
import hashlib
import os
import random
from datetime import datetime, timedelta
import threading
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'pk-battle-legal-safe-2026'
socketio = SocketIO(app, cors_allowed_origins="*")

online_users = {}
battle_votes = {'boss': 0, 'enemy': 0}
sessions = {}
live_streamers = set()
party_rooms = {} # {room_id: {owner, users: [], start_time, crown_seat}}

def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY,
                  username TEXT UNIQUE,
                  password TEXT,
                  coins INTEGER DEFAULT 0,
                  points INTEGER DEFAULT 0,
                  last_free TIMESTAMP,
                  last_spin TIMESTAMP,
                  last_flip TIMESTAMP,
                  last_box TIMESTAMP,
                  last_guess TIMESTAMP,
                  is_owner INTEGER DEFAULT 0,
                  profile_pic TEXT DEFAULT 'https://i.imgur.com/8Km9tLL.png',
                  bio TEXT DEFAULT 'PK Battle Player',
                  followers INTEGER DEFAULT 0,
                  following INTEGER DEFAULT 0)''')

    c.execute('''CREATE TABLE IF NOT EXISTS follows
                 (id INTEGER PRIMARY KEY,
                  follower TEXT,
                  following TEXT,
                  UNIQUE(follower, following))''')

    c.execute('''CREATE TABLE IF NOT EXISTS party_history
                 (id INTEGER PRIMARY KEY,
                  username TEXT,
                  room_id TEXT,
                  joined_at TIMESTAMP,
                  points_earned INTEGER DEFAULT 0,
                  coins_earned INTEGER DEFAULT 0)''')

    password = hashlib.sha256('BOSS123'.encode()).hexdigest()
    c.execute("INSERT OR REPLACE INTO users (username, password, coins, points, is_owner, bio, profile_pic) VALUES (?,?,?,?,?,?,?)",
              ('BOSS', password, 500, 100, 1, 'PK Battle Owner 👑', 'https://i.imgur.com/8Km9tLL.png'))

    conn.commit()
    conn.close()
    print("Database ready ✅ BOSS account created")

def get_user_data(username):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=?", (username,))
    user = c.fetchone()
    conn.close()
    if user:
        return {
            'id': user[0], 'username': user[1], 'password': user[2], 'coins': user[3],
            'points': user[4], 'last_free': user[5], 'last_spin': user[6], 'last_flip': user[7],
            'last_box': user[8], 'last_guess': user[9], 'is_owner': user[10],
            'profile_pic': user[11], 'bio': user[12], 'followers': user[13], 'following': user[14]
        }
    return None

def check_cooldown(last_time_str, hours=1):
    if not last_time_str: return True
    last_time = datetime.fromisoformat(last_time_str)
    return datetime.now() - last_time >= timedelta(hours=hours)

def party_timer(room_id):
    time.sleep(10800) # 3 hours = 10800 seconds
    if room_id in party_rooms:
        room = party_rooms[room_id]
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        for username in room['users']:
            c.execute("UPDATE users SET points = points + 1000 WHERE username=?", (username,))
            c.execute("INSERT INTO party_history (username, room_id, joined_at, points_earned) VALUES (?,?,?,?)",
                      (username, room_id, room['start_time'].isoformat(), 1000))
        conn.commit()
        conn.close()
        socketio.emit('party_ended', {'room_id': room_id, 'msg': '🎉 Party zo! Member zawng zawngin 1000 Points an hmu!'}, room=room_id)
        del party_rooms[room_id]

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    online_users[request.sid] = None
    emit('online_update', {'count': len(online_users)}, broadcast=True)
    emit('party_rooms_list', list(party_rooms.keys()))

@socketio.on('disconnect')
def handle_disconnect():
    username = online_users.get(request.sid)
    if username:
        if username in live_streamers:
            live_streamers.remove(username)
        # Remove from party rooms
        for room_id, room in list(party_rooms.items()):
            if username in room['users']:
                room['users'].remove(username)
                if username == room['crown_seat']:
                    room['crown_seat'] = None
                socketio.emit('party_update', {'room_id': room_id, 'users': room['users'], 'crown_seat': room['crown_seat']}, room=room_id)
    if request.sid in online_users:
        del online_users[request.sid]
    emit('online_update', {'count': len(online_users)}, broadcast=True)

@socketio.on('verify_session')
def handle_verify_session(data):
    session_id = data.get('session_id')
    username = sessions.get(session_id)
    if username:
        user = get_user_data(username)
        if user:
            online_users[request.sid] = username
            emit('auth_success', {
                'session_id': session_id,
                'username': user['username'],
                'coins': user['coins'],
                'is_owner': bool(user['is_owner']),
                'profile': {
                    'profile_pic': user['profile_pic'],
                    'bio': user['bio'],
                    'followers': user['followers'],
                    'following': user['following'],
                    'points': user['points']
                }
            })

@socketio.on('signup')
def handle_signup(data):
    username = data.get('username', '').strip()
    password = data.get('password', '')
    if not username or not password or len(username) < 3 or len(password) < 4:
        emit('auth_error', {'msg': 'Username/Password tawi lutuk'})
        return
    hashed = hashlib.sha256(password.encode()).hexdigest()
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password, coins, points) VALUES (?,?,?,?)", (username, hashed, 50, 0))
        conn.commit()
        user = get_user_data(username)
        session_id = os.urandom(16).hex()
        sessions[session_id] = username
        online_users[request.sid] = username
        emit('auth_success', {
            'session_id': session_id,
            'username': user['username'],
            'coins': user['coins'],
            'is_owner': bool(user['is_owner']),
            'profile': {
                'profile_pic': user['profile_pic'],
                'bio': user['bio'],
                'followers': user['followers'],
                'following': user['following'],
                'points': user['points']
            }
        })
    except sqlite3.IntegrityError:
        emit('auth_error', {'msg': 'Username hman a ni tawh'})
    conn.close()

@socketio.on('login')
def handle_login(data):
    username = data.get('username', '').strip()
    password = data.get('password', '')
    user = get_user_data(username)
    if user:
        hashed_input = hashlib.sha256(password.encode()).hexdigest()
        if user['password'] == hashed_input:
            session_id = os.urandom(16).hex()
            sessions[session_id] = username
            online_users[request.sid] = username
            emit('auth_success', {
                'session_id': session_id,
                'username': user['username'],
                'coins': user['coins'],
                'is_owner': bool(user['is_owner']),
                'profile': {
                    'profile_pic': user['profile_pic'],
                    'bio': user['bio'],
                    'followers': user['followers'],
                    'following': user['following'],
                    'points': user['points']
                }
            })
        else:
            emit('auth_error', {'msg': 'Password dik lo'})
    else:
        emit('auth_error', {'msg': 'Username hmuh loh'})

@socketio.on('get_profile')
def handle_get_profile(data):
    username = data.get('username')
    user = get_user_data(username)
    current_user = online_users.get(request.sid)
    if user and current_user:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("SELECT * FROM follows WHERE follower=? AND following=?", (current_user, username))
        is_following = c.fetchone() is not None
        conn.close()
        emit('profile_data', {
            'username': user['username'], 'profile_pic': user['profile_pic'], 'bio': user['bio'],
            'followers': user['followers'], 'following': user['following'],
            'coins': user['coins'], 'points': user['points'], 'is_following': is_following
        })

@socketio.on('toggle_follow')
def handle_toggle_follow(data):
    follower = online_users.get(request.sid)
    following = data.get('target')
    if not follower or not following or follower == following: return
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT * FROM follows WHERE follower=? AND following=?", (follower, following))
    existing = c.fetchone()
    if existing:
        c.execute("DELETE FROM follows WHERE follower=? AND following=?", (follower, following))
        c.execute("UPDATE users SET followers = followers - 1 WHERE username=?", (following,))
        c.execute("UPDATE users SET following = following - 1 WHERE username=?", (follower,))
    else:
        c.execute("INSERT INTO follows (follower, following) VALUES (?,?)", (follower, following))
        c.execute("UPDATE users SET followers = followers + 1 WHERE username=?", (following,))
        c.execute("UPDATE users SET following = following + 1 WHERE username=?", (follower,))
    conn.commit()
    conn.close()
    handle_get_profile({'username': following})

@socketio.on('update_profile')
def handle_update_profile(data):
    username = online_users.get(request.sid)
    if not username: return
    bio = data.get('bio', '')[:100]
    profile_pic = data.get('profile_pic', '')
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("UPDATE users SET bio=?, profile_pic=? WHERE username=?", (bio, profile_pic, username))
    conn.commit()
    conn.close()
    handle_get_profile({'username': username})

@socketio.on('go_live')
def handle_go_live(data):
    username = data.get('username')
    if username:
        live_streamers.add(username)
        emit('live_update', {'username': username, 'status': 'live'}, broadcast=True)

@socketio.on('stop_live')
def handle_stop_live(data):
    username = data.get('username')
    if username and username in live_streamers:
        live_streamers.remove(username)
        emit('live_update', {'username': username, 'status': 'offline'}, broadcast=True)

@socketio.on('send_chat')
def handle_chat(data):
    emit('chat_message', {
        'username': data['username'],
        'msg': data['msg'][:200],
        'profile_pic': data.get('profile_pic', 'https://i.imgur.com/8Km9tLL.png')
    }, broadcast=True)

@socketio.on('vote')
def handle_vote(data):
    side = data.get('side')
    username = data.get('username')
    if side in battle_votes and username:
        user = get_user_data(username)
        if user and user['coins'] >= 10:
            battle_votes += 1
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute("UPDATE users SET coins = coins - 10, points = points + 5 WHERE username=?", (username,))
            conn.commit()
            conn.close()
            emit('vote_update', battle_votes, broadcast=True)

@socketio.on('get_free_coins')
def handle_get_free_coins(data):
    username = data.get('username')
    if not username: return
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT last_free FROM users WHERE username=?", (username,))
    result = c.fetchone()
    can_claim = True
    if result and result[0]:
        last_free = datetime.fromisoformat(result[0])
        if datetime.now() - last_free < timedelta(hours=24):
            can_claim = False
    if can_claim:
        c.execute("UPDATE users SET coins = coins + 500, last_free =? WHERE username=?", (datetime.now().isoformat(), username))
        conn.commit()
        c.execute("SELECT coins FROM users WHERE username=?", (username,))
        new_coins = c.fetchone()[0]
        emit('coins_update', {'coins': new_coins})
    else:
        emit('auth_error', {'msg': '24 hours nghak rawh'})
    conn.close()

# 🎰 GAME 1: SPIN WHEEL
@socketio.on('spin_wheel')
def handle_spin_wheel(data):
    username = data.get('username')
    if not username: return
    user = get_user_data(username)
    if not user or user['coins'] < 20:
        emit('game_result', {'success': False, 'game': 'spin', 'msg': 'Coins i nei tlem! 20 Coins a ngai'})
        return
    if not check_cooldown(user['last_spin'], 1):
        emit('game_result', {'success': False, 'game': 'spin', 'msg': 'Cooldown! 1 hour nghak rawh'})
        return

    rewards = [
        {'points': 5, 'chance': 40, 'msg': '🎁 5 Points!'},
        {'points': 10, 'chance': 30, 'msg': '🎁 10 Points!'},
        {'points': 25, 'chance': 15, 'msg': '🎉 25 Points!'},
        {'points': 50, 'chance': 10, 'msg': '💎 50 Points JACKPOT!'},
        {'points': 100, 'chance': 5, 'msg': '👑 100 POINTS MEGA WIN!'}
    ]
    rand = random.randint(1, 100)
    cumulative = 0
    won = rewards[0]
    for reward in rewards:
        cumulative += reward['chance']
        if rand <= cumulative:
            won = reward
            break

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("UPDATE users SET coins = coins - 20, points = points +?, last_spin =? WHERE username=?",
              (won['points'], datetime.now().isoformat(), username))
    conn.commit()
    user = get_user_data(username)
    conn.close()
    emit('game_result', {'success': True, 'game': 'spin', 'msg': won['msg'], 'points_won': won['points'], 'new_coins': user['coins'], 'new_points': user['points']})

# 🪙 GAME 2: COIN FLIP
@socketio.on('coin_flip')
def handle_coin_flip(data):
    username = data.get('username')
    choice = data.get('choice')
    if not username: return
    user = get_user_data(username)
    if not user or user['coins'] < 10:
        emit('game_result', {'success': False, 'game': 'flip', 'msg': 'Coins i nei tlem! 10 Coins a ngai'})
        return

    result = random.choice(['heads', 'tails'])
    won = result == choice
    coins_change = 10 if won else -10
    points_change = 20 if won else 0

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("UPDATE users SET coins = coins +?, points = points +?, last_flip =? WHERE username=?",
              (coins_change, points_change, datetime.now().isoformat(), username))
    conn.commit()
    user = get_user_data(username)
    conn.close()

    msg = f'🎉 WIN! {result.upper()} - +20 Points!' if won else f'😢 LOSE! {result.upper()}'
    emit('game_result', {'success': True, 'game': 'flip', 'won': won, 'result': result, 'msg': msg, 'new_coins': user['coins'], 'new_points': user['points']})

# 🎁 GAME 3: LUCKY BOX
@socketio.on('lucky_box')
def handle_lucky_box(data):
    username = data.get('username')
    if not username: return
    user = get_user_data(username)
    if not user or user['coins'] < 30:
        emit('game_result', {'success': False, 'game': 'box', 'msg': 'Coins i nei tlem! 30 Coins a ngai'})
        return
    if not check_cooldown(user['last_box'], 2):
        emit('game_result', {'success': False, 'game': 'box', 'msg': 'Cooldown! 2 hours nghak rawh'})
        return

    boxes = [
        {'points': 10, 'chance': 35, 'msg': '📦 Common Box - 10 Points'},
        {'points': 30, 'chance': 30, 'msg': '🎁 Rare Box - 30 Points!'},
        {'points': 60, 'chance': 20, 'msg': '💎 Epic Box - 60 Points!!'},
        {'points': 100, 'chance': 10, 'msg': '👑 Legendary Box - 100 Points!!!'},
        {'points': 150, 'chance': 5, 'msg': '🌟 MYTHIC BOX - 150 POINTS!!!!'}
    ]
    rand = random.randint(1, 100)
    cumulative = 0
    won = boxes[0]
    for box in boxes:
        cumulative += box['chance']
        if rand <= cumulative:
            won = box
            break

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("UPDATE users SET coins = coins - 30, points = points +?, last_box =? WHERE username=?",
              (won['points'], datetime.now().isoformat(), username))
    conn.commit()
    user = get_user_data(username)
    conn.close()
    emit('game_result', {'success': True, 'game': 'box', 'msg': won['msg'], 'points_won': won['points'], 'new_coins': user['coins'], 'new_points': user['points']})

# 🔢 GAME 4: NUMBER GUESS
@socketio.on('number_guess')
def handle_number_guess(data):
    username = data.get('username')
    guess = data.get('guess')
    if not username or guess is None: return
    user = get_user_data(username)
    if not user or user['coins'] < 15:
        emit('game_result', {'success': False, 'game': 'guess', 'msg': 'Coins i nei tlem! 15 Coins a ngai'})
        return

    correct = random.randint(1, 10)
    won = int(guess) == correct
    coins_change = 35 if won else -15
    points_change = 50 if won else 0

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("UPDATE users SET coins = coins +?, points = points +?, last_guess =? WHERE username=?",
              (coins_change, points_change, datetime.now().isoformat(), username))
    conn.commit()
    user = get_user_data(username)
    conn.close()

    msg = f'🎯 CORRECT! Number {correct} - +50 Points +35 Coins!' if won else f'❌ WRONG! Correct: {correct}'
    emit('game_result', {'success': True, 'game': 'guess', 'won': won, 'correct': correct, 'msg': msg, 'new_coins': user['coins'], 'new_points': user['points']})

# 🎉 PARTY ROOM SYSTEM
@socketio.on('create_party')
def handle_create_party(data):
    username = data.get('username')
    room_name = data.get('room_name', f'{username} Party').strip()
    if not username: return

    room_id = f"party_{username}_{int(time.time())}"
    party_rooms[room_id] = {
        'owner': username,
        'name': room_name,
        'users': [username],
        'crown_seat': None,
        'start_time': datetime.now(),
        'max_users': 15
    }

    join_room(room_id)
    emit('party_created', {'room_id': room_id, 'room_name': room_name, 'users': [username], 'crown_seat': None})
    emit('party_rooms_list', list(party_rooms.keys()), broadcast=True)

    # Start 3 hour timer
    threading.Thread(target=party_timer, args=(room_id,), daemon=True).start()

@socketio.on('join_party')
def handle_join_party(data):
    username = data.get('username')
    room_id = data.get('room_id')
    if not username or room_id not in party_rooms: return

    room = party_rooms[room_id]
    if len(room['users']) >= room['max_users']:
        emit('party_error', {'msg': 'Party Room a full! 15 users max'})
        return

    if username not in room['users']:
        room['users'].append(username)
        join_room(room_id)
        socketio.emit('party_update', {'room_id': room_id, 'users': room['users'], 'crown_seat': room['crown_seat']}, room=room_id)

@socketio.on('leave_party')
def handle_leave_party(data):
    username = data.get('username')
    room_id = data.get('room_id')
    if not username or room_id not in party_rooms: return

    room = party_rooms[room_id]
    if username in room['users']:
        room['users'].remove(username)
        if username == room['crown_seat']:
            room['crown_seat'] = None
        leave_room(room_id)
        socketio.emit('party_update', {'room_id': room_id, 'users': room['users'], 'crown_seat': room['crown_seat']}, room=room_id)

@socketio.on('sit_crown_seat')
def handle_sit_crown_seat(data):
    username = data.get('username')
    room_id = data.get('room_id')
    if not username or room_id not in party_rooms: return

    room = party_rooms[room_id]
    if room['crown_seat'] is not None:
        emit('party_error', {'msg': 'Crown Seat a hman a ni tawh!'})
        return

    if username not in room['users']:
        emit('party_error', {'msg': 'Party ah lut phawt rawh!'})
        return

    room['crown_seat'] = username
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("UPDATE users SET coins = coins + 500 WHERE username=?", (username,))
    conn.commit()
    user = get_user_data(username)
    conn.close()

    socketio.emit('party_update', {'room_id': room_id, 'users': room['users'], 'crown_seat': room['crown_seat']}, room=room_id)
    emit('coins_update', {'coins': user['coins']})
    emit('party_notification', {'msg': f'👑 {username} Crown Seat ah a thu! +500 Coins!'}, room=room_id)

@socketio.on('get_party_rooms')
def handle_get_party_rooms():
    rooms_data = []
    for room_id, room in party_rooms.items():
        rooms_data.append({
            'room_id': room_id,
            'name': room['name'],
            'owner': room['owner'],
            'users': len(room['users']),
            'max': room['max_users'],
            'crown_taken': room['crown_seat'] is not None
        })
    emit('party_rooms_list', rooms_data)

@socketio.on('add_coins')
def handle_add_coins(data):
    username = data.get('username')
    coins = data.get('coins', 0)
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("UPDATE users SET coins = coins +? WHERE username=?", (coins, username))
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("🚀 PK BATTLE + 4 GAMES + PARTY ROOM RUNNING ON http://0.0.0.0:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
