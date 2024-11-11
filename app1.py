from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
from flask_socketio import SocketIO
from flask_cors import CORS
import cv2
import numpy as np
from tensorflow.keras.models import load_model
from twilio.rest import Client
import random
import string
from pymongo import MongoClient
from datetime import datetime, timedelta
import base64
import os
import logging
from call import init_video_call


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Change this in production

# Configure CORS
CORS(app, resources={r"/*": {"origins": "*"}})

# Initialize Socket.IO
socketio = SocketIO(app, cors_allowed_origins="*", ping_timeout=60)

# Initialize Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'land'
bcrypt = Bcrypt(app)

try:
    # MongoDB connection
    mongo_client = MongoClient("mongodb+srv://gesturespeakdb:gesturespeakdb@gsusers.8wjxr.mongodb.net/")
    db = mongo_client["gesturespeakdb"]
    users_collection = db["users"]
    rooms_collection = db["rooms"]
    logger.info("Successfully connected to MongoDB")
except Exception as e:
    logger.error(f"MongoDB connection error: {e}")
    raise

try:
    # Twilio configuration
    account_sid = 'ACbc271c75232fa7cba0188f1b3f8618a2'
    auth_token = 'a7f00c3cff83a88340e3eac3fcd12693'
    twilio_client = Client(account_sid, auth_token)
    logger.info("Successfully initialized Twilio client")
except Exception as e:
    logger.error(f"Twilio initialization error: {e}")
    twilio_client = None

try:
    # Load ASL model
    model = load_model('asl_model1.h5')
    class_map = ["A", "B", "C", "D", "E", "F", "G", "H", "Hello", "I", "I Love You",
                 "J", "K", "L", "M", "N", "No", "O", "P", "Q", "R", "S", "Space", 
                 "T", "U", "V", "W", "X", "Y", "Yes", "Z"]
    logger.info("Successfully loaded ASL model")
except Exception as e:
    logger.error(f"Model loading error: {e}")
    model = None

class User(UserMixin):
    def __init__(self, username):
        self.id = username

@login_manager.user_loader
def load_user(username):
    try:
        user_data = users_collection.find_one({"username": username})
        if user_data:
            return User(user_data["username"])
        return None
    except Exception as e:
        logger.error(f"Error loading user: {e}")
        return None

def preprocess_frame(frame):
    try:
        resized = cv2.resize(frame, (224, 224))
        normalized = resized / 255.0
        return np.expand_dims(normalized, axis=0)
    except Exception as e:
        logger.error(f"Frame preprocessing error: {e}")
        return None

def generate_otp():
    return random.randint(100000, 999999)

def generate_room_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

