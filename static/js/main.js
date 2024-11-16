document.addEventListener('DOMContentLoaded', function() {
    // Video elements setup
    const video = document.getElementById('video');
    const canvas = document.getElementById('canvas');
    const predictionElement = document.getElementById('prediction');

    // Function to access user's camera and display video
    if (video && canvas) {
        const ctx = canvas.getContext('2d');
        canvas.width = 640;
        canvas.height = 480;

        navigator.mediaDevices.getUserMedia({
            video: {
                width: 640,
                height: 480
            }
        })
        .then(stream => {
            video.srcObject = stream;
            video.play();
        })
        .catch(err => {
            console.error("Error accessing the camera:", err);
            alert("Unable to access the camera. Please make sure you have granted camera permissions.");
        });

        // Capture frame and send it to the server for prediction
        function captureFrame() {
            if (video.readyState === video.HAVE_ENOUGH_DATA) {
                ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                const imageData = canvas.toDataURL('image/jpeg', 0.8);

                fetch('/predict', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ image: imageData }),
                })
                .then(response => {
                    if (!response.ok) {
                        throw new Error('Network response was not ok');
                    }
                    return response.json();
                })
                .then(data => {
                    if (predictionElement) {
                        predictionElement.textContent = data.prediction;
                    }
                })
                .catch(error => {
                    console.error('Error:', error);
                });
            }
        }

        setInterval(captureFrame, 1000);
    }

    // Flash message auto-hide
    const flashMessages = document.querySelectorAll('.flash');
    flashMessages.forEach(message => {
        setTimeout(() => {
            message.style.opacity = '0';
            setTimeout(() => message.remove(), 300);
        }, 3000);
    });
    // Room functionality
    const socket = io();

    // Create room function
    async function createRoom() {
        try {
            const response = await fetch('/create-room');
            const data = await response.json();
            
            if (data.room_id) {
                console.log('Room created:', data.room_id);
                window.location.href = `/room/${data.room_id}`;
            } else {
                alert('Failed to create room');
            }
        } catch (error) {
            console.error('Error creating room:', error);
            alert('Error creating room. Please try again.');
        }
    }

    // Join room function
    function joinRoom() {
        const roomCodeInput = document.getElementById('room_id');
        
        if (!roomCodeInput) {
            console.error("Room code input element not found!");
            return;
        }
        
        const roomCode = roomCodeInput.value.trim();
        
        if (!roomCode) {
            alert('Please enter a room code');
            return;
        }

        // Create and submit form
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = '/join-room';

        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'room_id';
        input.value = roomCode;

        form.appendChild(input);
        document.body.appendChild(form);
        form.submit();
    }

    // Room code input validation
    const roomCodeInput = document.getElementById('room_id');
    if (roomCodeInput) {
        roomCodeInput.addEventListener('input', () => {
            roomCodeInput.value = roomCodeInput.value.replace(/[^a-zA-Z0-9]/g, '');
            if (roomCodeInput.value.length > 15) {
                roomCodeInput.value = roomCodeInput.value.slice(0, 15);
            }
        });
    }

    // Setup button event listeners
    const createRoomBtn = document.querySelector('.create-room-btn');
    if (createRoomBtn) {
        createRoomBtn.addEventListener('click', createRoom);
    }

    const joinButton = document.querySelector('button[onclick="joinRoom()"]');
    if (joinButton) {
        joinButton.removeAttribute('onclick');
        joinButton.addEventListener('click', joinRoom);
    }



});
