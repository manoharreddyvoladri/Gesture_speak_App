from flask import Flask, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import logging
from datetime import datetime
from pymongo import MongoClient
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_video_call(app):
    socketio = SocketIO(app, 
                       cors_allowed_origins="*", 
                       ping_timeout=60,
                       ping_interval=25,
                       async_mode='eventlet')
    
    # Track active users and rooms
    active_rooms = {}
    user_rooms = {}

    @socketio.on('connect')
    def handle_connect():
        logger.info(f'Client connected: {request.sid}')
        emit('connection_success', {'sid': request.sid})

    @socketio.on('disconnect')
    def handle_disconnect():
        room_id = user_rooms.get(request.sid)
        if room_id and room_id in active_rooms:
            username = None
            # Find username for this session
            for user, data in active_rooms[room_id]['participants'].items():
                if data['sid'] == request.sid:
                    username = user
                    break
            
            if username:
                del active_rooms[room_id]['participants'][username]
                del user_rooms[request.sid]
                
                if not active_rooms[room_id]['participants']:
                    del active_rooms[room_id]
                
                emit('user_left', {
                    'username': username,
                    'participant_count': len(active_rooms.get(room_id, {}).get('participants', {}))
                }, room=room_id)

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
            
            # Get current participants
            participants = list(active_rooms[room_id]['participants'].keys())
            
            # Notify room about new user
            emit('user_joined', {
                'username': username,
                'participant_count': len(participants)
            }, room=room_id)
            
            # Send participants list to the new user
            emit('room_participants', {
                'participants': participants
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
                leave_room(room_id)
                
                emit('user_left', {
                    'username': username,
                    'participant_count': len(active_rooms[room_id]['participants'])
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

    @socketio.on('sign_prediction')
    def handle_sign_prediction(data):
        try:
            room_id = data['room']
            emit('sign_prediction', {
                'username': data['username'],
                'prediction': data['prediction']
            }, room=room_id)
        except Exception as e:
            logger.error(f'Sign prediction error: {str(e)}')

    return socketio
