from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
from flask_socketio import SocketIO
from flask_cors import CORS
from twilio.rest import Client
import secrets
import string
from pymongo import MongoClient
from datetime import datetime, timedelta
import os
import socket
import logging
from dotenv import load_dotenv
from call import init_video_call

# Load environment variables
load_dotenv()

# Configure logging
# A hosting platform (Render, etc.) captures stdout/stderr as the log
# stream and gives you an ephemeral filesystem - writing to a local log
# file there is wasted I/O that nobody will ever read. Only add the
# FileHandler for local development.
_log_handlers = [logging.StreamHandler()]
if os.getenv('FLASK_ENV', 'production') == 'development':
    _log_handlers.append(logging.FileHandler(os.getenv('LOG_FILE', 'app.log')))

logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=_log_handlers
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.template_folder = os.path.abspath('templates')
app.secret_key = os.getenv('SECRET_KEY')
if not app.secret_key:
    raise RuntimeError(
        "SECRET_KEY environment variable is not set. Refusing to start with an "
        "insecure default secret key."
    )


def _is_secure_cookies_enabled():
    # A cookie marked Secure is silently dropped by every browser when the
    # page isn't loaded over HTTPS - which this app isn't in local/dev runs
    # (plain http://localhost). Force it off in development regardless of
    # the .env value, or login "succeeds" (302 to /dashboard) but the
    # session cookie never actually gets stored, so the very next request
    # looks logged-out and @login_required bounces the user right back out.
    if os.getenv('FLASK_ENV', 'production') == 'development':
        return False
    return os.getenv('SESSION_COOKIE_SECURE', 'True').lower() == 'true'


def _parse_cors_origins():
    """Read allowed origins from env. '*' disables credentialed CORS (the two
    are mutually exclusive - browsers reject a wildcard origin combined with
    credentials)."""
    origins = os.getenv('CORS_ALLOWED_ORIGINS', '*').strip()
    if origins == '*' or not origins:
        return '*'
    return [o.strip() for o in origins.split(',') if o.strip()]


cors_origins = _parse_cors_origins()
allow_credentialed_cors = cors_origins != '*'

# Enhanced app configuration
app.config.update(
    SESSION_COOKIE_SECURE=_is_secure_cookies_enabled(),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE=os.getenv('SESSION_COOKIE_SAMESITE', 'Lax'),
    PERMANENT_SESSION_LIFETIME=timedelta(days=int(os.getenv('SESSION_LIFETIME_DAYS', '7'))),
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,
    MAX_ROOM_PARTICIPANTS=int(os.getenv('MAX_ROOM_PARTICIPANTS', '5')),
    ROOM_TIMEOUT_HOURS=int(os.getenv('ROOM_TIMEOUT_HOURS', '24')),
    SESSION_COOKIE_PATH='/',
    SESSION_COOKIE_DOMAIN=None,
    REMEMBER_COOKIE_SECURE=_is_secure_cookies_enabled(),
    REMEMBER_COOKIE_HTTPONLY=True
)

# CORS configuration
CORS(app, resources={
    r"/*": {
        "origins": cors_origins,
        "allow_headers": ["Content-Type"],
        "methods": ["GET", "POST", "OPTIONS"],
        "supports_credentials": allow_credentialed_cors
    }
})

# Single SocketIO instance for the whole app (video-call signaling is wired
# onto this same instance via init_video_call, not a second SocketIO()).
# async_mode='threading' uses plain Python threads with no monkey-patching -
# eventlet's monkey_patch() broke on newer Python threading internals
# (missing _thread.start_joinable_thread), and pinning an older Python on
# the deploy platform proved unreliable, so this sidesteps that entirely.
socketio = SocketIO(
    app,
    cors_allowed_origins=cors_origins,
    ping_timeout=60,
    ping_interval=25,
    async_mode='threading',
    logger=True,
    engineio_logger=False,
    allow_upgrades=True
)

# Initialize Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
bcrypt = Bcrypt(app)


# Database connection with retry
def get_mongo_client():
    retries = 3
    while retries > 0:
        try:
            mongo_uri = os.getenv('MONGODB_URI')
            if not mongo_uri:
                raise RuntimeError("MONGODB_URI environment variable is not set")
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


mongo_client = get_mongo_client()
db = mongo_client[os.getenv('MONGODB_DB_NAME', 'gesturespeakdb')]
users_collection = db["users"]
rooms_collection = db["rooms"]
predictions_collection = db["predictions"]
logger.info("MongoDB collections initialized")

