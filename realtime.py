from flask import Flask, render_template, Response, jsonify
import cv2
import numpy as np
from ultralytics import YOLO
import time
from datetime import datetime
import threading
import queue
import os

app = Flask(__name__)
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

@app.route('/')
def index():
    try:
        return render_template('index1.html')
    except Exception as e:
        return f"Error: {str(e)}", 500

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

if __name__ == '__main__':
    if not os.path.exists(app.template_folder):
        os.makedirs(app.template_folder)
    app.run(debug=False, threaded=True, port=5001)