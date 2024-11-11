from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
from flask_socketio import SocketIO
import cv2
import numpy as np
from tensorflow.keras.models import load_model
from twilio.rest import Client
import random
from pymongo import MongoClient
from datetime import datetime, timedelta
import base64
import os
import json
from werkzeug.utils import secure_filename
import logging
from functools import wraps

# Initialize Flask app and configurations
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your_secret_key_here')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask extensions
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'land'
login_manager.login_message_category = 'info'
bcrypt = Bcrypt(app)

# Initialize SocketIO for real-time communication
socketio = SocketIO(app, cors_allowed_origins="*")

# MongoDB configuration
MONGO_URI = os.environ.get('MONGO_URI', "mongodb+srv://gesturespeakdb:gesturespeakdb@gsusers.8wjxr.mongodb.net/")
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["gesturespeakdb"]
users_collection = db["users"]
rooms_collection = db["rooms"]

# Twilio configuration
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', 'ACbc271c75232fa7cba0188f1b3f8618a2')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', 'a7f00c3cff83a88340e3eac3fcd12693')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER', '+17407600895')
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Load ASL model
try:
    model = load_model('asl_model1.h5')
    class_map = ["A", "B", "C", "D", "E", "F", "G", "H", "Hello", "I", "I Love You",
                 "J", "K", "L", "M", "N", "No", "O", "P", "Q", "R", "S", "Space", 
                 "T", "U", "V", "W", "X", "Y", "Yes", "Z"]
except Exception as e:
    logger.error(f"Error loading model: {e}")
    model = None

class User(UserMixin):
    def __init__(self, username, user_data=None):
        self.id = username
        self.user_data = user_data or {}

@login_manager.user_loader
def load_user(username):
    user_data = users_collection.find_one({"username": username})
    if user_data:
        return User(username, user_data)
    return None

