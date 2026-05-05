@socketio.on('send_chat')
def handle_chat(data):
    session_id = data['session_id']
    if session_id not in sessions_db:
        return

    username = sessions_db[session_id]
    message = data['message'][:200] # 200 char limit

    # Bad words filter
    bad_words = ['chhe', 'dawt', 'hmaw'] # I duh belh rawh
    for word in bad_words:
        if word in message.lower():
            return

    emit('chat_message', {
        'username': username,
        'message': message,
        'is_owner': username == OWNER_USERNAME
    }, broadcast=True)

@socketio.on('get_free_coins')
def give_free_coins(data):
    session_id = data['session_id']
    if session_id not in sessions_db:
        return

    username = sessions_db[session_id]
    if users_db[username].get('free_claimed'):
        return

    users_db[username]['coins'] += 50
    users_db[username]['free_claimed'] = True
    emit('free_coins_success', {'coins': users_db[username]['coins']})
    emit('coins_update', {'coins': users_db[username]['coins']})

@socketio.on('start_stream')
def start_stream(data):
    session_id = data['session_id']
    if session_id not in sessions_db:
        return
    emit('stream_started', {'userId': sessions_db[session_id], 'team': data['team']}, broadcast=True)

@socketio.on('stop_stream')
def stop_stream(data):
    session_id = data['session_id']
    if session_id not in sessions_db:
        return
    emit('stream_stopped', {'userId': sessions_db[session_id]}, broadcast=True)
