class VideoCall {
    constructor(roomId, username) {
        this.roomId = roomId;
        this.username = username;
        this.peers = {};
        this.localStream = null;
        this.socket = io();
        this.isVideoEnabled = true;
        this.isAudioEnabled = true;
        this.isPredictionEnabled = false;
        this.predictionInterval = null;
        this.localVideoAdded = false;
        
        // Initialize everything after socket connection
        this.socket.on('connect', () => {
            console.log('Socket connected, initializing...');
            this.initializeSocket();
            this.initializeMedia().catch(err => {
                console.error('Failed to initialize media:', err);
                alert('Failed to access camera/microphone. Please check permissions.');
            });
        });

        // Handle connection errors
        this.socket.on('connect_error', (error) => {
            console.error('Socket connection error:', error);
            alert('Connection error. Please refresh the page.');
        });
    }

    async initializeMedia() {
        try {
            console.log('Requesting media devices...');
            this.localStream = await navigator.mediaDevices.getUserMedia({
                video: {
                    width: { ideal: 1280 },
                    height: { ideal: 720 },
                    frameRate: { ideal: 30 }
                },
                audio: true
            });
            console.log('Media devices obtained successfully');
            
            const videoGrid = document.getElementById('video-grid');
            if (!videoGrid) {
                throw new Error('Video grid element not found');
            }
            
            const videoContainer = this.createVideoContainer('local', true);
            const video = videoContainer.querySelector('video');
            video.srcObject = this.localStream;
            video.id = 'localVideo';
            
            await video.play();
            videoGrid.appendChild(videoContainer);
            
            this.joinRoom();
            if (this.isPredictionEnabled) {
                this.startPredictionInterval();
            }
        } catch (err) {
            console.error('Media initialization error:', err);
            throw err;
        }
    }

    initializeSocket() {
        // Connection events
        this.socket.on('error', (error) => {
            console.error('Socket error:', error);
            alert(error.message || 'An error occurred');
        });

        // Room events
        this.socket.on('user_joined', this.handleUserJoined.bind(this));
        this.socket.on('user_left', this.handleUserLeft.bind(this));
        
        // WebRTC events
        this.socket.on('offer', this.handleOffer.bind(this));
        this.socket.on('answer', this.handleAnswer.bind(this));
        this.socket.on('ice_candidate', this.handleIceCandidate.bind(this));
        this.socket.on('sign_prediction', this.handleSignPrediction.bind(this));
    }

    createVideoContainer(username, isLocal = false) {
        const videoContainer = document.createElement('div');
        videoContainer.className = 'video-container';
        videoContainer.id = `video-${username}`;
        
        const video = document.createElement('video');
        video.autoplay = true;
        video.playsInline = true;
        if (isLocal) {
            video.muted = true;
        }

        const overlay = document.createElement('div');
        overlay.className = 'video-overlay';
        
        const nameTag = document.createElement('div');
        nameTag.className = 'name-tag';
        nameTag.textContent = isLocal ? `${username} (You)` : username;
        
        overlay.appendChild(nameTag);
        videoContainer.appendChild(video);
        videoContainer.appendChild(overlay);
        
        return videoContainer;
    }

    startPredictionInterval() {
        if (this.predictionInterval) {
            clearInterval(this.predictionInterval);
        }
        
        this.predictionInterval = setInterval(() => {
            if (this.isPredictionEnabled) {
                this.captureAndPredict();
            }
        }, 1000);
    }

