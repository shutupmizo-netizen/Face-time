from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import sqlite3
import hashlib
import os
import random
from datetime import datetime, timedelta
import threading
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'pk-battle-v9-video-2026')
socketio = SocketIO(app, cors_allowed_origins="*")

online_users = {}
battle_votes = {'boss': 0, 'enemy': 0}
sessions = {}
live_streamers = {}
party_rooms = {}

def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT,
                  coins INTEGER DEFAULT 0, points INTEGER DEFAULT 0, last_free TIMESTAMP,
                  last_spin TIMESTAMP, last_flip TIMESTAMP, last_box TIMESTAMP,
                  last_guess TIMESTAMP, is_owner INTEGER DEFAULT 0,
                  profile_pic TEXT DEFAULT 'https://i.imgur.com/8Km9tLL.png',
                  bio TEXT DEFAULT 'PK Battle Player', followers INTEGER DEFAULT 0,
                  following INTEGER DEFAULT 0, total_gifts INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS follows
                 (id INTEGER PRIMARY KEY, follower TEXT, following TEXT,
                  UNIQUE(follower, following))''')
    c.execute('''CREATE TABLE IF NOT EXISTS party_history
                 (id INTEGER PRIMARY KEY, username TEXT, room_id TEXT,
                  joined_at TIMESTAMP, points_earned INTEGER DEFAULT 0,
                  coins_earned INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS game_logs
                 (id INTEGER PRIMARY KEY, username TEXT, game TEXT,
                  bet INTEGER, won INTEGER, points_change INTEGER, timestamp TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS gifts
                 (id INTEGER PRIMARY KEY, sender TEXT, receiver TEXT,
                  gift_type TEXT, coins INTEGER, timestamp TIMESTAMP)''')

    password = hashlib.sha256('BOSS123'.encode()).hexdigest()
    c.execute("INSERT OR REPLACE INTO users (username, password, coins, points, is_owner, bio, profile_pic) VALUES (?,?,?,?,?,?,?)",
              ('BOSS', password, 5000, 500, 1, 'PK Battle Owner 👑 LIVE', 'https://i.imgur.com/8Km9tLL.png'))
    conn.commit()
    conn.close()
    print("🔥 PK BATTLE V9.0 VIDEO - Database ready ✅")

def get_user_data(username):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=?", (username,))
    user = c.fetchone()
    conn.close()
    if user:
        return {'id': user[0], 'username': user[1], 'password': user[2], 'coins': user[3],
                'points': user[4], 'last_free': user[5], 'last_spin': user[6], 'last_flip': user[7],
                'last_box': user[8], 'last_guess': user[9], 'is_owner': user[10],
                'profile_pic': user[11], 'bio': user[12], 'followers': user[13], 'following': user[14],
                'total_gifts': user[15]}
    return None

def check_cooldown(last_time_str, hours=1):
    if not last_time_str: return True
    last_time = datetime.fromisoformat(last_time_str)
    return datetime.now() - last_time >= timedelta(hours=hours)

def log_game(username, game, bet, won, points_change):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("INSERT INTO game_logs (username, game, bet, won, points_change, timestamp) VALUES (?,?,?,?,?,?)",
              (username, game, bet, won, points_change, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def party_timer(room_id):
    time.sleep(10800)
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
        socketio.emit('party_ended', {'room_id': room_id, 'msg': '🎉 Party 3 Hours zo! +1000 Points!'}, room=room_id)
        del party_rooms[room_id]

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    online_users[request.sid] = None
    emit('online_update', {'count': len(online_users)}, broadcast=True)
    rooms_data = [{'room_id': k, 'name': v['name'], 'owner': v['owner'], 'users': len(v['users']), 'max': v['max_users'], 'crown_taken': v['crown_seat'] is not None} for k,v in party_rooms.items()]
    emit('party_rooms_list', rooms_data)
    live_list = [{'username': u, 'viewers': live_streamers[u]['viewers']} for u in live_streamers]
    emit('live_streamers_list', live_list)

@socketio.on('disconnect')
def handle_disconnect():
    username = online_users.get(request.sid)
    if username:
        if username in live_streamers:
            del live_streamers[username]
            socketio.emit('live_update', {'username': username, 'status': 'offline'}, broadcast=True)
        for room_id, room in list(party_rooms.items()):
            if username in room['users']:
                room['users'].remove(username)
                if username == room['crown_seat']: room['crown_seat'] = None
                socketio.emit('party_update', {'room_id': room_id, 'users': room['users'], 'crown_seat': room['crown_seat']}, room=room_id)
    if request.sid in online_users: del online_users[request.sid]
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
                'session_id': session_id, 'username': user['username'], 'coins': user['coins'],
                'is_owner': bool(user['is_owner']),
                'profile': {'profile_pic': user['profile_pic'], 'bio': user['bio'],
                           'followers': user['followers'], 'following': user['following'],
                           'points': user['points'], 'total_gifts': user['total_gifts']}
            })

@socketio.on('signup')
def handle_signup(data):
    username = data.get('username', '').strip()
    password = data.get('password', '')
    if not username or not password or len(username) < 3 or len(password) < 4:
        emit('auth_error', {'msg': 'Username 3+ chars, Password 4+ chars'}); return
    hashed = hashlib.sha256(password.encode()).hexdigest()
    conn = sqlite3.connect('users.db'); c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password, coins, points) VALUES (?,?,?,?)", (username, hashed, 100, 0))
        conn.commit(); user = get_user_data(username)
        session_id = os.urandom(16).hex(); sessions[session_id] = username
        online_users[request.sid] = username
        emit('auth_success', {'session_id': session_id, 'username': user['username'], 'coins': user['coins'],
              'is_owner': False, 'profile': {'profile_pic': user['profile_pic'], 'bio': user['bio'],
              'followers': 0, 'following': 0, 'points': 0, 'total_gifts': 0}})
    except sqlite3.IntegrityError:
        emit('auth_error', {'msg': 'Username hman a ni tawh'})
    conn.close()

@socketio.on('login')
def handle_login(data):
    username = data.get('username', '').strip(); password = data.get('password', '')
    user = get_user_data(username)
    if user:
        hashed_input = hashlib.sha256(password.encode()).hexdigest()
        if user['password'] == hashed_input:
            session_id = os.urandom(16).hex(); sessions[session_id] = username
            online_users[request.sid] = username
            emit('auth_success', {'session_id': session_id, 'username': user['username'], 'coins': user['coins'],
                  'is_owner': bool(user['is_owner']),
                  'profile': {'profile_pic': user['profile_pic'], 'bio': user['bio'],
                             'followers': user['followers'], 'following': user['following'],
                             'points': user['points'], 'total_gifts': user['total_gifts']}})
        else: emit('auth_error', {'msg': 'Password dik lo'})
    else: emit('auth_error', {'msg': 'Username hmuh loh'})

# VIDEO LIVE FEATURES
@socketio.on('go_live')
def handle_go_live(data):
    username = data.get('username')
    if username:
        live_streamers[username] = {'viewers': 0, 'socket_id': request.sid}
        join_room(f"live_{username}")
        emit('live_update', {'username': username, 'status': 'live', 'viewers': 0}, broadcast=True)
        emit('live_started', {'username': username})

@socketio.on('stop_live')
def handle_stop_live(data):
    username = data.get('username')
    if username and username in live_streamers:
        leave_room(f"live_{username}")
        del live_streamers[username]
        emit('live_update', {'username': username, 'status': 'offline'}, broadcast=True)

@socketio.on('join_live')
def handle_join_live(data):
    username = data.get('username')
    streamer = data.get('streamer')
    if streamer in live_streamers:
        join_room(f"live_{streamer}")
        live_streamers[streamer]['viewers'] += 1
        emit('live_viewer_count', {'username': streamer, 'viewers': live_streamers[streamer]['viewers']}, broadcast=True)

@socketio.on('leave_live')
def handle_leave_live(data):
    streamer = data.get('streamer')
    if streamer in live_streamers:
        leave_room(f"live_{streamer}")
        live_streamers[streamer]['viewers'] = max(0, live_streamers[streamer]['viewers'] - 1)
        emit('live_viewer_count', {'username': streamer, 'viewers': live_streamers[streamer]['viewers']}, broadcast=True)

@socketio.on('webrtc_offer')
def handle_webrtc_offer(data):
    emit('webrtc_offer', data, room=f"live_{data['to']}")

@socketio.on('webrtc_answer')
def handle_webrtc_answer(data):
    emit('webrtc_answer', data, room=f"live_{data['to']}")

@socketio.on('webrtc_ice_candidate')
def handle_ice_candidate(data):
    emit('webrtc_ice_candidate', data, room=f"live_{data['to']}")

@socketio.on('send_gift')
def handle_send_gift(data):
    sender = data.get('sender')
    receiver = data.get('receiver')
    gift_type = data.get('gift_type')
    coins = data.get('coins', 0)

    sender_data = get_user_data(sender)
    if not sender_data or sender_data['coins'] < coins:
        emit('gift_error', {'msg': 'Coins i nei tlem!'})
        return

    conn = sqlite3.connect('users.db'); c = conn.cursor()
    c.execute("UPDATE users SET coins = coins -? WHERE username=?", (coins, sender))
    c.execute("UPDATE users SET coins = coins +?, total_gifts = total_gifts +? WHERE username=?", (coins, 1, receiver))
    c.execute("INSERT INTO gifts (sender, receiver, gift_type, coins, timestamp) VALUES (?,?,?,?,?)",
              (sender, receiver, gift_type, coins, datetime.now().isoformat()))
    conn.commit()

    sender_new = get_user_data(sender)
    receiver_new = get_user_data(receiver)
    conn.close()

    emit('gift_sent', {'sender': sender, 'receiver': receiver, 'gift_type': gift_type, 'coins': coins}, room=f"live_{receiver}")
    emit('coins_update', {'coins': sender_new['coins'], 'points': sender_new['points']})

# GAMES + PROFILE + PARTY - V8.1 ang tho
@socketio.on('get_profile')
def handle_get_profile(data):
    username = data.get('username')
    user = get_user_data(username)
    current_user = online_users.get(request.sid)
    if user and current_user:
        conn = sqlite3.connect('users.db'); c = conn.cursor()
        c.execute("SELECT * FROM follows WHERE follower=? AND following=?", (current_user, username))
        is_following = c.fetchone() is not None
        conn.close()
        emit('profile_data', {'username': user['username'], 'profile_pic': user['profile_pic'], 'bio': user['bio'],
              'followers': user['followers'], 'following': user['following'], 'coins': user['coins'],
              'points': user['points'], 'total_gifts': user['total_gifts'],
              'is_following': is_following, 'is_self': current_user == username})

@socketio.on('toggle_follow')
def handle_toggle_follow(data):
    follower = online_users.get(request.sid)
    following = data.get('target')
    if not follower or not following or follower == following: return
    conn = sqlite3.connect('users.db'); c = conn.cursor()
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
    conn.commit(); conn.close()
    handle_get_profile({'username': following})

@socketio.on('update_profile')
def handle_update_profile(data):
    username = online_users.get(request.sid)
    if not username: return
    bio = data.get('bio', '')[:100]; profile_pic = data.get('profile_pic', '')
    conn = sqlite3.connect('users.db'); c = conn.cursor()
    c.execute("UPDATE users SET bio=?, profile_pic=? WHERE username=?", (bio, profile_pic, username))
    conn.commit(); conn.close()
    emit('profile_updated', {'msg': 'Profile update success!'})
    handle_get_profile({'username': username})

@socketio.on('send_chat')
def handle_chat(data):
    emit('chat_message', {
        'username': data['username'], 'msg': data['msg'][:200],
        'profile_pic': data.get('profile_pic', 'https://i.imgur.com/8Km9tLL.png')
    }, broadcast=True)

@socketio.on('vote')
def handle_vote(data):
    side = data.get('side'); username = data.get('username')
    if side in battle_votes and username:
        user = get_user_data(username)
        if user and user['coins'] >= 10:
            battle_votes += 1
            conn = sqlite3.connect('users.db'); c = conn.cursor()
            c.execute("UPDATE users SET coins = coins - 10, points = points + 5 WHERE username=?", (username,))
            conn.commit(); conn.close()
            emit('vote_update', battle_votes, broadcast=True)
            user_new = get_user_data(username)
            emit('coins_update', {'coins': user_new['coins'], 'points': user_new['points']})
        else:
            emit('game_result', {'success': False, 'game': 'vote', 'msg': 'Coins i nei tlem! 10 Coins a ngai'})

@socketio.on('get_free_coins')
def handle_get_free_coins(data):
    username = data.get('username')
    if not username: return
    conn = sqlite3.connect('users.db'); c = conn.cursor()
    c.execute("SELECT last_free FROM users WHERE username=?", (username,)); result = c.fetchone()
    can_claim = True
    if result and result[0]:
        if datetime.now() - datetime.fromisoformat(result[0]) < timedelta(hours=24): can_claim = False
    if can_claim:
        c.execute("UPDATE users SET coins = coins + 500, last_free =? WHERE username=?", (datetime.now().isoformat(), username))
        conn.commit(); user = get_user_data(username)
        emit('coins_update', {'coins': user['coins'], 'points': user['points']})
        emit('game_result', {'success': True, 'game': 'free', 'msg': '🎁 500 Free Coins i hmu!'})
    else: emit('game_result', {'success': False, 'game': 'free', 'msg': '24 hours nghak rawh'})
    conn.close()

@socketio.on('spin_wheel')
def handle_spin_wheel(data):
    username = data.get('username')
    if not username: return
    user = get_user_data(username)
    if not user or user['coins'] < 20:
        emit('game_result', {'success': False, 'game': 'spin', 'msg': 'Coins i nei tlem! 20 Coins a ngai'}); return
    if not check_cooldown(user['last_spin'], 1):
        emit('game_result', {'success': False, 'game': 'spin', 'msg': 'Cooldown! 1 hour nghak rawh'}); return
    rewards = [{'points': 5, 'chance': 40, 'msg': '🎁 5 Points!'},{'points': 10, 'chance': 30, 'msg': '🎁 10 Points!'},{'points': 25, 'chance': 15, 'msg': '🎉 25 Points!'},{'points': 50, 'chance': 10, 'msg': '💎 50 Points JACKPOT!'},{'points': 100, 'chance': 5, 'msg': '👑 100 POINTS MEGA WIN!'}]
    rand = random.randint(1, 100); cumulative = 0; won = rewards[0]
    for reward in rewards:
        cumulative += reward['chance']
        if rand <= cumulative: won = reward; break
    conn = sqlite3.connect('users.db'); c = conn.cursor()
    c.execute("UPDATE users SET coins = coins - 20, points = points +?, last_spin =? WHERE username=?", (won['points'], datetime.now().isoformat(), username))
    conn.commit(); user = get_user_data(username); conn.close()
    log_game(username, 'spin', 20, won['points'], won['points'])
    emit('game_result', {'success': True, 'game': 'spin', 'msg': won['msg'], 'points_won': won['points'], 'new_coins': user['coins'], 'new_points': user['points']})

@socketio.on('coin_flip')
def handle_coin_flip(data):
    username = data.get('username'); choice = data.get('choice')
    if not username: return
    user = get_user_data(username)
    if not user or user['coins'] < 10:
        emit('game_result', {'success': False, 'game': 'flip', 'msg': 'Coins i nei tlem! 10 Coins a ngai'}); return
    result = random.choice(['heads', 'tails']); won = result == choice
    coins_change = 10 if won else -10; points_change = 20 if won else 0
    conn = sqlite3.connect('users.db'); c = conn.cursor()
    c.execute("UPDATE users SET coins = coins +?, points = points +?, last_flip =? WHERE username=?", (coins_change, points_change, datetime.now().isoformat(), username))
    conn.commit(); user = get_user_data(username); conn.close()
    log_game(username, 'flip', 10, coins_change, points_change)
    msg = f'🎉 WIN! {result.upper()} - +20 Points +10 Coins!' if won else f'😢 LOSE! {result.upper()} -10 Coins'
    emit('game_result', {'success': True, 'game': 'flip', 'won': won, 'result': result, 'msg': msg, 'new_coins': user['coins'], 'new_points': user['points']})

@socketio.on('lucky_box')
def handle_lucky_box(data):
    username = data.get('username')
    if not username: return
    user = get_user_data(username)
    if not user or user['coins'] < 30:
        emit('game_result', {'success': False, 'game': 'box', 'msg': 'Coins i nei tlem! 30 Coins a ngai'}); return
    if not check_cooldown(user['last_box'], 2):
        emit('game_result', {'success': False, 'game': 'box', 'msg': 'Cooldown! 2 hours nghak rawh'}); return
    boxes = [{'points': 10, 'chance': 35, 'msg': '📦 Common Box - 10 Points'},{'points': 30, 'chance': 30, 'msg': '🎁 Rare Box - 30 Points!'},{'points': 60, 'chance': 20, 'msg': '💎 Epic Box - 60 Points!!'},{'points': 100, 'chance': 10, 'msg': '👑 Legendary Box - 100 Points!!!'},{'points': 150, 'chance': 5, 'msg': '🌟 MYTHIC BOX - 150 POINTS!!!!'}]
    rand = random.randint(1, 100); cumulative = 0; won = boxes[0]
    for box in boxes:
        cumulative += box['chance']
        if rand <= cumulative: won = box; break
    conn = sqlite3.connect('users.db'); c = conn.cursor()
    c.execute("UPDATE users SET coins = coins - 30, points = points +?, last_box =? WHERE username=?", (won['points'], datetime.now().isoformat(), username))
    conn.commit(); user = get_user_data(username); conn.close()
    log_game(username, 'box', 30, won['points'], won['points'])
    emit('game_result', {'success': True, 'game': 'box', 'msg': won['msg'], 'points_won': won['points'], 'new_coins': user['coins'], 'new_points': user['points']})

@socketio.on('number_guess')
def handle_number_guess(data):
    username = data.get('username'); guess = data.get('guess')
    if not username or guess is None: return
    user = get_user_data(username)
    if not user or user['coins'] < 15:
        emit('game_result', {'success': False, 'game': 'guess', 'msg': 'Coins i nei tlem! 15 Coins a ngai'}); return
    correct = random.randint(1, 10); won = int(guess) == correct
    coins_change = 35 if won else -15; points_change = 50 if won else 0
    conn = sqlite3.connect('users.db'); c = conn.cursor()
    c.execute("UPDATE users SET coins = coins +?, points = points +?, last_guess =? WHERE username=?", (coins_change, points_change, datetime.now().isoformat(), username))
    conn.commit(); user = get_user_data(username); conn.close()
    log_game(username, 'guess', 15, coins_change, points_change)
    msg = f'🎯 CORRECT! Number {correct} - +50 Points +35 Coins!' if won else f'❌ WRONG! Correct: {correct} -15 Coins'
    emit('game_result', {'success': True, 'game': 'guess', 'won': won, 'correct': correct, 'msg': msg, 'new_coins': user['coins'], 'new_points': user['points']})

@socketio.on('create_party')
def handle_create_party(data):
    username = data.get('username'); room_name = data.get('room_name', f'{username} Party').strip()
    if not username: return
    room_id = f"party_{username}_{int(time.time())}"
    party_rooms[room_id] = {'owner': username, 'name': room_name, 'users': [username], 'crown_seat': None, 'start_time': datetime.now(), 'max_users': 15}
    join_room(room_id)
    emit('party_created', {'room_id': room_id, 'room_name': room_name, 'users': [username], 'crown_seat': None})
    rooms_data = [{'room_id': k, 'name': v['name'], 'owner': v['owner'], 'users': len(v['users']), 'max': v['max_users'], 'crown_taken': v['crown_seat'] is not None} for k,v in party_rooms.items()]
    emit('party_rooms_list', rooms_data, broadcast=True)
    threading.Thread(target=party_timer, args=(room_id,), daemon=True).start()

@socketio.on('join_party')
def handle_join_party(data):
    username = data.get('username'); room_id = data.get('room_id')
    if not username or room_id not in party_rooms: return
    room = party_rooms[room_id]
    if len(room['users']) >= room['max_users']:
        emit('party_error', {'msg': 'Party Room a full! 15 users max'}); return
    if username not in room['users']:
        room['users'].append(username)
        join_room(room_id)
        socketio.emit('party_update', {'room_id': room_id, 'users': room['users'], 'crown_seat': room['crown_seat']}, room=room_id)

@socketio.on('leave_party')
def handle_leave_party(data):
    username = data.get('username'); room_id = data.get('room_id')
    if not username or room_id not in party_rooms: return
    room = party_rooms[room_id]
    if username in room['users']:
        room['users'].remove(username)
        if username == room['crown_seat']: room['crown_seat'] = None
        leave_room(room_id)
        socketio.emit('party_update', {'room_id': room_id, 'users': room['users'], 'crown_seat': room['crown_seat']}, room=room_id)

@socketio.on('sit_crown_seat')
def handle_sit_crown_seat(data):
    username = data.get('username'); room_id = data.get('room_id')
    if not username or room_id not in party_rooms: return
    room = party_rooms[room_id]
    if room['crown_seat'] is not None:
        emit('party_error', {'msg': 'Crown Seat a hman a ni tawh!'}); return
    if username not in room['users']:
        emit('party_error', {'msg': 'Party ah lut phawt rawh!'}); return
    room['crown_seat'] = username
    conn = sqlite3.connect('users.db'); c = conn.cursor()
    c.execute("UPDATE users SET coins = coins + 500 WHERE username=?", (username,))
    conn.commit(); user = get_user_data(username); conn.close()
    socketio.emit('party_update', {'room_id': room_id, 'users': room['users'], 'crown_seat': room['crown_seat']}, room=room_id)
    emit('coins_update', {'coins': user['coins'], 'points': user['points']})
    emit('party_notification', {'msg': f'👑 {username} Crown Seat ah a thu! +500 Coins!'}, room=room_id)

@socketio.on('get_party_rooms')
def handle_get_party_rooms():
    rooms_data = [{'room_id': k, 'name': v['name'], 'owner': v['owner'], 'users': len(v['users']), 'max': v['max_users'], 'crown_taken': v['crown_seat'] is not None} for k,v in party_rooms.items()]
    emit('party_rooms_list', rooms_data)

@socketio.on('get_leaderboard')
def handle_get_leaderboard(data):
    conn = sqlite3.connect('users.db'); c = conn.cursor()
    c.execute("SELECT username, points, coins, profile_pic FROM users ORDER BY points DESC LIMIT 10")
    top_points = c.fetchall()
    c.execute("SELECT username, coins, points, profile_pic FROM users ORDER BY coins DESC LIMIT 10")
    top_coins = c.fetchall()
    conn.close()
    emit('leaderboard_data', {'top_points': top_points, 'top_coins': top_coins})

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
    from flask import Flask, render_template, request, jsonify, session, redirect
from flask_socketio import SocketIO, emit, join_room
import sqlite3, hashlib, secrets, time

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)
socketio = SocketIO(app, cors_allowed_origins="*")

def init_db():
    conn = sqlite3.connect('battle.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY,
                  username TEXT UNIQUE,
                  password TEXT,
                  email TEXT,
                  phone TEXT,
                  dob TEXT,
                  gender TEXT,
                  security_q TEXT,
                  security_a TEXT,
                  score INTEGER DEFAULT 0,
                  created_at INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS reset_tokens
                 (id INTEGER PRIMARY KEY, username TEXT, token TEXT, expires INTEGER)''')
    conn.commit()
    conn.close()

init_db()
active_users = {}

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/signup', methods=['POST'])
def signup():
    data = request.json
    username = data['username']
    password = hashlib.sha256(data['password'].encode()).hexdigest()
    email = data.get('email', '')
    phone = data.get('phone', '')
    dob = data.get('dob', '')
    gender = data.get('gender', '')
    sec_q = data.get('security_q', '')
    sec_a = data.get('security_a', '')

    if not username or not password:
        return jsonify({"success": False, "msg": "Username leh Password a ngai!"})

    conn = sqlite3.connect('battle.db')
    c = conn.cursor()
    try:
        c.execute("""INSERT INTO users
                     (username, password, email, phone, dob, gender, security_q, security_a, created_at)
                     VALUES (?,?,?,?,?,?,?,?,?)""",
                  (username, password, email, phone, dob, gender, sec_q, sec_a, int(time.time())))
        conn.commit()
        return jsonify({"success": True, "msg": "Account siam fel! Login rawh."})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "msg": "Username hman sa a ni!"})
    finally:
        conn.close()

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data['username']
    password = hashlib.sha256(data['password'].encode()).hexdigest()

    conn = sqlite3.connect('battle.db')
    c = conn.cursor()
    c.execute("SELECT username, email, phone, dob, gender FROM users WHERE username=? AND password=?", (username, password))
    user = c.fetchone()
    conn.close()

    if user:
        session['user'] = username
        return jsonify({
            "success": True,
            "username": user[0],
            "email": user[1],
            "phone": user[2],
            "dob": user[3],
            "gender": user[4]
        })
    return jsonify({"success": False, "msg": "Username/Password dik lo!"})

