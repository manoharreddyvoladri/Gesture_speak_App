from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask import Flask, render_template, Response, jsonify
from flask_bcrypt import Bcrypt
from flask_socketio import SocketIO
from flask_cors import CORS
from OpenSSL import SSL
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
import gdown
from dotenv import load_dotenv
from call import init_video_call
import threading
import queue
from ultralytics import YOLO
import time
import socket
import eventlet
# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    filename=os.getenv('LOG_FILE', 'app.log'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.getenv('LOG_FILE', 'app.log'))
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'aOJ********************')
app.template_folder = os.path.abspath('templates')












# Initialize YOLO model
model = YOLO('best.pt')

# Global variables
detection_history = []
frame_queue = queue.Queue(maxsize=2)
prediction_queue = queue.Queue(maxsize=2)
is_predicting = False

LETTER_TO_WORD = {
    'A': 'APPLE', 'B': 'BOOK', 'C': 'CAT', 'D': 'DOG',
    'E': 'ELEPHANT', 'F': 'FRIEND', 'G': 'GOOD', 'H': 'HELLO',
    'I': 'ICE CREAM', 'J': 'JUMP', 'K': 'KING', 'L': 'LOVE',
    'M': 'MOTHER', 'N': 'NICE', 'O': 'ORANGE', 'P': 'PLEASE',
    'Q': 'QUEEN', 'R': 'RAINBOW', 'S': 'SUN', 'T': 'THANK YOU',
    'U': 'UMBRELLA', 'V': 'VICTORY', 'W': 'WATER', 'X': 'X-RAY',
    'Y': 'YELLOW', 'Z': 'ZEBRA'
}

class VideoCamera:
    def __init__(self):
        self.video = cv2.VideoCapture(0)
        self.video.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.video.set(cv2.CAP_PROP_FPS, 30)
        self.last_prediction_time = time.time()
        self.current_prediction = None
        self.current_word = None
        self.current_bbox = None
        self.running = True
        
        self.prediction_thread = threading.Thread(target=self.predict_frames)
        self.prediction_thread.daemon = True
        self.prediction_thread.start()

    def __del__(self):
        self.running = False
        if self.video.isOpened():
            self.video.release()

    def predict_frames(self):
        while self.running:
            if not is_predicting:
                time.sleep(0.1)
                continue
                
            try:
                frame = frame_queue.get_nowait()
                current_time = time.time()
                
                if current_time - self.last_prediction_time >= 0.5:
                    results = model(frame, conf=0.3)
                    
                    if len(results[0].boxes) > 0:
                        confidences = results[0].boxes.conf.cpu().numpy()
                        max_conf_idx = np.argmax(confidences)
                        prediction = results[0].names[int(results[0].boxes.cls[max_conf_idx])]
                        bbox = results[0].boxes.xyxy[max_conf_idx].cpu().numpy()
                        word = LETTER_TO_WORD.get(prediction, "Unknown")
                        confidence = float(confidences[max_conf_idx])
                        
                        prediction_data = {
                            'prediction': prediction,
                            'word': word,
                            'bbox': bbox,
                            'confidence': confidence
                        }
                        
                        try:
                            prediction_queue.put_nowait(prediction_data)
                        except queue.Full:
                            pass
                        
                        detection_history.append({
                            'letter': prediction,
                            'word': word,
                            'confidence': confidence,
                            'timestamp': datetime.now().strftime("%H:%M:%S")
                        })
                        if len(detection_history) > 10:
                            detection_history.pop(0)
                        
                        self.last_prediction_time = current_time
            except queue.Empty:
                time.sleep(0.01)

    def get_frame(self):
        success, frame = self.video.read()
        if not success:
            return None

        try:
            frame_queue.put_nowait(frame.copy())
        except queue.Full:
            pass

        if is_predicting:
            try:
                prediction_data = prediction_queue.get_nowait()
                self.current_prediction = prediction_data['prediction']
                self.current_word = prediction_data['word']
                self.current_bbox = prediction_data['bbox']
            except queue.Empty:
                pass

            if self.current_bbox is not None:
                x1, y1, x2, y2 = map(int, self.current_bbox)
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                label = f"{self.current_prediction} - {self.current_word}"
                cv2.putText(frame, label, (x1, y1-10), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)

        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
        _, jpeg = cv2.imencode('.jpg', frame, encode_param)
        return jpeg.tobytes()

