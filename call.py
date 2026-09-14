from flask import request
from flask_socketio import emit, join_room, leave_room
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def init_video_call(app, socketio):
    """Wire video-call signaling (WebRTC offer/answer/ICE), chat, and the
    host-approval join flow onto an existing SocketIO instance.

    Takes the app's already-configured `socketio` instance rather than
    creating a new one, so these handlers (and the app's own CORS/logging
    config) actually run on the socket connections clients use.

    Returns (socketio, consume_approved_sid) - the latter lets app.py's
    /room/<id>/confirm route check and consume a host's approval decision.
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
            # Drop this sid from any room's pending-approval queue - no
            # point leaving a stale entry for someone who already left.
            for room in active_rooms.values():
                room.get('pending', {}).pop(request.sid, None)

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
                elif active_rooms[room_id].get('host_sid') == request.sid:
                    active_rooms[room_id]['host_sid'] = None

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
                    'created_at': datetime.now(),
                    'pending': {},
                    'host_sid': None,
                    'approved_sids': set()
                }

            active_rooms[room_id]['participants'][username] = {
                'sid': request.sid,
                'joined_at': datetime.now()
            }
            user_rooms[request.sid] = room_id

            if data.get('is_host'):
                active_rooms[room_id]['host_sid'] = request.sid

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

    @socketio.on('join_request')
    def handle_join_request(data):
        """A visitor on the lobby page is asking the host to let them in."""
        try:
            room_id = data['room']
            name = str(data.get('name', '')).strip()[:50] or 'Guest'

            room = active_rooms.setdefault(room_id, {
                'participants': {},
                'created_at': datetime.now(),
                'pending': {},
                'host_sid': None,
                'approved_sids': set()
            })
            room['pending'][request.sid] = {'name': name}

            host_sid = room.get('host_sid')
            if host_sid:
                emit('join_request', {'sid': request.sid, 'name': name}, room=host_sid)
            # If no host is connected yet, the requester just keeps waiting -
            # they'll be notified once the host shows up and responds.
        except Exception as e:
            logger.error(f'Join request error: {str(e)}')

    @socketio.on('respond_to_request')
    def handle_respond_to_request(data):
        """Host approving/rejecting/holding a pending join request."""
        try:
            room_id = data['room']
            target_sid = data['sid']
            action = data.get('action')

            room = active_rooms.get(room_id)
            if not room:
                return
            # Only the room's tracked host can act on requests for it.
            if room.get('host_sid') != request.sid:
                return
            if target_sid not in room.get('pending', {}):
                return

            if action == 'approve':
                room['pending'].pop(target_sid, None)
                # Recorded here, consumed by the Flask /room/<id>/confirm
                # route - a plain HTTP POST, not another socket message,
                # because Flask-SocketIO can't write a Set-Cookie back to
                # the browser over an established WebSocket connection, only
                # over HTTP long-polling (which this app's client disables).
                room.setdefault('approved_sids', set()).add(target_sid)
                emit('join_response', {'status': 'approved'}, room=target_sid)
            elif action == 'reject':
                room['pending'].pop(target_sid, None)
                emit('join_response', {'status': 'rejected'}, room=target_sid)
            elif action == 'hold':
                emit('join_response', {'status': 'held'}, room=target_sid)
        except Exception as e:
            logger.error(f'Respond to request error: {str(e)}')

    def consume_approved_sid(room_id, sid):
        """Called from the Flask /room/<id>/confirm route (a real HTTP
        request, so it can actually set the session cookie). Returns True
        exactly once per approval - single-use, so replaying the same sid
        doesn't grant repeated access."""
        room = active_rooms.get(room_id)
        if not room:
            return False
        approved = room.get('approved_sids')
        if approved and sid in approved:
            approved.discard(sid)
            return True
        return False

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

    return socketio, consume_approved_sid