@app.route('/')
def land():
    return render_template('land.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            username = request.form['username']
            password = request.form['password']
            user = users_collection.find_one({"username": username})

            if user and bcrypt.check_password_hash(user['password'], password):
                login_user(User(username))
                users_collection.update_one(
                    {"username": username},
                    {"$set": {"last_login": datetime.utcnow()}}
                )
                return redirect(url_for('dashboard'))
            flash("Invalid username or password", "error")
        except Exception as e:
            logger.error(f"Login error: {e}")
            flash("An error occurred during login", "error")
    
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    try:
        recent_rooms = list(rooms_collection.find({
            "participants": current_user.id,
            "active": True
        }).sort("last_activity", -1).limit(5))
        
        return render_template('dashboard.html', recent_rooms=recent_rooms)
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        flash("Error loading dashboard", "error")
        return redirect(url_for('land'))

@app.route('/phone_signin', methods=['POST'])
def phone_signin():
    try:
        phone_number = request.form['phone_number']
        if not phone_number.isdigit() or len(phone_number) != 10:
            flash("Invalid phone number format", "error")
            return redirect(url_for('login'))

        otp = generate_otp()
        expiry = datetime.utcnow() + timedelta(minutes=5)

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

        # Send OTP via Twilio
        if twilio_client:
            twilio_client.messages.create(
                body=f"Your GestureSpeak verification code is: {otp}",
                from_='+17407600895',
                to=f'+91{phone_number}'
            )
        
        return redirect(url_for('verify_otp', phone_number=phone_number))
    except Exception as e:
        logger.error(f"Phone signin error: {e}")
        flash("Error processing phone signin", "error")
        return redirect(url_for('login'))

@app.route('/verify_otp/<phone_number>', methods=['GET', 'POST'])
def verify_otp(phone_number):
    if request.method == 'POST':
        try:
            entered_otp = request.form['otp']
            user = users_collection.find_one({"phone_number": phone_number})

            if user:
                if datetime.utcnow() > user["otp_expiry"]:
                    flash("OTP expired", "error")
                    return redirect(url_for('login'))
                if int(entered_otp) == user["otp"]:
                    login_user(User(user["username"]))
                    users_collection.update_one(
                        {"username": user["username"]},
                        {"$set": {"last_login": datetime.utcnow()}}
                    )
                    return redirect(url_for('dashboard'))
            else:
                if datetime.utcnow().timestamp() > session.get('temp_expiry', 0):
                    flash("OTP expired", "error")
                    return redirect(url_for('login'))
                if int(entered_otp) == session.get('temp_otp'):
                    return redirect(url_for('register'))

            flash("Invalid OTP", "error")
        except Exception as e:
            logger.error(f"OTP verification error: {e}")
            flash("Error verifying OTP", "error")
    
    return render_template('verify_otp.html', phone_number=phone_number)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
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
            
            hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
            phone_number = session.get('temp_phone')

            user_data = {
                "name": name,
                "email": email,
                "username": username,
                "password": hashed_password,
                "phone_number": phone_number,
                "verified": True,
                "created_at": datetime.utcnow(),
                "last_login": datetime.utcnow()
            }
            
            users_collection.insert_one(user_data)
            login_user(User(username))
            return redirect(url_for('dashboard'))
        except Exception as e:
            logger.error(f"Registration error: {e}")
            flash("Error during registration", "error")
    
    return render_template('register.html')

@app.route('/index')
@login_required
def index():
    return render_template('index.html')

@app.route('/predict', methods=['POST'])
@login_required
def predict():
    if not model:
        return jsonify({'error': 'Model not available'}), 500

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
            return jsonify({'error': 'Error preprocessing image'}), 400

        prediction = model.predict(processed_img)
        predicted_class = class_map[np.argmax(prediction)]
        confidence = float(np.max(prediction)) * 100

        return jsonify({
            'prediction': predicted_class,
            'confidence': confidence,
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        logger.error(f"Prediction error: {e}")
        return jsonify({'error': 'Prediction failed'}), 500

@app.route('/create-room')
@login_required
def create_room():
    try:
        room_id = generate_room_code()
        
        rooms_collection.insert_one({
            "room_id": room_id,
            "creator": current_user.id,
            "created_at": datetime.utcnow(),
            "last_activity": datetime.utcnow(),
            "active": True,
            "participants": [current_user.id],
            "settings": {
                "max_participants": 5,
                "enable_chat": True,
                "enable_predictions": True
            }
        })
        
        return jsonify({'room_id': room_id})
    except Exception as e:
        logger.error(f"Room creation error: {e}")
        return jsonify({'error': 'Failed to create room'}), 500

@app.route('/join-room', methods=['POST'])
@login_required
def join_room():
    try:
        room_id = request.form.get('room_id')
        if not room_id:
            flash('Room code is required', 'error')
            return redirect(url_for('dashboard'))
        
        room = rooms_collection.find_one({"room_id": room_id, "active": True})
        if not room:
            flash('Room not found or inactive', 'error')
            return redirect(url_for('dashboard'))
        
        if len(room['participants']) >= room['settings']['max_participants']:
            flash('Room is full', 'error')
            return redirect(url_for('dashboard'))

        if current_user.id not in room['participants']:
            rooms_collection.update_one(
                {"room_id": room_id},
                {
                    "$push": {"participants": current_user.id},
                    "$set": {"last_activity": datetime.utcnow()}
                }
            )
        
        return redirect(url_for('room', room_id=room_id))
    except Exception as e:
        logger.error(f"Room joining error: {e}")
        flash("Error joining room", "error")
        return redirect(url_for('dashboard'))

@app.route('/room/<room_id>')
@login_required
def room(room_id):
    try:
        room = rooms_collection.find_one({"room_id": room_id, "active": True})
        if not room:
            flash('Room not found or inactive', 'error')
            return redirect(url_for('dashboard'))
        
        return render_template('room.html', 
                             room_id=room_id, 
                             username=current_user.id,
                             room_data=room)
    except Exception as e:
        logger.error(f"Room access error: {e}")
        flash("Error accessing room", "error")
        return redirect(url_for('dashboard'))

@app.route('/logout')
@login_required
def logout():
    try:
        # Update last activity
        users_collection.update_one(
            {"username": current_user.id},
            {"$set": {"last_activity": datetime.utcnow()}}
        )
        logout_user()
    except Exception as e:
        logger.error(f"Logout error: {e}")
    return redirect(url_for('land'))

@app.errorhandler(404)
def not_found_error(error):
    return render_template('land.html', 
                         error="Page not found",
                         message="The requested page could not be found."), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return render_template('land.html',
                         error="Internal Server Error",
                         message="An unexpected error occurred."), 500

# Initialize video calling functionality
socketio = init_video_call(app)

if __name__ == '__main__':
    try:
        port = int(os.environ.get('PORT', 5000))
        socketio.run(app, 
                    debug=True,
                    port=port,
                    allow_unsafe_werkzeug=True)
    except Exception as e:
        logger.error(f"Server startup error: {e}")