def handle_error(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {f.__name__}: {str(e)}")
            flash("An error occurred. Please try again.", "error")
            return redirect(url_for('land'))
    return decorated_function

def preprocess_frame(frame):
    try:
        resized = cv2.resize(frame, (224, 224))
        normalized = resized / 255.0
        return np.expand_dims(normalized, axis=0)
    except Exception as e:
        logger.error(f"Error preprocessing frame: {e}")
        return None

@app.route('/')
def land():
    return render_template('land.html')

@app.route('/login', methods=['GET', 'POST'])
@handle_error
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = users_collection.find_one({"username": username})

        if user and bcrypt.check_password_hash(user['password'], password):
            login_user(User(username, user))
            flash("Successfully logged in!", "success")
            return redirect(url_for('dashboard'))
        flash("Invalid username or password", "error")
    
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', user=current_user)

@app.route('/phone_signin', methods=['POST'])
@handle_error
def phone_signin():
    phone_number = request.form['phone_number']
    if not phone_number.isdigit() or len(phone_number) != 10:
        flash("Invalid phone number format", "error")
        return redirect(url_for('index'))

    otp = random.randint(100000, 999999)
    expiry = datetime.now() + timedelta(minutes=5)
    
    user = users_collection.find_one({"phone_number": phone_number})
    if user:
        users_collection.update_one(
            {"phone_number": phone_number},
            {"$set": {"otp": otp, "otp_expiry": expiry}}
        )
    else:
        session['temp_phone'] = phone_number
        session['temp_otp'] = otp
        session['temp_expiry'] = expiry.timestamp()
    
    try:
        twilio_client.messages.create(
            body=f"Your GestureSpeak OTP is {otp}. Valid for 5 minutes.",
            from_=TWILIO_PHONE_NUMBER,
            to=f'+91{phone_number}'
        )
        flash("OTP sent successfully!", "success")
    except Exception as e:
        logger.error(f"Error sending OTP: {e}")
        flash("Error sending OTP. Please try again.", "error")
        return redirect(url_for('land'))

    return redirect(url_for('verify_otp', phone_number=phone_number))

@app.route('/verify_otp/<phone_number>', methods=['GET', 'POST'])
@handle_error
def verify_otp(phone_number):
    if request.method == 'POST':
        entered_otp = request.form['otp']
        user = users_collection.find_one({"phone_number": phone_number})

        if user:
            if datetime.now() > user["otp_expiry"]:
                flash("OTP expired", "error")
                return redirect(url_for('land'))
            if int(entered_otp) == user["otp"]:
                login_user(User(user["username"], user))
                flash("Successfully logged in!", "success")
                return redirect(url_for('dashboard'))
        else:
            if datetime.now().timestamp() > session.get('temp_expiry', 0):
                flash("OTP expired", "error")
                return redirect(url_for('land'))
            if int(entered_otp) == session.get('temp_otp'):
                return redirect(url_for('register'))

        flash("Invalid OTP", "error")
    return render_template('verify_otp.html', phone_number=phone_number)

@app.route('/register', methods=['GET', 'POST'])
@handle_error
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            flash("Passwords do not match", "error")
            return render_template('register.html')
        
        if users_collection.find_one({"username": username}):
            flash("Username already exists", "error")
            return render_template('register.html')
        
        if users_collection.find_one({"email": email}):
            flash("Email already registered", "error")
            return render_template('register.html')

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        phone_number = session.get('temp_phone')

        user_data = {
            "name": name,
            "email": email,
            "username": username,
            "password": hashed_password,
            "phone_number": phone_number,
            "verified": True,
            "created_at": datetime.now(),
            "last_login": datetime.now()
        }

        users_collection.insert_one(user_data)
        login_user(User(username, user_data))
        flash("Registration successful!", "success")
        return redirect(url_for('dashboard'))
    
    return render_template('register.html')

@app.route('/room/<room_id>')
@login_required
def room(room_id):
    room_data = rooms_collection.find_one({"room_id": room_id})
    if not room_data:
        flash("Room not found", "error")
        return redirect(url_for('dashboard'))
    return render_template('room.html', room_id=room_id, username=current_user.id)

@app.route('/create_room', methods=['POST'])
@login_required
def create_room():
    room_id = ''.join(random.choices('0123456789ABCDEF', k=6))
    room_data = {
        "room_id": room_id,
        "created_by": current_user.id,
        "created_at": datetime.now(),
        "active": True,
        "participants": [current_user.id]
    }
    rooms_collection.insert_one(room_data)
    return jsonify({"room_id": room_id})

@app.route('/join_room', methods=['POST'])
@login_required
def join_room():
    room_id = request.form.get('room_id')
    room_data = rooms_collection.find_one({"room_id": room_id})
    
    if not room_data:
        flash("Invalid room code", "error")
        return redirect(url_for('dashboard'))
    
    if not room_data["active"]:
        flash("This room is no longer active", "error")
        return redirect(url_for('dashboard'))
    
    if current_user.id not in room_data["participants"]:
        rooms_collection.update_one(
            {"room_id": room_id},
            {"$push": {"participants": current_user.id}}
        )
    
    return redirect(url_for('room', room_id=room_id))

@app.route('/index')
@login_required
def index():
    return render_template('index.html')

@app.route('/predict', methods=['POST'])
@login_required
def predict():
    try:
        data = request.get_json()
        image_data = data['image'].split(',')[1]
        image_bytes = base64.b64decode(image_data)
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            return jsonify({'error': 'Invalid image data'}), 400
        
        processed_img = preprocess_frame(img)
        if processed_img is None:
            return jsonify({'error': 'Error processing image'}), 400
        
        prediction = model.predict(processed_img)
        predicted_class = class_map[np.argmax(prediction)]
        confidence = float(np.max(prediction))
        
        return jsonify({
            'prediction': predicted_class,
            'confidence': confidence,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f"Error in prediction: {e}")
        return jsonify({'error': 'Prediction failed'}), 500




@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Successfully logged out!", "success")
    return redirect(url_for('land'))

# SocketIO event handlers
@socketio.on('join')
def handle_join(data):
    room = data.get('room')
    if room:
        join_room(room)
        socketio.emit('user_joined', {
            'username': current_user.id,
            'timestamp': datetime.now().isoformat()
        }, room=room)

@socketio.on('leave')
def handle_leave(data):
    room = data.get('room')
    if room:
        leave_room(room)
        socketio.emit('user_left', {
            'username': current_user.id,
            'timestamp': datetime.now().isoformat()
        }, room=room)

@socketio.on('sign_prediction')
def handle_sign_prediction(data):
    room = data.get('room')
    if room:
        socketio.emit('sign_update', {
            'username': current_user.id,
            'prediction': data.get('prediction'),
            'timestamp': datetime.now().isoformat()
        }, room=room)

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return render_template('500.html'), 500

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)