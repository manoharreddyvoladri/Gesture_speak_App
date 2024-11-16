from flask import Flask, render_template, request, redirect, url_for, flash
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, EmailField
from wtforms.validators import DataRequired, Length, Email, ValidationError
from flask_login import login_user, LoginManager, login_required, current_user, logout_user, UserMixin
from flask_bcrypt import Bcrypt
from pymongo import MongoClient
from datetime import datetime
import os
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log')
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', "my-secrets")
app.template_folder = os.path.abspath('templates11')  # Fixed template folder name

# Initialize MongoDB with error handling
try:
    mongo_client = MongoClient(os.getenv('MONGODB_URI', 'mongodb+srv://gesturespeakdb:gesturespeakdb@gsusers.8wjxr.mongodb.net/'))
    mongo_client.admin.command('ping')
    db = mongo_client.gesturespeakdb
    users_collection = db.users
    logger.info("Successfully connected to MongoDB")
except Exception as e:
    logger.error(f"MongoDB connection error: {e}")
    raise

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

# Initialize Bcrypt
bcrypt = Bcrypt(app)

class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data.get('_id', ''))
        self.email = user_data.get('email', '')
        self.first_name = user_data.get('first_name', '')
        self.last_name = user_data.get('last_name', '')
        self.username = user_data.get('username', '')

    def get_id(self):
        return self.username

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False

@login_manager.user_loader
def load_user(username):
    if not username:
        return None
    user_data = users_collection.find_one({"username": username})
    if user_data:
        return User(user_data)
    return None

class RegistrationForm(FlaskForm):
    email = EmailField(label='Email', validators=[
        DataRequired(),
        Email(message="Please enter a valid email address")
    ])
    first_name = StringField(label="First Name", validators=[
        DataRequired(),
        Length(min=2, max=50)
    ])
    last_name = StringField(label="Last Name", validators=[
        DataRequired(),
        Length(min=2, max=50)
    ])
    username = StringField(label="Username", validators=[
        DataRequired(),
        Length(min=4, max=20)
    ])
    password = PasswordField(label="Password", validators=[
        DataRequired(),
        Length(min=8, max=20)
    ])

    def validate_username(self, username):
        existing_user = users_collection.find_one({"username": username.data})
        if existing_user:
            raise ValidationError("Username already exists")

    def validate_email(self, email):
        existing_user = users_collection.find_one({"email": email.data.lower()})
        if existing_user:
            raise ValidationError("Email already registered")

class LoginForm(FlaskForm):
    email = EmailField(label='Email', validators=[DataRequired(), Email()])
    password = PasswordField(label="Password", validators=[DataRequired()])

@app.route("/")
def home():
    return redirect(url_for("login"))

@app.route("/login", methods=["POST", "GET"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    
    form = LoginForm()
    if request.method == "POST" and form.validate_on_submit():
        email = form.email.data.lower()
        password = form.password.data
        user_data = users_collection.find_one({"email": email})
        
        if user_data and bcrypt.check_password_hash(user_data['password'], password):
            user = User(user_data)
            login_user(user)
            
            # Update last login time
            users_collection.update_one(
                {"email": email},
                {"$set": {"last_login": datetime.utcnow()}}
            )
            
            return redirect(url_for("dashboard"))
        flash("Invalid email or password", "error")

    return render_template("login.html", form=form)

@app.route("/logout", methods=["GET"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out successfully!", "info")
    return redirect(url_for("login"))

@app.route("/register", methods=["POST", "GET"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
        
    form = RegistrationForm()
    if request.method == "POST" and form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        
        new_user = {
            "email": form.email.data.lower(),
            "first_name": form.first_name.data.strip(),
            "last_name": form.last_name.data.strip(),
            "username": form.username.data,
            "password": hashed_password,
            "created_at": datetime.utcnow(),
            "last_login": datetime.utcnow()
        }
        
        try:
            users_collection.insert_one(new_user)
            flash("Account created Successfully! You can now log in.", "success")
            return redirect(url_for("login"))
        except Exception as e:
            flash("An error occurred during registration. Please try again.", "error")
            logger.error(f"Registration error: {e}")

    return render_template("register.html", form=form)

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", 
                         first_name=current_user.first_name, 
                         last_name=current_user.last_name)

@app.route("/meeting")
@login_required
def meeting():
    return render_template("meeting.html", username=current_user.username)

@app.route("/join", methods=["GET", "POST"])
@login_required
def join():
    if request.method == "POST":
        room_id = request.form.get("roomID")
        return redirect(f"/meeting?roomID={room_id}")

    return render_template("join.html")

if __name__ == '__main__':
    try:
        import socket
        from flask_socketio import SocketIO

        # Initialize SocketIO
        socketio = SocketIO(
            app,
            cors_allowed_origins="*",
            ping_timeout=60,
            ping_interval=25,
            async_mode='eventlet',
            logger=True,
            engineio_logger=True
        )

        def get_ip():
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(('8.8.8.8', 80))
                IP = s.getsockname()[0]
            except Exception:
                IP = '127.0.0.1'
            finally:
                s.close()
            return IP

        host = '0.0.0.0'
        port = 5002
        local_ip = get_ip()

        print("\n" + "="*60)
        print("GestureSpeak Server Starting!".center(60))
        print("="*60)
        print("\nServer Configuration:")
        print(f"Host: {host}")
        print(f"Port: {port}")
        print("\nAccess URLs:")
        print(f"→ Local computer: http://localhost:{port}")
        print(f"→ Other devices : http://{local_ip}:{port}")

        # Check if port is available
        test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            test_socket.bind((host, port))
            test_socket.close()
        except socket.error:
            logger.error(f"Port {port} is already in use!")
            raise

        logger.info("Server starting...")
        socketio.run(
            app,
            host=host,
            port=port,
            debug=False,
            allow_unsafe_werkzeug=True,
            use_reloader=False
        )

    except socket.error as e:
        logger.error(f"Network Error: {e}")
        raise
    except Exception as e:
        logger.error(f"Server Startup Error: {e}")
        raise
    finally:
        logger.info("Server shutdown complete.")