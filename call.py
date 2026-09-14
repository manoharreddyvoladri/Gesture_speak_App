from flask import request
from flask_socketio import emit, join_room, leave_room
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def init_video_call(app, socketio):
    """Wire video-call signaling (WebRTC offer/answer/ICE) and chat onto an
    existing SocketIO instance.

    Takes the app's already-configured `socketio` instance rather than
    creating a new one, so these handlers (and the app's own CORS/logging
    config) actually run on the socket connections clients use.
    """

    # Track active users and rooms (in-memory - fine for a single worker
    # process; would need a shared message queue/backend to scale across
    # multiple worker processes).
    active_rooms = {}
    user_rooms = {}

    @socketio.on('connect')
    def handle_connect():
        logger.info(f'Client connected: {request.sid}')
        emit('connection_success', {'sid': request.sid})

    @socketio.on('disconnect')
    def handle_disconnect():
        try:
            room_id = user_rooms.get(request.sid)
            if not room_id or room_id not in active_rooms:
                return

            username = None
            for user, data in active_rooms[room_id]['participants'].items():
                if data['sid'] == request.sid:
                    username = user
                    break

            if username:
                del active_rooms[room_id]['participants'][username]
                user_rooms.pop(request.sid, None)

                participant_count = len(active_rooms.get(room_id, {}).get('participants', {}))

                if not active_rooms[room_id]['participants']:
                    del active_rooms[room_id]

                emit('user_left', {
                    'username': username,
                    'participant_count': participant_count
                }, room=room_id)

                logger.info(f'User {username} disconnected from room {room_id}')
        except Exception as e:
            logger.error(f'Disconnect handling error: {str(e)}')

    @socketio.on('join_room')
    def handle_join_room(data):
        try:
            username = data['username']
            room_id = data['room']

            join_room(room_id)

            if room_id not in active_rooms:
                active_rooms[room_id] = {
                    'participants': {},
                    'created_at': datetime.now()
                }

            active_rooms[room_id]['participants'][username] = {
                'sid': request.sid,
                'joined_at': datetime.now()
            }
            user_rooms[request.sid] = room_id

            participants = list(active_rooms[room_id]['participants'].keys())

            # Notify room about new/rejoined user
            emit('user_joined', {
                'username': username,
                'participant_count': len(participants)
            }, room=room_id)

            # Send participants list + count to the new user
            emit('room_participants', {
                'participants': participants,
                'participant_count': len(participants)
            })

            logger.info(f'User {username} joined room {room_id}')
        except Exception as e:
            logger.error(f'Join room error: {str(e)}')
            emit('error', {'message': 'Failed to join room'})

    @socketio.on('leave_room')
    def handle_leave_room(data):
        try:
            username = data['username']
            room_id = data['room']

            if room_id in active_rooms and username in active_rooms[room_id]['participants']:
                del active_rooms[room_id]['participants'][username]
                user_rooms.pop(request.sid, None)
                leave_room(room_id)

                participant_count = len(active_rooms[room_id]['participants'])
                if not active_rooms[room_id]['participants']:
                    del active_rooms[room_id]

                emit('user_left', {
                    'username': username,
                    'participant_count': participant_count
                }, room=room_id)
        except Exception as e:
            logger.error(f'Leave room error: {str(e)}')

    @socketio.on('offer')
    def handle_offer(data):
        try:
            room_id = data['room']
            target = data['target']
            if room_id in active_rooms and target in active_rooms[room_id]['participants']:
                target_sid = active_rooms[room_id]['participants'][target]['sid']
                emit('offer', {
                    'sdp': data['sdp'],
                    'username': data['username']
                }, room=target_sid)
        except Exception as e:
            logger.error(f'Offer error: {str(e)}')

    @socketio.on('answer')
    def handle_answer(data):
        try:
            room_id = data['room']
            target = data['target']
            if room_id in active_rooms and target in active_rooms[room_id]['participants']:
                target_sid = active_rooms[room_id]['participants'][target]['sid']
                emit('answer', {
                    'sdp': data['sdp'],
                    'username': data['username']
                }, room=target_sid)
        except Exception as e:
            logger.error(f'Answer error: {str(e)}')

    @socketio.on('ice_candidate')
    def handle_ice_candidate(data):
        try:
            room_id = data['room']
            target = data['target']
            if room_id in active_rooms and target in active_rooms[room_id]['participants']:
                target_sid = active_rooms[room_id]['participants'][target]['sid']
                emit('ice_candidate', {
                    'candidate': data['candidate'],
                    'username': data['username']
                }, room=target_sid)
        except Exception as e:
            logger.error(f'ICE candidate error: {str(e)}')

    @socketio.on('chat_message')
    def handle_chat_message(data):
        try:
            room_id = data['room']
            username = data['username']
            message = str(data.get('message', '')).strip()[:500]
            if not message:
                return
            emit('chat_message', {
                'username': username,
                'message': message,
                'timestamp': data.get('timestamp') or datetime.utcnow().isoformat()
            }, room=room_id)
        except Exception as e:
            logger.error(f'Chat message error: {str(e)}')

    return socketio
