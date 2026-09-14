---

# SyncUp: Fast, Professional Video Calls & Chat

## **Overview**
SyncUp is a lightweight video-calling and chat platform. Create a room, share the code, and talk face-to-face with live text chat alongside the call - no plugins, no heavy client, just a browser.

---

## **Features**
- **Video Conferencing**: Multi-participant rooms over WebRTC with automatic reconnect handling.
- **Live Chat**: Real-time messaging inside every call room.
- **Secure Authentication**: Password login plus OTP-based phone sign-in.
- **Call Controls**: Camera/microphone toggles, device switching, and adjustable video quality.
- **Low Latency**: Direct peer-to-peer media - the server only handles signaling.

---

## **Directory Structure**
```
syncup/
├── app.py             # Main application - routes, auth, rooms
├── call.py            # SocketIO signaling (WebRTC + chat)
├── requirements.txt   # Python dependencies
├── server.crt         # SSL certificate
├── server.key         # SSL private key
├── vercel.json        # Deployment configuration
├── static/            # Static assets
│   ├── css/
│   │   ├── syncup.css   # Shared design tokens
│   │   ├── dashboard.css
│   │   ├── room.css
│   │   └── style.css
│   ├── images/
│   └── js/
│       └── call.js
├── templates/         # HTML templates
│   ├── dashboard.html
│   ├── error.html
│   ├── land.html
│   ├── login.html
│   ├── register.html
│   ├── room.html
│   └── verify_otp.html
```

---

## **Installation**

### **1. Prerequisites**
- Python 3.x installed on your system.
- `pip` (Python package installer) configured.
- A virtual environment (optional but recommended).

### **2. Clone the Repository**
```bash
git clone https://github.com/manoharreddyvoladri/Gesture_speak_App.git
cd Gesture_speak_App
```

### **3. Install Dependencies**
Create a virtual environment (optional):
```bash
python -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate
```

Install the required packages:
```bash
pip install -r requirements.txt
```

Create a `.env` file with `SECRET_KEY`, `MONGODB_URI`, and Twilio credentials before running.

---

## **Usage**

1. Run the main application:
   ```bash
   python app.py
   ```

2. Open the application in your browser:
   ```
   http://localhost:5000
   ```

3. **User Authentication**:
   - Register and log in using the provided forms, or sign in with a phone number and OTP.

4. **Start a Call**:
   - Create a room from the dashboard and share the room code with others.
   - Toggle camera/mic, switch devices, or adjust video quality from in-call settings.
   - Chat with everyone in the room from the side panel.

---

## **Technologies Used**
- **Backend**: Flask + Flask-SocketIO (eventlet) for server-side logic and real-time signaling.
- **Database**: MongoDB for user accounts and room state.
- **Video Conferencing**: WebRTC (peer-to-peer) with Socket.IO signaling.
- **Auth**: Flask-Login, Flask-Bcrypt, Twilio for OTP delivery.

---

## **Deployment**
The application includes a `vercel.json` configuration for deployment on platforms like Vercel. Ensure all dependencies and configurations are properly set before deployment.

---