@app.route('/oauth/google')
def google_login():
    demo_user = f"google_{secrets.token_hex(4)}"
    session['user'] = demo_user
    return redirect(f'/?oauth=google&user={demo_user}')

@app.route('/oauth/facebook')
def facebook_login():
    demo_user = f"fb_{secrets.token_hex(4)}"
    session['user'] = demo_user
    return redirect(f'/?oauth=facebook&user={demo_user}')

@app.route('/reset_request', methods=['POST'])
def reset_request():
    data = request.json
    username = data['username']
    conn = sqlite3.connect('battle.db')
    c = conn.cursor()
    c.execute("SELECT security_q FROM users WHERE username=?", (username,))
    result = c.fetchone()
    conn.close()
    if result:
        return jsonify({"success": True, "security_q": result[0]})
    return jsonify({"success": False, "msg": "User hmuh loh!"})

@app.route('/reset_password', methods=['POST'])
def reset_password():
    data = request.json
    username = data['username']
    answer = data['answer']
    new_pass = hashlib.sha256(data['new_password'].encode()).hexdigest()

    conn = sqlite3.connect('battle.db')
    c = conn.cursor()
    c.execute("SELECT security_a FROM users WHERE username=?", (username,))
    result = c.fetchone()

    if result and result[0] == answer:
        c.execute("UPDATE users SET password=? WHERE username=?", (new_pass, username))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "msg": "Password thlak fel!"})
    conn.close()
    return jsonify({"success": False, "msg": "Chhanna dik lo!"})

if __name__ == '__main__':
    print("* PK BATTLE V9.0 FULL PROFILE - Database ready ✅")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)
