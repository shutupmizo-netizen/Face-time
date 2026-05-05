from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import sqlite3, os, hashlib, time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'pk-battle-pro-2026-mizo'
socketio = SocketIO(app, cors_allowed_origins="*")

battle_votes = 0
live_streamers = {}
online_users = 0
active_pk = None

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
                  is_owner INTEGER DEFAULT 0,
                  profile_pic TEXT DEFAULT 'https://i.imgur.com/8Km9tLL.png',
                  bio TEXT DEFAULT 'PK Battle Player 🎤',
                  followers INTEGER DEFAULT 0,
                  following INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS follows
                 (id INTEGER PRIMARY KEY,
                  follower TEXT,
                  following TEXT,
                  UNIQUE(follower, following))''')
    try:
        c.execute("UPDATE users SET is_owner=1 WHERE username='admin'")
    except:
        pass
    conn.commit()
    conn.close()

init_db()

def get_user_data(username):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT username, coins, points, is_owner, profile_pic, bio, followers, following FROM users WHERE username=?", (username,))
    user = c.fetchone()
    conn.close()
    if user:
        return {
            'username': user[0], 'coins': user[1], 'points': user[2], 'is_owner': user[3],
            'profile_pic': user[4], 'bio': user[5], 'followers': user[6], 'following': user[7]
        }
    return None

def check_following(follower, following):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT id FROM follows WHERE follower=? AND following=?", (follower, following))
    result = c.fetchone()
    conn.close()
    return result is not None

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    global online_users
    online_users += 1
    emit('online_count', online_users, broadcast=True)
    emit('update_live_streamers', list(live_streamers.values()))

@socketio.on('disconnect')
def handle_disconnect():
    global online_users
    online_users = max(0, online_users - 1)
    emit('online_count', online_users, broadcast=True)

@socketio.on('signup')
def handle_signup(data):
    username = data['username'].strip()
    password = data['password']
    hashed = hashlib.sha256(password.encode()).hexdigest()

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    try:
        c.execute("INSERT INTO users (username, password) VALUES (?,?)", (username, hashed))
        conn.commit()
        session_id = f"{username}_{int(time.time())}"
        emit('auth_success', {'session_id': session_id, 'username': username, 'coins': 0, 'points': 0, 'is_owner': False})
    except:
        emit('error', {'msg': 'Username already exists'})
    conn.close()

@socketio.on('login')
def handle_login(data):
    username = data['username'].strip()
    password = data['password']
    hashed = hashlib.sha256(password.encode()).hexdigest()

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, hashed))
    user = c.fetchone()
    conn.close()

    if user:
        session_id = f"{username}_{int(time.time())}"
        user_data = get_user_data(username)
        emit('auth_success', {
            'session_id': session_id,
            'username': username,
            'coins': user_data['coins'],
            'points': user_data['points'],
            'is_owner': bool(user_data['is_owner'])
        })
    else:
        emit('error', {'msg': 'Invalid login'})

@socketio.on('verify_session')
def handle_verify(data):
    session_id = data['session_id']
    username = session_id.split('_')[0]
    user_data = get_user_data(username)
    if user_data:
        emit('auth_success', {
            'session_id': session_id,
            'username': username,
            'coins': user_data['coins'],
            'points': user_data['points'],
            'is_owner': bool(user_data['is_owner'])
        })

@socketio.on('get_profile')
def handle_get_profile(data):
    viewer = data['session_id'].split('_')[0]
    target = data['username']
    user_data = get_user_data(target)
    if user_data:
        user_data['is_following'] = check_following(viewer, target)
        user_data['is_self'] = viewer == target
        emit('profile_data', user_data)

@socketio.on('update_profile')
def handle_update_profile(data):
    username = data['session_id'].split('_')[0]
    bio = data['bio'][:100]
    pic = data['pic']

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("UPDATE users SET bio=?, profile_pic=? WHERE username=?", (bio, pic, username))
    conn.commit()
    conn.close()

    user_data = get_user_data(username)
    emit('profile_updated', user_data)
    emit('success', {'msg': '✅ Profile updated!'})

@socketio.on('toggle_follow')
def handle_toggle_follow(data):
    follower = data['session_id'].split('_')[0]
    following = data['target']

    if follower == following:
        return

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT id FROM follows WHERE follower=? AND following=?", (follower, following))
    exists = c.fetchone()

    if exists:
        c.execute("DELETE FROM follows WHERE follower=? AND following=?", (follower, following))
        c.execute("UPDATE users SET followers=followers-1 WHERE username=?", (following,))
        c.execute("UPDATE users SET following=following-1 WHERE username=?", (follower,))
        is_following = False
    else:
        c.execute("INSERT INTO follows (follower, following) VALUES (?,?)", (follower, following))
        c.execute("UPDATE users SET followers=followers+1 WHERE username=?", (following,))
        c.execute("UPDATE users SET following=following+1 WHERE username=?", (follower,))
        is_following = True

    conn.commit()
    conn.close()

    user_data = get_user_data(following)
    user_data['is_following'] = is_following
    user_data['is_self'] = False
    emit('profile_data', user_data)

@socketio.on('start_stream')
def handle_start_stream(data):
    username = data['session_id'].split('_')[0]
    user_data = get_user_data(username)
    if user_data:
        live_streamers[username] = {
            'username': username,
            'profile_pic': user_data['profile_pic'],
            'bio': user_data['bio']
        }
        emit('update_live_streamers', list(live_streamers.values()), broadcast=True)

@socketio.on('stop_stream')
def handle_stop_stream(data):
    username = data['session_id'].split('_')[0]
    if username in live_streamers:
        del live_streamers[username]
    emit('update_live_streamers', list(live_streamers.values()), broadcast=True)

@socketio.on('vote')
def handle_vote(data):
    global battle_votes
    username = data['session_id'].split('_')[0]
    team = data['team']
    target_streamer = data.get('target')

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT coins FROM users WHERE username=?", (username,))
    result = c.fetchone()

    if result and result[0] >= 10:
        new_coins = result[0] - 10
        c.execute("UPDATE users SET coins=? WHERE username=?", (new_coins, username))

        if target_streamer and target_streamer in live_streamers:
            c.execute("UPDATE users SET points=points+5 WHERE username=?", (target_streamer,))

        conn.commit()
        battle_votes += 1
        emit('update_coins', {'coins': new_coins})
        emit('update_votes', battle_votes, broadcast=True)

        if target_streamer:
            target_data = get_user_data(target_streamer)
            if target_data:
                emit('points_update', {'username': target_streamer, 'points': target_data['points']}, broadcast=True)
    else:
        emit('error', {'msg': 'Not enough Gift Coins!'})
    conn.close()

@socketio.on('get_free_coins')
def handle_free_coins(data):
    username = data['session_id'].split('_')[0]
    now = time.time()

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT last_free FROM users WHERE username=?", (username,))
    result = c.fetchone()

    if not result[0] or (now - result[0]) > 300:
        c.execute("UPDATE users SET coins=coins+500, last_free=? WHERE username=?", (now, username))
        conn.commit()
        c.execute("SELECT coins FROM users WHERE username=?", (username,))
        new_coins = c.fetchone()[0]
        emit('update_coins', {'coins': new_coins})
        emit('success', {'msg': '✅ +500 Gift Coins!'})
    else:
        wait = int(300 - (now - result[0]))
        emit('error', {'msg': f'Wait {wait}s'})
    conn.close()

@socketio.on('redeem_points')
def handle_redeem_points(data):
    username = data['session_id'].split('_')[0]
    points_to_redeem = data['points']

    if points_to_redeem < 100:
        emit('error', {'msg': '100 Points tal a ngai. 100 Points = 60 Coins'})
        return

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT points, coins FROM users WHERE username=?", (username,))
    result = c.fetchone()

    if result and result[0] >= points_to_redeem:
        coins_to_add = (points_to_redeem // 100) * 60
        new_points = result[0] - (points_to_redeem // 100) * 100
        new_coins = result[1] + coins_to_add

        c.execute("UPDATE users SET points=?, coins=? WHERE username=?", (new_points, new_coins, username))
        conn.commit()

        emit('update_coins', {'coins': new_coins})
        emit('update_points', {'points': new_points})
        emit('success', {'msg': f'✅ {coins_to_add} Coins i redeem e!'})
    else:
        emit('error', {'msg': 'Points i nei tlem lutuk!'})
    conn.close()

@socketio.on('start_pk')
def handle_start_pk(data):
    global active_pk
    challenger = data['session_id'].split('_')[0]
    team = data['team']

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT coins FROM users WHERE username=?", (challenger,))
    result = c.fetchone()

    if not result or result[0] < 20:
        emit('error', {'msg': '❌ PK Fee 20 Coins i nei lo!'})
        conn.close()
        return

    new_coins = result[0] - 20
    c.execute("UPDATE users SET coins=? WHERE username=?", (new_coins, challenger))
    conn.commit()
    conn.close()

    emit('update_coins', {'coins': new_coins})

    if active_pk is None:
        active_pk = {
            'challenger1': challenger,
            'team1': team,
            'challenger2': None,
            'team2': None,
            'votes': {'boss': 0, 'enemy': 0},
            'pot': 20
        }
        emit('pk_waiting', {'msg': f'⚔️ {challenger} in PK a challenge! 20 Coins bet. Opponent nghak mek...'}, broadcast=True)
    elif active_pk['challenger1']!= challenger and active_pk['challenger2'] is None:
        active_pk['challenger2'] = challenger
        active_pk['team2'] = team
        active_pk['pot'] += 20

        emit('pk_start', {
            'msg': f'🔥 PK START! {active_pk["challenger1"]} VS {challenger}',
            'challenger1': active_pk['challenger1'],
            'challenger2': challenger,
            'team1': active_pk['team1'],
            'team2': active_pk['team2'],
            'pot': active_pk['pot']
        }, broadcast=True)
    else:
        emit('error', {'msg': '❌ PK khat a kal mek. Lo nghak rawh!'})

@socketio.on('pk_vote')
def handle_pk_vote(data):
    global active_pk
    voter = data['session_id'].split('_')[0]
    team = data['team']

    if not active_pk or not active_pk['challenger2']:
        emit('error', {'msg': '❌ PK a la in tan lo!'})
        return

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT coins FROM users WHERE username=?", (voter,))
    result = c.fetchone()

    if result and result[0] >= 10:
        new_coins = result[0] - 10
        c.execute("UPDATE users SET coins=? WHERE username=?", (new_coins, voter))
        conn.commit()

        active_pk['votes'] += 1
        active_pk['pot'] += 10

        emit('update_coins', {'coins': new_coins})
        emit('pk_vote_update', {
            'votes': active_pk['votes'],
            'pot': active_pk['pot']
        }, broadcast=True)
    else:
        emit('error', {'msg': '❌ Coins i nei tlem lutuk!'})
    conn.close()

@socketio.on('end_pk')
def handle_end_pk(data):
    global active_pk
    if not active_pk or not active_pk['challenger2']:
        return

    votes = active_pk['votes']
    if votes['boss'] > votes['enemy']:
        winner = active_pk['challenger1'] if active_pk['team1'] == 'boss' else active_pk['challenger2']
    elif votes['enemy'] > votes['boss']:
        winner = active_pk['challenger1'] if active_pk['team1'] == 'enemy' else active_pk['challenger2']
    else:
        emit('pk_result', {'msg': '🤝 DRAW! Coins kir lo. House in a la.', 'winner': None}, broadcast=True)
        active_pk = None
        return

    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("UPDATE users SET coins=coins+35 WHERE username=?", (winner,))
    conn.commit()
    conn.close()

    emit('pk_result', {
        'msg': f'🏆 {winner} WIN! 35 Coins a dawng e!',
        'winner': winner,
        'pot': active_pk['pot']
    }, broadcast=True)

    active_pk = None

@socketio.on('chat_message')
def handle_chat(data):
    username = data['session_id'].split('_')[0]
    message = data['message'][:200]
    user_data = get_user_data(username)

    if user_data:
        emit('new_chat', {
            'username': username,
            'message': message,
            'profile_pic': user_data['profile_pic'],
            'is_owner': user_data['is_owner']
        }, broadcast=True)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
