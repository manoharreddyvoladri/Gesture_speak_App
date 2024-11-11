from flask import Flask, render_template, request, redirect, url_for, flash
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_login import login_required, current_user
from datetime import datetime, timedelta
import secrets
import logging
from typing import Dict, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RoomManager:
    def __init__(self):
        self.active_rooms: Dict[str, dict] = {}
        self.user_rooms: Dict[str, str] = {}  # sid -> room_id
        self.max_rooms = 100
        self.max_participants = 5
        self.room_timeout = timedelta(hours=24)

    def create_room(self, room_id: str) -> bool:
        if len(self.active_rooms) >= self.max_rooms:
            return False
            
        if room_id not in self.active_rooms:
            self.active_rooms[room_id] = {
                'participants': {},  # username -> {sid, joined_at}
                'created_at': datetime.now(),
                'settings': {
                    'max_participants': self.max_participants,
                    'enable_predictions': True
                }
            }
        return True

    def can_join_room(self, room_id: str, username: str) -> tuple[bool, Optional[str]]:
        if room_id not in self.active_rooms:
            return False, "Room does not exist"
            
        room = self.active_rooms[room_id]
        
        if len(room['participants']) >= self.max_participants:
            return False, "Room is full"
            
        if username in room['participants']:
            return False, "Already in this room"
            
        if self._is_room_expired(room):
            self._cleanup_room(room_id)
            return False, "Room has expired"
            
        return True, None

    def add_participant(self, room_id: str, username: str, sid: str) -> None:
        self.active_rooms[room_id]['participants'][username] = {
            'sid': sid,
            'joined_at': datetime.now()
        }
        self.user_rooms[sid] = room_id

    def remove_participant(self, room_id: str, username: str) -> None:
        if room_id in self.active_rooms:
            participant = self.active_rooms[room_id]['participants'].pop(username, None)
            if participant:
                self.user_rooms.pop(participant['sid'], None)

    def get_participant_count(self, room_id: str) -> int:
        return len(self.active_rooms.get(room_id, {}).get('participants', {}))

    def get_participant_list(self, room_id: str) -> list:
        return list(self.active_rooms.get(room_id, {}).get('participants', {}).keys())

    def get_participant_sid(self, room_id: str, username: str) -> Optional[str]:
        participant = self.active_rooms.get(room_id, {}).get('participants', {}).get(username)
        return participant['sid'] if participant else None

    def _is_room_expired(self, room: dict) -> bool:
        return datetime.now() - room['created_at'] > self.room_timeout

    def _cleanup_room(self, room_id: str) -> None:
        if room_id in self.active_rooms:
            for participant in self.active_rooms[room_id]['participants'].values():
                self.user_rooms.pop(participant['sid'], None)
            del self.active_rooms[room_id]

    def cleanup_empty_rooms(self) -> None:
        current_time = datetime.now()
        rooms_to_cleanup = [
            room_id for room_id, room in self.active_rooms.items()
            if len(room['participants']) == 0 or current_time - room['created_at'] > self.room_timeout
        ]
        for room_id in rooms_to_cleanup:
            self._cleanup_room(room_id)

def init_video_call(app: Flask) -> SocketIO:
    socketio = SocketIO(app, cors_allowed_origins="*", ping_timeout=60)
    room_manager = RoomManager()

    @socketio.on('connect')
    def handle_connect():
        logger.info(f"Client connected: {request.sid}")

    @socketio.on('disconnect')
    def handle_disconnect():
        try:
            room_id = room_manager.user_rooms.get(request.sid)
            if room_id:
                for username, participant in room_manager.active_rooms[room_id]['participants'].items():
                    if participant['sid'] == request.sid:
                        room_manager.remove_participant(room_id, username)
                        emit('user_left', {
                            'username': username,
                            'participant_count': room_manager.get_participant_count(room_id)
                        }, room=room_id)
                        break
                
                room_manager.cleanup_empty_rooms()
                
        except Exception as e:
            logger.error(f"Error in handle_disconnect: {e}")

    @socketio.on('join')
    def handle_join(data):
        try:
            username = data['username']
            room_id = data['room']
            
            can_join, error = room_manager.can_join_room(room_id, username)
            if not can_join:
                emit('error', {'message': error})
                return
            
            join_room(room_id)
            room_manager.add_participant(room_id, username, request.sid)
            
            emit('user_joined', {
                'username': username,
                'participant_count': room_manager.get_participant_count(room_id)
            }, room=room_id)
            
            emit('room_participants', {
                'participants': room_manager.get_participant_list(room_id)
            })
            
            logger.info(f"User {username} joined room {room_id}")
            
        except Exception as e:
            logger.error(f"Error in handle_join: {e}")
            emit('error', {'message': 'Failed to join room'})

    @socketio.on('offer')
    def handle_offer(data):
        try:
            target_username = data['target']
            room_id = data['room']
            target_sid = room_manager.get_participant_sid(room_id, target_username)
            
            if target_sid:
                emit('offer', {
                    'sdp': data['sdp'],
                    'username': data['username']
                }, room=target_sid)
                
        except Exception as e:
            logger.error(f"Error in handle_offer: {e}")

    @socketio.on('answer')
    def handle_answer(data):
        try:
            target_username = data['target']
            room_id = data['room']
            target_sid = room_manager.get_participant_sid(room_id, target_username)
            
            if target_sid:
                emit('answer', {
                    'sdp': data['sdp'],
                    'username': data['username']
                }, room=target_sid)
                
        except Exception as e:
            logger.error(f"Error in handle_answer: {e}")

    @socketio.on('ice_candidate')
    def handle_ice_candidate(data):
        try:
            target_username = data['target']
            room_id = data['room']
            target_sid = room_manager.get_participant_sid(room_id, target_username)
            
            if target_sid:
                emit('ice_candidate', {
                    'candidate': data['candidate'],
                    'username': data['username']
                }, room=target_sid)
                
        except Exception as e:
            logger.error(f"Error in handle_ice_candidate: {e}")

    @socketio.on('sign_prediction')
    def handle_sign_prediction(data):
        try:
            room_id = data['room']
            if room_id in room_manager.active_rooms:
                emit('sign_prediction', {
                    'username': data['username'],
                    'prediction': data['prediction']
                }, room=room_id)
                
        except Exception as e:
            logger.error(f"Error in handle_sign_prediction: {e}")

    return socketio