---

# GestureSpeak: Bridging Communication Gaps with AI-Powered Sign Language Translation and Real-Time Video Conferencing

## **Overview**
GestureSpeak is an AI-powered platform designed to provide real-time sign language detection and translation. This application bridges communication gaps by integrating advanced deep learning models with a user-friendly interface. The system processes live video streams, detects sign language using YOLOv5, and translates it into text in real-time.

---

## **Features**
- **Real-Time Sign Detection**: Utilizes YOLOv5 for detecting and interpreting sign language with high accuracy.
- **Video Conferencing**: Supports seamless communication between users.
- **Secure Authentication**: Provides OTP-based secure user authentication.
- **Intuitive Interface**: Features a clean, professional UI for easy navigation.
- **Low Latency**: Enables real-time interaction with minimal delay.

---

## **Directory Structure**
```
manoharreddyvoladri-gesture_speak_app/
├── _.crt
├── app.py             # Main application file
├── best.pt            # Pre-trained YOLOv5 model
├── call.py            # Video conferencing functionality
├── realtime.py        # Real-time sign detection logic
├── requirements.txt   # Python dependencies
├── server.crt         # SSL certificate
├── server.key         # SSL private key
├── vercel.json        # Deployment configuration
├── Reports/           # Project-related documents
│   ├── FINAL REVIEW.pptx
│   ├── Project meetings.xlsx
│   ├── REVIEW - 1.pptx
│   ├── REVIEW.pptx
│   └── base papers/
├── static/            # Static assets
│   ├── css/
│   │   ├── dashboard.css
│   │   ├── room.css
│   │   └── style.css
│   ├── images/
│   └── js/
│       ├── call.js
│       └── main.js
├── templates/         # HTML templates
│   ├── dashboard.html
│   ├── error.html
│   ├── index.html
│   ├── index1.html
│   ├── land.html
│   ├── login.html
│   ├── register.html
│   ├── room.html
│   └── verify_otp.html
└── test.py
```

---

## **Installation**

### **1. Prerequisites**
- Python 3.x installed on your system.
- `pip` (Python package installer) configured.
- A virtual environment (optional but recommended).

### **2. Clone the Repository**
```bash
git clone https://github.com/username/manoharreddyvoladri-gesture_speak_app.git
cd manoharreddyvoladri-gesture_speak_app
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
   - Register and log in using the provided forms.
   - Enter the OTP for secure authentication.

4. **Sign Language Detection**:
   - Navigate to the video conferencing feature.
   - Signs will be detected and translated into text in real-time.

5. **Real-Time Communication**:
   - Use the `call.py` script to enable video calls between users.

---

## **Dataset**
- **Hand Landmark Dataset**: Contains 6,500 images of American Sign Language (ASL) hand signs with 21 keypoints tracked for each hand pose.
- **Model**: Trained with YOLOv5 for high-accuracy real-time sign detection.

---

## **Technologies Used**
- **Backend**: Flask for handling server-side logic and routing.
- **Deep Learning**: YOLOv5 for object detection and VGG16 for classification.
- **Database**: MongoDB for user management.
- **Video Conferencing**: WebRTC integrated through custom scripts.

---

## **Deployment**
The application includes a `vercel.json` configuration for deployment on platforms like Vercel. Ensure all dependencies and configurations are properly set before deployment.

---

## **Conclusion**
GestureSpeak successfully demonstrates the integration of AI with real-time communication tools to enhance accessibility for the deaf and hard of hearing community. With its high accuracy, low latency, and user-friendly interface, GestureSpeak paves the way for inclusive digital interactions.

---

Let me know if you need further modifications! 🚀
