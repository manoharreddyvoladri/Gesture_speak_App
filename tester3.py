from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
import cv2
import numpy as np
from tensorflow.keras.models import load_model
from twilio.rest import Client
import random
from pymongo import MongoClient
from datetime import datetime, timedelta
import base64

app = Flask(__name__)
app.secret_key = 'your_secret_key'

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'land'
bcrypt = Bcrypt(app)

mongo_client = MongoClient("mongodb+srv://gesturespeakdb:gesturespeakdb@gsusers.8wjxr.mongodb.net/")
db = mongo_client["gesturespeakdb"]
users_collection = db["users"]

account_sid = 'ACbc271c75232fa7cba0188f1b3f8618a2'
auth_token = 'a7f00c3cff83a88340e3eac3fcd12693'
client = Client(account_sid, auth_token)

model = load_model('asl_model1.h5')

class_map = ["A", "B", "C", "D", "E", "F", "G", "H", "Hello", "I", "I Love You",
             "J", "K", "L", "M", "N", "No", "O", "P", "Q", "R", "S", "Space", 
             "T", "U", "V", "W", "X", "Y", "Yes", "Z"]

class User(UserMixin):
    def __init__(self, username):
        self.id = username

@login_manager.user_loader
def load_user(username):
    user_data = users_collection.find_one({"username": username})
    if user_data:
        return User(user_data["username"])
    return None

def preprocess_frame(frame):
    resized = cv2.resize(frame, (224, 224))
    normalized = resized / 255.0
    return np.expand_dims(normalized, axis=0)

@app.route('/')
def land():
    return render_template('land.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = users_collection.find_one({"username": username})

        if user and bcrypt.check_password_hash(user['password'], password):
            login_user(User(username))
            return redirect(url_for('dashboard'))
        flash("Invalid username or password", "error")
    
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/phone_signin', methods=['POST'])
def phone_signin():
    phone_number = request.form['phone_number']
    user = users_collection.find_one({"phone_number": phone_number})
    otp = random.randint(100000, 999999)
    expiry = datetime.now() + timedelta(minutes=5)

    if user:
        users_collection.update_one({"phone_number": phone_number}, {"$set": {"otp": otp, "otp_expiry": expiry}})
    else:
        session['temp_phone'] = phone_number
        session['temp_otp'] = otp
        session['temp_expiry'] = expiry.timestamp()
    
    client.messages.create(body=f"Your OTP is {otp}", from_='+17407600895', to=f'+91{phone_number}')
    return redirect(url_for('verify_otp', phone_number=phone_number))

@app.route('/verify_otp/<phone_number>', methods=['GET', 'POST'])
def verify_otp(phone_number):
    if request.method == 'POST':
        entered_otp = request.form['otp']
        user = users_collection.find_one({"phone_number": phone_number})

        if user:
            if datetime.now() > user["otp_expiry"]:
                flash("OTP expired", "error")
                return redirect(url_for('land'))
            if int(entered_otp) == user["otp"]:
                login_user(User(user["username"]))
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
        
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        phone_number = session.get('temp_phone')

        users_collection.insert_one({
            "name": name,
            "email": email,
            "username": username,
            "password": hashed_password,
            "phone_number": phone_number,
            "verified": True
        })
        
        login_user(User(username))
        return redirect(url_for('dashboard'))
    
    return render_template('register.html')

@app.route('/index')
@login_required
def index():
    return render_template('index.html')

@app.route('/predict', methods=['POST'])
@login_required
def predict():
    data = request.get_json()
    image_data = data['image'].split(',')[1]
    image_bytes = base64.b64decode(image_data)
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    img = preprocess_frame(img)

    prediction = model.predict(img)
    predicted_class = class_map[np.argmax(prediction)]
    return jsonify({'prediction': predicted_class})

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('land'))

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