camera = None

def get_camera():
    global camera
    if camera is None:
        camera = VideoCamera()
    return camera


# Add this before your routes in app.py
@app.before_request
def force_https():
    if not request.is_secure and app.env != 'development' and request.headers.get('X-Forwarded-Proto', 'http') == 'http':
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url, code=301)



@app.route('/video_feed')
def video_feed():
    return Response(gen(get_camera()),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/get_history')
def get_history():
    return jsonify(detection_history)

@app.route('/start_prediction')
def start_prediction():
    global is_predicting
    is_predicting = True
    return jsonify({'status': 'success'})

@app.route('/stop_prediction')
def stop_prediction():
    global is_predicting
    is_predicting = False
    return jsonify({'status': 'success'})

def gen(camera):
    while True:
        frame = camera.get_frame()
        if frame is not None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n\r\n')













# Update model download function with new configuration
def download_model_from_gdrive():
    """Download the ASL model from Google Drive if not present."""
    try:
        model_path = os.getenv('MODEL_PATH', 'asl_model1.h5')
        if not os.path.exists(model_path):
            logger.info("Downloading ASL model from Google Drive...")
            url = os.getenv('MODEL_DOWNLOAD_URL', 
                          'https://drive.google.com/uc?id=1HaKX9r7D7F_xXH0yp5rDehMdjdNAfchl')
            gdown.download(url, model_path, quiet=False)
            logger.info("Model downloaded successfully")
        return True
    except Exception as e:
        logger.error(f"Error downloading model: {e}")
        return False
try:
    mongo_client = MongoClient(os.getenv('MONGODB_URI'))
    db = mongo_client[os.getenv('MONGODB_DB_NAME', 'gesturespeakdb')]
    users_collection = db["users"]
    rooms_collection = db["rooms"]
    predictions_collection = db["predictions"]
    logger.info("Successfully connected to MongoDB")
except Exception as e:
    logger.error(f"MongoDB connection error: {e}")
    raise

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'aOJl6**********************Uj0')

# Enhanced app configuration
app.config.update(
    SESSION_COOKIE_SECURE=False,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,
    MAX_ROOM_PARTICIPANTS=int(os.getenv('MAX_ROOM_PARTICIPANTS', '5')),
    ROOM_TIMEOUT_HOURS=int(os.getenv('ROOM_TIMEOUT_HOURS', '24')),
    SOCKET_TIMEOUT=60,  # Fixed default value
    SESSION_COOKIE_PATH='/',
    SESSION_COOKIE_DOMAIN=None,
    REMEMBER_COOKIE_SECURE=False,
    REMEMBER_COOKIE_HTTPONLY=True
)


# Add CORS configuration
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "allow_headers": ["Content-Type"],
        "methods": ["GET", "POST", "OPTIONS"],
        "supports_credentials": True
    }
})

# Update your SocketIO initialization with new configurations
socketio = SocketIO(
    app, 
    cors_allowed_origins="*",
    ping_timeout=60,
    ping_interval=25,
    async_mode='eventlet',
    logger=True,
    engineio_logger=True,
    allow_upgrades=True
)
# Initialize Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'land'
bcrypt = Bcrypt(app)

# Database connection with retry
def get_mongo_client():
    retries = 3
    while retries > 0:
        try:
            mongo_uri = os.getenv(MONGODB_URI)
            client = MongoClient(mongo_uri)
            client.admin.command('ping')
            logger.info("Successfully connected to MongoDB")
            return client
        except Exception as e:
            retries -= 1
            if retries == 0:
                logger.error(f"Failed to connect to MongoDB after 3 attempts: {e}")
                raise
            logger.warning(f"MongoDB connection attempt failed, retrying... ({3-retries}/3)")
    return None

try:
    mongo_client = get_mongo_client()
    db = mongo_client[os.getenv('MONGODB_DB_NAME', 'gesturespeakdb')]
    users_collection = db["users"]
    rooms_collection = db["rooms"]
    predictions_collection = db["predictions"]
    logger.info("MongoDB collections initialized")
except Exception as e:
    logger.error(f"MongoDB initialization error: {e}")
    raise