# Twilio client initialization
try:
    twilio_client = Client(
        os.getenv('TWILIO_ACCOUNT_SID'),
        os.getenv('TWILIO_AUTH_TOKEN')
    )
    logger.info("Successfully initialized Twilio client")
except Exception as e:
    logger.error(f"Twilio initialization error: {e}")
    twilio_client = None


class User(UserMixin):
    def __init__(self, username, user_data=None):
        self.id = username
        self.user_data = user_data or {}

    def get_id(self):
        return str(self.id)

    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False


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


def safe_next_url(candidate):
    """Only allow same-site relative redirects (e.g. '/room/ABC123') after
    login - never an absolute/external URL, which would be an open redirect."""
    if not candidate:
        return None
    if candidate.startswith('/') and not candidate.startswith('//') and '\\' not in candidate:
        return candidate
    return None


def generate_otp():
    """Generate a cryptographically secure 6-digit OTP."""
    return secrets.randbelow(900000) + 100000


def generate_room_code():
    """Generate a unique room code."""
    while True:
        code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        if not rooms_collection.find_one({"room_id": code}):
            return code


def send_otp(phone_number, otp):
    """Send OTP via Twilio."""
    if not twilio_client:
        logger.error("Twilio client not initialized")
        return False

    try:
        twilio_client.messages.create(
            body=f"Your SyncUp verification code is: {otp}",
            from_=os.getenv('TWILIO_PHONE_NUMBER'),
            to=f'+91{phone_number}'
        )
        logger.info(f"OTP sent successfully to {phone_number}")
        return True
    except Exception as e:
        logger.error(f"Failed to send OTP: {e}")
        return False


@app.before_request
def force_https():
    if os.getenv('FLASK_ENV', 'production') == 'development':
        return
    if request.is_secure:
        return
    if request.headers.get('X-Forwarded-Proto', 'http') != 'https':
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url, code=301)


@app.before_request
def refresh_session():
    if current_user.is_authenticated:
        session.permanent = True