    async captureAndPredict() {
        const video = document.getElementById('localVideo');
        if (!video) return;

        const canvas = document.createElement('canvas');
        canvas.width = 224;
        canvas.height = 224;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        
        try {
            const response = await fetch('/predict', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    image: canvas.toDataURL('image/jpeg', 0.8)
                })
            });

            if (!response.ok) throw new Error('Prediction request failed');
            
            const data = await response.json();
            if (data.prediction) {
                this.addPrediction(this.username, data.prediction);
                this.socket.emit('sign_prediction', {
                    room: this.roomId,
                    username: this.username,
                    prediction: data.prediction
                });
            }
        } catch (err) {
            console.error('Prediction error:', err);
        }
    }

    addPrediction(username, prediction) {
        const container = document.getElementById('predictions-container');
        if (!container) return;

        const predictionElement = document.createElement('div');
        predictionElement.className = 'prediction-item';
        const timestamp = new Date().toLocaleTimeString();

        predictionElement.innerHTML = `
            <div class="user-avatar">${username[0].toUpperCase()}</div>
            <div class="prediction-content">
                <div class="prediction-user">${username}</div>
                <div class="prediction-text">${prediction}</div>
                <div class="prediction-time">${timestamp}</div>
            </div>
        `;
        
        container.appendChild(predictionElement);
        container.scrollTop = container.scrollHeight;
        
        while (container.children.length > 10) {
            container.removeChild(container.firstChild);
        }
    }

    toggleVideo() {
        if (!this.localStream) return false;
        
        this.isVideoEnabled = !this.isVideoEnabled;
        this.localStream.getVideoTracks().forEach(track => {
            track.enabled = this.isVideoEnabled;
        });
        return this.isVideoEnabled;
    }

    toggleAudio() {
        if (!this.localStream) return false;
        
        this.isAudioEnabled = !this.isAudioEnabled;
        this.localStream.getAudioTracks().forEach(track => {
            track.enabled = this.isAudioEnabled;
        });
        return this.isAudioEnabled;
    }

    togglePrediction() {
        this.isPredictionEnabled = !this.isPredictionEnabled;
        if (this.isPredictionEnabled) {
            this.startPredictionInterval();
        } else if (this.predictionInterval) {
            clearInterval(this.predictionInterval);
        }
        return this.isPredictionEnabled;
    }

    joinRoom() {
        console.log('Joining room:', this.roomId);
        this.socket.emit('join', {
            room: this.roomId,
            username: this.username
        });
    }

    async createPeerConnection(targetUsername) {
        const pc = new RTCPeerConnection({
            iceServers: [
                { urls: 'stun:stun.l.google.com:19302' },
                {
                    urls: 'turn:numb.viagenie.ca',
                    username: 'webrtc@live.com',
                    credential: 'muazkh'
                }
            ]
        });

        // Add local tracks to the connection
        this.localStream.getTracks().forEach(track => {
            pc.addTrack(track, this.localStream);
        });

        // Handle incoming tracks
        pc.ontrack = (event) => {
            this.addVideoStream(targetUsername, event.streams[0]);
        };

        // Handle ICE candidates
        pc.onicecandidate = (event) => {
            if (event.candidate) {
                this.socket.emit('ice_candidate', {
                    room: this.roomId,
                    candidate: event.candidate,
                    target: targetUsername,
                    username: this.username
                });
            }
        };

        return pc;
    }

    async handleUserJoined(data) {
        console.log('User joined:', data.username);
        try {
            const pc = await this.createPeerConnection(data.username);
            this.peers[data.username] = pc;
            
            const offer = await pc.createOffer();
            await pc.setLocalDescription(offer);
            
            this.socket.emit('offer', {
                room: this.roomId,
                target: data.username,
                username: this.username,
                sdp: offer
            });
        } catch (err) {
            console.error('Error handling user joined:', err);
        }
    }

    async handleOffer(data) {
        console.log('Received offer from:', data.username);
        try {
            const pc = await this.createPeerConnection(data.username);
            this.peers[data.username] = pc;
            
            await pc.setRemoteDescription(new RTCSessionDescription(data.sdp));
            const answer = await pc.createAnswer();
            await pc.setLocalDescription(answer);
            
            this.socket.emit('answer', {
                room: this.roomId,
                target: data.username,
                username: this.username,
                sdp: answer
            });
        } catch (err) {
            console.error('Error handling offer:', err);
        }
    }

    async handleAnswer(data) {
        try {
            const pc = this.peers[data.username];
            if (pc) {
                await pc.setRemoteDescription(new RTCSessionDescription(data.sdp));
            }
        } catch (err) {
            console.error('Error handling answer:', err);
        }
    }

    async handleIceCandidate(data) {
        try {
            const pc = this.peers[data.username];
            if (pc) {
                await pc.addIceCandidate(new RTCIceCandidate(data.candidate));
            }
        } catch (err) {
            console.error('Error handling ICE candidate:', err);
        }
    }

    handleUserLeft(data) {
        console.log('User left:', data.username);
        if (this.peers[data.username]) {
            this.peers[data.username].close();
            delete this.peers[data.username];
        }

        const videoElement = document.getElementById(`video-${data.username}`);
        if (videoElement) {
            videoElement.remove();
        }
    }

    handleSignPrediction(data) {
        this.addPrediction(data.username, data.prediction);
    }

    leaveRoom() {
        // Stop all tracks
        if (this.localStream) {
            this.localStream.getTracks().forEach(track => track.stop());
        }
        
        // Close all peer connections
        Object.values(this.peers).forEach(pc => pc.close());
        this.peers = {};
        
        // Clear prediction interval
        if (this.predictionInterval) {
            clearInterval(this.predictionInterval);
        }
        
        // Emit leave event
        this.socket.emit('leave', {
            room: this.roomId,
            username: this.username
        });
        
        // Disconnect socket
        this.socket.disconnect();
        
        // Redirect to dashboard
        window.location.href = '/dashboard';
    }
}

// Initialize the video call when page loads
document.addEventListener('DOMContentLoaded', () => {
    if (typeof ROOM_ID === 'undefined' || typeof USERNAME === 'undefined') {
        console.error('Room ID or Username not defined');
        return;
    }

    // Create global instance
    window.videoCall = new VideoCall(ROOM_ID, USERNAME);

    // Set up control buttons
    const controls = {
        video: document.getElementById('toggle-video'),
        audio: document.getElementById('toggle-audio'),
        prediction: document.getElementById('toggle-prediction'),
        leave: document.getElementById('leave-room')
    };

    if (controls.video) {
        controls.video.addEventListener('click', function() {
            const isEnabled = window.videoCall.toggleVideo();
            this.innerHTML = isEnabled ? 
                '<i class="fas fa-video"></i>' : 
                '<i class="fas fa-video-slash"></i>';
            this.classList.toggle('active', isEnabled);
        });
    }

    if (controls.audio) {
        controls.audio.addEventListener('click', function() {
            const isEnabled = window.videoCall.toggleAudio();
            this.innerHTML = isEnabled ? 
                '<i class="fas fa-microphone"></i>' : 
                '<i class="fas fa-microphone-slash"></i>';
            this.classList.toggle('active', isEnabled);
        });
    }

    if (controls.prediction) {
        controls.prediction.addEventListener('click', function() {
            const isEnabled = window.videoCall.togglePrediction();
            this.classList.toggle('active', isEnabled);
        });
    }

    if (controls.leave) {
        controls.leave.addEventListener('click', () => {
            if (window.videoCall) {
                window.videoCall.leaveRoom();
            }
        });
    }
});