# Twilio client initialization
# Update Twilio configuration
try:
    twilio_client = Client(
        os.getenv('TWILIO_ACCOUNT_SID'),
        os.getenv('TWILIO_AUTH_TOKEN')
    )
    logger.info("Successfully initialized Twilio client")
except Exception as e:
    logger.error(f"Twilio initialization error: {e}")
    twilio_client = None

# Load ASL model with retry and download
def load_asl_model():
    retries = 3
    while retries > 0:
        try:
            model_path = 'asl_model1.h5'
            if not os.path.exists(model_path):
                if not download_model_from_gdrive():
                    raise Exception("Failed to download model")
                
            model = load_model(model_path)
            logger.info(f"Successfully loaded ASL model from {model_path}")
            return model
        except Exception as e:
            retries -= 1
            if retries == 0:
                logger.error(f"Failed to load ASL model after 3 attempts: {e}")
                return None
            logger.warning(f"Model loading attempt failed, retrying... ({3-retries}/3)")
    return None

try:
    model = load_asl_model()
    class_map = ["A", "B", "C", "D", "E", "F", "G", "H", "Hello", "I", "I Love You",
                "J", "K", "L", "M", "N", "No", "O", "P", "Q", "R", "S", "Space", 
                "T", "U", "V", "W", "X", "Y", "Yes", "Z"]
except Exception as e:
    logger.error(f"Model loading error: {e}")
    model = None


class User(UserMixin):
    def __init__(self, username, user_data=None):
        self.id = username
        self.user_data = user_data or {}

    def get_id(self):
        return str(self.id)  # Make sure it returns a string

    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

@socketio.on('sign_prediction')
def handle_sign_prediction(data):
    try:
        room_id = data['room']
        emit('sign_prediction', {
            'username': data['username'],
            'prediction': data['prediction'],
            'confidence': data['confidence'],
            'timestamp': data['timestamp']
        }, room=room_id)
    except Exception as e:
        logger.error(f"Error handling sign prediction: {e}")


@login_manager.user_loader
def load_user(username):
    try:
        user_data = users_collection.find_one({"username": username})
        if user_data:
            return User(username, user_data)
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
    """Generate a secure OTP."""
    return random.randint(100000, 999999)

def generate_room_code():
    """Generate a unique room code."""
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        if not rooms_collection.find_one({"room_id": code}):
            return code

def send_otp(phone_number, otp):
    """Send OTP via Twilio."""
    if not twilio_client:
        logger.error("Twilio client not initialized")
        return False

    try:
        message = twilio_client.messages.create(
            body=f"Your GestureSpeak verification code is: {otp}",
            from_=os.getenv('TWILIO_PHONE_NUMBER', '+17407600895'),
            to=f'+91{phone_number}'
        )
        logger.info(f"OTP sent successfully to {phone_number}")
        return True
    except Exception as e:
        logger.error(f"Failed to send OTP: {e}")
        return False
