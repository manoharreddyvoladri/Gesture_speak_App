from flask import Flask, render_template, request, jsonify
import cv2
import numpy as np
from tensorflow.keras.models import load_model
import base64

app = Flask(__name__)

# Load the trained model
model = load_model('asl_model.h5')

# Dictionary to map class indices to ASL letters/numbers
class_map = {0: '0', 1: '1', 2: '2', 3: '3', 4: '4', 5: '5', 6: '6', 7: '7', 8: '8', 9: '9',
             10: 'A', 11: 'B', 12: 'C', 13: 'D', 14: 'E', 15: 'F', 16: 'G', 17: 'H', 18: 'I',
             19: 'J', 20: 'K', 21: 'L', 22: 'M', 23: 'N', 24: 'O', 25: 'P', 26: 'Q', 27: 'R',
             28: 'S', 29: 'T', 30: 'U', 31: 'V', 32: 'W', 33: 'X', 34: 'Y', 35: 'Z'}

# class_map = [
#     "A", "B", "C", "D", "E", "F", "G", "H", "Hello", "I", "I Love You",
#     "J", "K", "L", "M", "N", "No", "O", "P", "Q", "R", "S","Space", "T", "U",
#     "V", "W", "X", "Y", "Yes", "Z",
# ]

def preprocess_frame(frame):
    resized = cv2.resize(frame, (224, 224))
    normalized = resized / 255.0
    return np.expand_dims(normalized, axis=0)


# def preprocess_frame(frame):
#     resized = cv2.resize(frame, (64, 64))
#     normalized = resized / 255.0
#     return np.expand_dims(normalized, axis=0)

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/predict', methods=['POST'])
def predict():
    image_data = request.json['image']
    image_data = image_data.split(',')[1]
    image_data = base64.b64decode(image_data)
    
    nparr = np.frombuffer(image_data, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    preprocessed_frame = preprocess_frame(frame)
    print(f"Preprocessed frame shape: {preprocessed_frame.shape}")
    
    try:
        prediction = model.predict(preprocessed_frame)
        predicted_class = np.argmax(prediction)
        predicted_sign = class_map[predicted_class]
        print(f"Predicted class: {predicted_class}, Predicted sign: {predicted_sign}")
        return jsonify({'prediction': predicted_sign})
    except Exception as e:
        print(f"Error during prediction: {str(e)}")
        return jsonify({'error': str(e)}), 500



if __name__ == '__main__':
    app.run(debug=True)