# Routes
@app.route('/')
def land():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('land.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    next_url = safe_next_url(request.args.get('next'))

    if current_user.is_authenticated:
        return redirect(next_url or url_for('dashboard'))

    if request.method == 'POST':
        try:
            username = request.form['username']
            password = request.form['password']
            remember = request.form.get('remember') in ('on', 'true', '1', 'yes')
            next_url = safe_next_url(request.form.get('next')) or next_url
            user = users_collection.find_one({"username": username})

            if user and bcrypt.check_password_hash(user['password'], password):
                user_obj = User(username)
                login_user(user_obj, remember=remember)
                users_collection.update_one(
                    {"username": username},
                    {"$set": {
                        "last_login": datetime.utcnow(),
                        "last_ip": request.remote_addr
                    }}
                )
                session['user_id'] = username
                session.permanent = True

                return redirect(next_url or url_for('dashboard'))
            flash("Invalid username or password", "error")
        except Exception as e:
            logger.error(f"Login error: {e}")
            flash("An error occurred during login", "error")

    return render_template('login.html', next_url=next_url)


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
        expiry = datetime.utcnow() + timedelta(minutes=int(os.getenv('OTP_EXPIRY_MINUTES', '5')))

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
            session.pop('phone_verified', None)

        session.pop(f'otp_attempts_{phone_number}', None)

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
            attempts_key = f'otp_attempts_{phone_number}'
            if session.get(attempts_key, 0) >= 5:
                flash("Too many incorrect attempts. Please request a new code.", "error")
                return redirect(url_for('land'))

            entered_otp = request.form['otp']
            user = users_collection.find_one({"phone_number": phone_number})

            if user:
                if datetime.utcnow() > user["otp_expiry"]:
                    flash("OTP expired", "error")
                    return redirect(url_for('land'))
                if str(entered_otp) == str(user["otp"]):
                    session.pop(attempts_key, None)
                    login_user(User(user["username"]))
                    return redirect(url_for('dashboard'))
            else:
                if datetime.utcnow().timestamp() > session.get('temp_expiry', 0):
                    flash("OTP expired", "error")
                    return redirect(url_for('land'))
                if str(entered_otp) == str(session.get('temp_otp')):
                    session.pop(attempts_key, None)
                    session['phone_verified'] = True
                    return redirect(url_for('register'))

            session[attempts_key] = session.get(attempts_key, 0) + 1
            flash("Invalid OTP", "error")
        except Exception as e:
            logger.error(f"OTP verification error: {e}")
            flash("Error verifying OTP", "error")
    return render_template('verify_otp.html', phone_number=phone_number)


@app.route('/register', methods=['GET', 'POST'])
def register():
    # Manual sign-up (name/email/username/password) is the primary path here -
    # both land.html's "Get Started" and login.html's "Create Account" link
    # straight to this route. The phone-OTP flow (/phone_signin ->
    # /verify_otp) also lands here for brand-new numbers and pre-fills
    # phone_number from session['temp_phone'] below, but is not required.
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

            session.pop('phone_verified', None)
            session.pop('temp_phone', None)
            session.pop('temp_otp', None)
            session.pop('temp_expiry', None)

            login_user(User(username))
            return redirect(url_for('dashboard'))
        except Exception as e:
            logger.error(f"Registration error: {e}")
            flash("Error during registration", "error")

    return render_template('register.html')


@app.route('/create-room')
@login_required
def create_room():
    try:
        room_id = generate_room_code()
        current_time = datetime.utcnow()
        require_login = request.args.get('require_login') == '1'

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
                "require_login": require_login
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

        room = rooms_collection.find_one({
            "room_id": room_id,
            "active": True
        })

        if not room:
            flash('Room not found or inactive', 'error')
            return redirect(url_for('dashboard'))

        # Participants are only added once the host actually approves them
        # (see room()/room_lobby()) - just hand off to that gate here rather
        # than admitting them directly.
        return redirect(url_for('room', room_id=room_id))
    except Exception as e:
        logger.error(f"Room joining error: {e}")
        flash("Error joining room", "error")
        return redirect(url_for('dashboard'))


@app.route('/room/<room_id>/lobby')
def room_lobby(room_id):
    try:
        room = rooms_collection.find_one({
            "room_id": room_id,
            "active": True
        })

        if not room:
            flash('Room not found or inactive', 'error')
            return redirect(url_for('land'))

        # Host and anyone already approved this session skip the lobby.
        if current_user.is_authenticated and current_user.id == room['creator']:
            return redirect(url_for('room', room_id=room_id))
        if session.get(f'room_approved_{room_id}'):
            return redirect(url_for('room', room_id=room_id))

        require_login = room.get('settings', {}).get('require_login', False)
        if require_login and not current_user.is_authenticated:
            next_url = url_for('room_lobby', room_id=room_id)
            return redirect(url_for('login', next=next_url))

        return render_template('lobby.html',
                            room_id=room_id,
                            is_authenticated=current_user.is_authenticated,
                            username=current_user.id if current_user.is_authenticated else None)
    except Exception as e:
        logger.error(f"Room lobby error: {e}")
        flash("Error accessing room", "error")
        return redirect(url_for('land'))


@app.route('/room/<room_id>')
def room(room_id):
    try:
        room = rooms_collection.find_one({
            "room_id": room_id,
            "active": True
        })

        if not room:
            flash('Room not found or inactive', 'error')
            return redirect(url_for('dashboard') if current_user.is_authenticated else url_for('land'))

        is_host = current_user.is_authenticated and current_user.id == room['creator']
        is_approved = bool(session.get(f'room_approved_{room_id}'))

        if not (is_host or is_approved):
            return redirect(url_for('room_lobby', room_id=room_id))

        if is_host:
            identity = current_user.id
        elif current_user.is_authenticated:
            identity = current_user.id
        else:
            guest_name = session.get('guest_name')
            guest_id = session.get('guest_id')
            if not guest_name or not guest_id:
                # Approved flag with no guest identity shouldn't normally
                # happen - fall back to the lobby to establish one.
                return redirect(url_for('room_lobby', room_id=room_id))
            identity = f"{guest_name}#{guest_id}"

        if identity not in room['participants']:
            rooms_collection.update_one(
                {"room_id": room_id},
                {
                    "$push": {"participants": identity},
                    "$set": {"last_activity": datetime.utcnow()}
                }
            )
            room['participants'] = room['participants'] + [identity]

        room_link = request.host_url.rstrip('/') + url_for('room', room_id=room_id)

        return render_template('room.html',
                            room_id=room_id,
                            username=identity,
                            room_data=room,
                            room_link=room_link)
    except Exception as e:
        logger.error(f"Room access error: {e}")
        flash("Error accessing room", "error")
        return redirect(url_for('dashboard') if current_user.is_authenticated else url_for('land'))


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


# Wire the video-call / chat signaling handlers onto the single SocketIO
# instance created above (previously this created a second, independent
# SocketIO() bound to the same app, silently orphaning this app's socket
# handlers and half the app's config).
socketio, _consume_approved_sid = init_video_call(app, socketio)


@app.route('/room/<room_id>/confirm', methods=['POST'])
def room_confirm(room_id):
    """The lobby page calls this after the host approves it over the
    socket - a real HTTP POST, not another socket message, so the session
    cookie actually gets set (see call.py's consume_approved_sid for why).
    Only succeeds if the host genuinely approved this exact browser."""
    try:
        data = request.get_json(silent=True) or {}
        sid = data.get('sid')
        if not sid or not _consume_approved_sid(room_id, sid):
            return jsonify({'status': 'error', 'message': 'Not approved'}), 403

        if not current_user.is_authenticated:
            name = str(data.get('name', '')).strip()[:50] or 'Guest'
            if not session.get('guest_id'):
                session['guest_id'] = secrets.token_hex(3)
            session['guest_name'] = name

        session[f'room_approved_{room_id}'] = True
        return jsonify({'status': 'ok'})
    except Exception as e:
        logger.error(f"Room confirm error: {e}")
        return jsonify({'status': 'error', 'message': 'Server error'}), 500


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
        def get_ip():
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(('10.255.255.255', 1))
                IP = s.getsockname()[0]
            except Exception:
                IP = '127.0.0.1'
            finally:
                s.close()
            return IP

        host = '0.0.0.0'
        port = int(os.getenv('PORT', 5000))
        local_ip = get_ip()

        # Browsers only allow camera/microphone access on a "secure context":
        # https://, or http:// on localhost/127.0.0.1 specifically. Any other
        # host over plain http - e.g. the LAN IP printed below - gets no
        # camera/mic access at all, no matter what the page asks for. Serve
        # over TLS using the cert already checked into the repo so the LAN
        # URL actually works for other devices, and so a browser that
        # auto-upgrades to https/wss (many do) hits a server that's actually
        # listening for TLS instead of sending it a raw HTTP 400.
        # Only self-sign locally. A real deployment (Render, etc.) terminates
        # HTTPS at its own edge/proxy and forwards plain HTTP to this process -
        # wrapping our socket in this self-signed cert there too would make
        # the platform's own proxy fail to talk to us.
        is_local_dev = os.getenv('FLASK_ENV', 'production') == 'development'
        cert_path = os.getenv('SSL_CERT_PATH', 'server.crt')
        key_path = os.getenv('SSL_KEY_PATH', 'server.key')
        ssl_kwargs = {}
        scheme = 'http'
        if is_local_dev and os.path.exists(cert_path) and os.path.exists(key_path):
            # threading mode runs on Werkzeug's run_simple(), which takes
            # ssl_context=(certfile, keyfile) - not the certfile/keyfile
            # kwargs eventlet's wrap_ssl() used.
            ssl_kwargs = {'ssl_context': (cert_path, key_path)}
            scheme = 'https'

        print("\n" + "="*50)
        print("Server Running!")
        print("="*50)
        print(f"\nAccess URLs:")
        print(f"Local computer: {scheme}://localhost:{port}")
        print(f"Other devices : {scheme}://{local_ip}:{port}")
        if scheme == 'https':
            print("\n(Self-signed certificate - your browser will warn once;")
            print(" accept/continue to proceed. Required for camera/mic access")
            print(" from any device other than localhost.)")
        elif is_local_dev:
            print(f"\nWARNING: no {cert_path}/{key_path} found - running plain HTTP.")
            print("Camera/microphone will only work at http://localhost, not the LAN URL.")
        else:
            print("\nRunning plain HTTP - expected behind a platform proxy/load")
            print("balancer (Render, etc.) that terminates HTTPS for you.")
        print("\nImportant Notes:")
        print("1. Make sure all devices are on the same network")
        print("2. Allow camera/microphone permissions when prompted")
        print("3. If using mobile, enable desktop site in browser")
        print("="*50 + "\n")

        socketio.start_background_task(cleanup_inactive_rooms)
        socketio.run(
            app,
            host=host,
            port=port,
            debug=False,
            allow_unsafe_werkzeug=True,
            **ssl_kwargs
        )
    except Exception as e:
        print(f"Server startup error: {e}")
        raise