# Routes
@app.route('/')
def land():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('land.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        try:
            username = request.form['username']
            password = request.form['password']
            remember = request.form.get('remember', False)  # Add this
            user = users_collection.find_one({"username": username})

            if user and bcrypt.check_password_hash(user['password'], password):
                user_obj = User(username)
                login_user(user_obj, remember=remember)  # Add remember parameter
                users_collection.update_one(
                    {"username": username},
                    {"$set": {
                        "last_login": datetime.utcnow(),
                        "last_ip": request.remote_addr  # Add this
                    }}
                )
                # Set session variables
                session['user_id'] = username
                session.permanent = True  # Add this
                
                return redirect(url_for('dashboard'))
            flash("Invalid username or password", "error")
        except Exception as e:
            logger.error(f"Login error: {e}")
            flash("An error occurred during login", "error")
    
    return render_template('login.html')
@app.before_request
def before_request():
    if current_user.is_authenticated:
        session.permanent = True
        app.permanent_session_lifetime = timedelta(days=7)

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

        if not send_otp(phone_number, otp):
            flash("Failed to send OTP. Please try again.", "error")
            return redirect(url_for('login'))
        
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
                    return redirect(url_for('land'))
                if int(entered_otp) == user["otp"]:
                    login_user(User(user["username"]))
                    return redirect(url_for('dashboard'))
            else:
                if datetime.utcnow().timestamp() > session.get('temp_expiry', 0):
                    flash("OTP expired", "error")
                    return redirect(url_for('land'))
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

            users_collection.insert_one({
                "name": name,
                "email": email,
                "username": username,
                "password": hashed_password,
                "phone_number": phone_number,
                "verified": True,
                "created_at": datetime.utcnow(),
                "last_login": datetime.utcnow()
            })
            
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
        current_time = datetime.utcnow()
        
        room_data = {
            "room_id": room_id,
            "creator": current_user.id,
            "created_at": current_time,
            "last_activity": current_time,
            "active": True,
            "participants": [current_user.id],
            "settings": {
                "max_participants": 5,
                "enable_chat": True,
                "enable_predictions": True
            }
        }
        
        result = rooms_collection.insert_one(room_data)
        if not result.inserted_id:
            raise Exception("Failed to create room in database")
            
        logger.info(f"Room created successfully: {room_id}")
        return jsonify({"status": "success", "room_id": room_id})
    except Exception as e:
        logger.error(f"Room creation error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/join-room', methods=['POST'])
@login_required
def join_room():
    try:
        room_id = request.form.get('room_id')
        if not room_id:
            flash('Room code is required', 'error')
            return redirect(url_for('dashboard'))

        # Check if room exists and is active
        room = rooms_collection.find_one({
            "room_id": room_id,
            "active": True
        })

        if not room:
            flash('Room not found or inactive', 'error')
            return redirect(url_for('dashboard'))
            
        # Add user to participants if not already there
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
        room = rooms_collection.find_one({
            "room_id": room_id,
            "active": True
        })
        
        if not room:
            flash('Room not found or inactive', 'error')
            return redirect(url_for('dashboard'))

        if current_user.id not in room['participants']:
            flash('Not authorized to join this room', 'error')
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
        users_collection.update_one(
            {"username": current_user.id},
            {"$set": {"last_activity": datetime.utcnow()}}
        )
        logout_user()
    except Exception as e:
        logger.error(f"Logout error: {e}")
    return redirect(url_for('land'))

@app.route('/health')
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'model_loaded': bool(model),
        'database_connected': bool(mongo_client)
    })

@app.errorhandler(404)
def not_found_error(error):
    return render_template('error.html',
                         error="Page not found",
                         message="The requested page could not be found."), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return render_template('error.html',
                         error="Internal Server Error",
                         message="An unexpected error occurred."), 500

# Initialize video calling functionality
socketio = init_video_call(app)

# Update cleanup function with new configuration
def cleanup_inactive_rooms():
    """Cleanup inactive rooms periodically."""
    while True:
        try:
            timeout_hours = int(os.getenv('ROOM_TIMEOUT_HOURS', 24))
            cleanup_interval = int(os.getenv('ROOM_CLEANUP_INTERVAL', 300))
            cutoff_time = datetime.utcnow() - timedelta(hours=timeout_hours)
            
            rooms_collection.update_many(
                {
                    "last_activity": {"$lt": cutoff_time},
                    "active": True
                },
                {"$set": {"active": False}}
            )
            logger.info("Completed room cleanup")
        except Exception as e:
            logger.error(f"Room cleanup error: {e}")
        socketio.sleep(cleanup_interval)

if __name__ == '__main__':
    try:
        import socket
        def get_ip():
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                # doesn't even have to be reachable
                s.connect(('10.255.255.255', 1))
                IP = s.getsockname()[0]
            except Exception:
                IP = '127.0.0.1'
            finally:
                s.close()
            return IP

        host = '0.0.0.0'  # Listen on all network interfaces
        port = 5000
        local_ip = get_ip()

        print("\n" + "="*50)
        print("Server Running!")
        print("="*50)
        print(f"\nAccess URLs:")
        print(f"Local computer: http://localhost:{port}")
        print(f"Other devices : http://{local_ip}:{port}")
        print("\nImportant Notes:")
        print("1. Make sure all devices are on the same network")
        print("2. Allow camera/microphone permissions when prompted")
        print("3. If using mobile, enable desktop site in browser")
        print("="*50 + "\n")

        socketio.run(
            app,
            host=host,
            port=port,
            debug=False,  # Set to False for production
            allow_unsafe_werkzeug=True
        )
    except Exception as e:
        print(f"Server startup error: {e}")
        raise
