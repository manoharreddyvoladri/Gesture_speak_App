// Usernames, chat text and predictions all come from other users over the
// socket - escape before inserting via innerHTML to avoid stored XSS.
function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
}

const peerConfiguration = {
    iceServers: [
        {
            urls: [
                'stun:stun.l.google.com:19302',
                'stun:stun1.l.google.com:19302',
                'stun:stun2.l.google.com:19302',
                'stun:stun3.l.google.com:19302',
                'stun:stun4.l.google.com:19302'
            ]
        },
        {
            urls: 'turn:numb.viagenie.ca',
            username: 'webrtc@live.com',
            credential: 'muazkh'
        }
    ],
    iceCandidatePoolSize: 10,
    bundlePolicy: 'max-bundle',
    rtcpMuxPolicy: 'require'
};

class VideoCall {
    constructor(roomId, username) {
        this.roomId = roomId;
        this.username = username;
        this.peers = {};
        this.localStream = null;
        this.socket = io({
            transports: ['websocket'],
            upgrade: false,
            reconnection: true,
            reconnectionAttempts: Infinity,
            reconnectionDelay: 1000,
            reconnectionDelayMax: 5000,
            timeout: 20000
        });

        this.isVideoEnabled = true;
        this.isAudioEnabled = true;
        this.isPredictionEnabled = false;
        this.predictionInterval = null;
        this.debug = true;
        this.participants = new Set([this.username]);
        this.videoDevices = [];
        this.currentCameraIndex = 0;
        this.renderParticipants();

        // Initialize everything
    this.initializeSocketEvents();
    // Initialize settings when media is ready
    this.initializeMedia().then(() => {
        this.initializeSettings();
    }).catch(err => {
        console.error('Media initialization error:', err);
        this.showError('Failed to access camera/microphone. Please check permissions.');
    });
}

    async initializeMedia() {
        try {
            this.localStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                },
                video: {
                    width: { ideal: 1280 },
                    height: { ideal: 720 },
                    frameRate: { ideal: 30 },
                    facingMode: 'user'
                }
            });

            await this.displayLocalVideo();
            return true;
        } catch (error) {
            console.error('Media initialization error:', error);
            throw error;
        }
    }


    async displayLocalVideo() {
        const videoGrid = document.getElementById('video-grid');
        if (!videoGrid) return;

        const videoContainer = this.createVideoContainer(this.username, true);
        const video = videoContainer.querySelector('video');
        video.srcObject = this.localStream;
        video.id = 'localVideo';

        try {
            await video.play();
            videoGrid.appendChild(videoContainer);
            this.joinRoom();
        } catch (error) {
            console.error('Error playing local video:', error);
            throw error;
        }
    }


    initializeSocketEvents() {
        this.socket.on('connect', () => {
            console.log('Socket connected');
            this.hideConnectionStatus();
        });

        // A dropped connection (wifi blip, laptop sleep, etc.) leaves stale
        // peer connections behind and the server forgets this socket's room
        // membership. On reconnect, tear down old peers and rejoin so both
        // sides re-negotiate fresh offers instead of the call staying dead.
        this.socket.on('reconnect', (attempt) => {
            console.log(`Socket reconnected after ${attempt} attempt(s)`);
            this.hideConnectionStatus();
            this.teardownPeers();
            if (this.localStream) {
                this.joinRoom();
            }
        });

        this.socket.on('disconnect', (reason) => {
            console.warn('Socket disconnected:', reason);
            this.showConnectionStatus('Connection lost. Reconnecting...');
        });

        this.socket.on('connect_error', (err) => {
            console.warn('Socket connect error:', err.message);
            this.showConnectionStatus('Connection problem. Retrying...');
        });

        this.socket.on('reconnect_failed', () => {
            this.showError('Unable to reconnect to the call. Please refresh the page.');
        });

        this.socket.on('sign_prediction', (data) => {
            if (data.username !== this.username) {
                this.addPredictionToUI(data);
            }
        });

        this.socket.on('room_participants', (data) => {
            if (Array.isArray(data.participants)) {
                this.participants = new Set(data.participants);
                this.renderParticipants();
            }
            if (typeof data.participant_count === 'number') {
                this.updateParticipantCount(data.participant_count);
            } else if (Array.isArray(data.participants)) {
                this.updateParticipantCount(data.participants.length);
            }
        });

        this.socket.on('user_joined', async (data) => {
            console.log('User joined:', data);
            this.participants.add(data.username);
            this.renderParticipants();
            if (typeof data.participant_count === 'number') {
                this.updateParticipantCount(data.participant_count);
            }
            if (data.username !== this.username) {
                await this.handleUserJoined(data);
            }
        });

        this.socket.on('chat_message', (data) => {
            if (data.username !== this.username) {
                this.addChatMessage(data, false);
            }
        });

        this.socket.on('offer', async (data) => {
            console.log('Received offer from:', data.username);
            await this.handleOffer(data);
        });

        this.socket.on('answer', async (data) => {
            console.log('Received answer from:', data.username);
            await this.handleAnswer(data);
        });

        this.socket.on('ice_candidate', async (data) => {
            await this.handleIceCandidate(data);
        });

        this.socket.on('user_left', (data) => {
            this.handleUserLeft(data);
        });

        this.socket.on('error', (data) => {
            console.error('Socket error:', data);
            this.showError(data.message);
        });
    }

    async createPeerConnection(targetUsername) {
        const pc = new RTCPeerConnection(peerConfiguration);

        // Add all local tracks
        this.localStream.getTracks().forEach(track => {
            pc.addTrack(track, this.localStream);
        });

        // Handle incoming streams
        pc.ontrack = (event) => {
            const videoContainer = document.getElementById(`video-${targetUsername}`);
            if (!videoContainer) {
                const container = this.createVideoContainer(targetUsername);
                const video = container.querySelector('video');
                video.srcObject = event.streams[0];
                document.getElementById('video-grid').appendChild(container);
            }
        };

        // Handle ICE candidates
        pc.onicecandidate = (event) => {
            if (event.candidate) {
                this.socket.emit('ice_candidate', {
                    room: this.roomId,
                    target: targetUsername,
                    username: this.username,
                    candidate: event.candidate
                });
            }
        };

        // Monitor connection state
        this.monitorPeerConnection(pc, targetUsername);

        return pc;
    }

    async handleUserJoined(data) {
        try {
            const pc = await this.createPeerConnection(data.username);
            this.peers[data.username] = pc;

            // Create and send offer
            const offer = await pc.createOffer({
                offerToReceiveAudio: true,
                offerToReceiveVideo: true
            });
            await pc.setLocalDescription(offer);

            this.socket.emit('offer', {
                room: this.roomId,
                target: data.username,
                username: this.username,
                sdp: offer
            });
        } catch (error) {
            console.error('Error handling user joined:', error);
            this.showError('Failed to establish connection with new participant');
        }
    }

    async handleOffer(data) {
        try {
            let pc = this.peers[data.username];
            if (!pc) {
                pc = await this.createPeerConnection(data.username);
                this.peers[data.username] = pc;
            }

            await pc.setRemoteDescription(new RTCSessionDescription(data.sdp));
            const answer = await pc.createAnswer();
            await pc.setLocalDescription(answer);

            this.socket.emit('answer', {
                room: this.roomId,
                target: data.username,
                username: this.username,
                sdp: answer
            });
        } catch (error) {
            console.error('Error handling offer:', error);
            this.showError('Failed to process connection offer');
        }
    }

    async handleAnswer(data) {
        try {
            const pc = this.peers[data.username];
            if (pc) {
                await pc.setRemoteDescription(new RTCSessionDescription(data.sdp));
            }
        } catch (error) {
            console.error('Error handling answer:', error);
        }
    }
    async handleIceCandidate(data) {
        try {
            const pc = this.peers[data.username];
            if (pc) {
                await pc.addIceCandidate(new RTCIceCandidate(data.candidate));
            }
        } catch (error) {
            console.error('Error handling ICE candidate:', error);
        }
    }

    handleUserLeft(data) {
        if (this.peers[data.username]) {
            this.peers[data.username].close();
            delete this.peers[data.username];
        }

        const videoElement = document.getElementById(`video-container-${data.username}`);
        if (videoElement) {
            videoElement.remove();
        }

        this.participants.delete(data.username);
        this.renderParticipants();
        this.updateParticipantCount(data.participant_count);
    }

    renderParticipants() {
        const list = document.getElementById('participantsList');
        if (!list) return;
        list.innerHTML = '';
        Array.from(this.participants).sort().forEach(name => {
            const item = document.createElement('div');
            item.className = 'participant-item';
            const label = escapeHtml(name) + (name === this.username ? ' (You)' : '');
            item.innerHTML = `<i class="fas fa-user"></i><span>${label}</span>`;
            list.appendChild(item);
        });
    }

    sendChatMessage(text) {
        const payload = {
            room: this.roomId,
            username: this.username,
            message: text,
            timestamp: new Date().toISOString()
        };
        this.socket.emit('chat_message', payload);
        this.addChatMessage(payload, true);
    }

    addChatMessage(data, isOwn) {
        const container = document.getElementById('chatMessages');
        if (!container) return;

        const el = document.createElement('div');
        el.className = 'chat-message' + (isOwn ? ' own' : '');
        const timestamp = data.timestamp ? new Date(data.timestamp).toLocaleTimeString() : new Date().toLocaleTimeString();

        el.innerHTML = `
            <div class="chat-meta">
                <span>${escapeHtml(data.username || '')}</span>
                <span>${timestamp}</span>
            </div>
            <div class="chat-text">${escapeHtml(data.message || '')}</div>
        `;

        container.appendChild(el);
        container.scrollTop = container.scrollHeight;
    }

    teardownPeers() {
        Object.values(this.peers).forEach(pc => pc.close());
        this.peers = {};
        document.querySelectorAll('.video-container').forEach(el => {
            if (el.id !== `video-container-${this.username}`) {
                el.remove();
            }
        });
    }

    monitorPeerConnection(pc, username) {
        pc.onconnectionstatechange = () => {
            console.log(`Connection state with ${username}:`, pc.connectionState);

            const container = document.getElementById(`video-container-${username}`);
            if (container) {
                const status = container.querySelector('.connection-status');
                if (status) {
                    status.textContent = pc.connectionState;
                    status.className = `connection-status ${pc.connectionState}`;
                }
            }

            if (pc.connectionState === 'failed') {
                this.handleConnectionFailure(username);
            }
        };

        pc.oniceconnectionstatechange = () => {
            console.log(`ICE connection state with ${username}:`, pc.iceConnectionState);
        };
    }

    async handleConnectionFailure(username) {
        try {
            if (this.peers[username]) {
                this.peers[username].close();
                delete this.peers[username];
            }

            const pc = await this.createPeerConnection(username);
            this.peers[username] = pc;

            const offer = await pc.createOffer();
            await pc.setLocalDescription(offer);

            this.socket.emit('offer', {
                room: this.roomId,
                target: username,
                username: this.username,
                sdp: offer
            });
        } catch (error) {
            console.error('Reconnection failed:', error);
            this.showError('Failed to re-establish connection');
        }
    }

    createVideoContainer(username, isLocal = false) {
        const container = document.createElement('div');
        container.className = 'video-container';
        container.id = `video-container-${username}`;

        const video = document.createElement('video');
        video.id = `video-${username}`;
        video.autoplay = true;
        video.playsInline = true;
        if (isLocal) {
            video.muted = true;
        }

        const overlay = document.createElement('div');
        overlay.className = 'video-overlay';
        overlay.innerHTML = `
            <div class="name-tag">${username}${isLocal ? ' (You)' : ''}</div>
            <div class="connection-status"></div>
        `;

        container.appendChild(video);
        container.appendChild(overlay);
        return container;
    }

    joinRoom() {
        console.log('Joining room:', this.roomId);
        this.socket.emit('join_room', {
            room: this.roomId,
            username: this.username
        });
    }

    toggleVideo() {
        if (this.localStream) {
            const videoTrack = this.localStream.getVideoTracks()[0];
            if (videoTrack) {
                videoTrack.enabled = !videoTrack.enabled;
                this.isVideoEnabled = videoTrack.enabled;
                return this.isVideoEnabled;
            }
        }
        return false;
    }

    toggleAudio() {
        if (this.localStream) {
            const audioTrack = this.localStream.getAudioTracks()[0];
            if (audioTrack) {
                audioTrack.enabled = !audioTrack.enabled;
                this.isAudioEnabled = audioTrack.enabled;
                return this.isAudioEnabled;
            }
        }
        return false;
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

    async initializeSettings() {
        try {
            const devices = await navigator.mediaDevices.enumerateDevices();
            const cameraSelect = document.getElementById('cameraSelect');
            const microphoneSelect = document.getElementById('microphoneSelect');

            const videoDevices = devices.filter(device => device.kind === 'videoinput');
            this.videoDevices = videoDevices;

            const switchCameraBtn = document.getElementById('switch-camera');
            if (switchCameraBtn) {
                switchCameraBtn.style.display = videoDevices.length > 1 ? '' : 'none';
            }

            if (cameraSelect) {
                videoDevices.forEach(device => {
                    const option = document.createElement('option');
                    option.value = device.deviceId;
                    option.text = device.label || `Camera ${cameraSelect.length + 1}`;
                    cameraSelect.appendChild(option);
                });

                cameraSelect.addEventListener('change', () => this.switchCamera(cameraSelect.value));
            }

            if (microphoneSelect) {
                const audioDevices = devices.filter(device => device.kind === 'audioinput');
                audioDevices.forEach(device => {
                    const option = document.createElement('option');
                    option.value = device.deviceId;
                    option.text = device.label || `Microphone ${microphoneSelect.length + 1}`;
                    microphoneSelect.appendChild(option);
                });

                microphoneSelect.addEventListener('change', () => this.switchMicrophone(microphoneSelect.value));
            }
        } catch (error) {
            console.error('Error initializing settings:', error);
        }
    }

    async switchCamera(deviceId) {
        try {
            const newStream = await navigator.mediaDevices.getUserMedia({
                video: {
                    deviceId: deviceId ? { exact: deviceId } : undefined,
                    width: { ideal: 1280 },
                    height: { ideal: 720 },
                    frameRate: { ideal: 30 }
                },
                audio: false
            });

            // Update local video track
            const oldTrack = this.localStream.getVideoTracks()[0];
            const newTrack = newStream.getVideoTracks()[0];
            this.localStream.removeTrack(oldTrack);
            this.localStream.addTrack(newTrack);
            oldTrack.stop();

            // Update local video element
            const localVideo = document.getElementById('localVideo');
            if (localVideo) {
                localVideo.srcObject = this.localStream;
            }

            // Update track for all peer connections
            Object.values(this.peers).forEach(pc => {
                const sender = pc.getSenders().find(s => s.track && s.track.kind === 'video');
                if (sender) {
                    sender.replaceTrack(newTrack);
                }
            });

            this.isVideoEnabled = true;
            const videoButton = document.getElementById('toggle-video');
            if (videoButton) {
                videoButton.innerHTML = '<i class="fas fa-video"></i>';
                videoButton.classList.add('active');
            }
        } catch (error) {
            console.error('Error switching camera:', error);
            this.showError('Failed to switch camera');
        }
    }

    async switchToNextCamera() {
        if (!this.videoDevices || this.videoDevices.length < 2) return;
        this.currentCameraIndex = (this.currentCameraIndex + 1) % this.videoDevices.length;
        await this.switchCamera(this.videoDevices[this.currentCameraIndex].deviceId);
    }

    async setVideoQuality(quality) {
        const presets = {
            low: { width: 640, height: 360 },
            medium: { width: 1280, height: 720 },
            high: { width: 1920, height: 1080 }
        };
        const dims = presets[quality] || presets.medium;

        if (!this.localStream) return;

        try {
            const currentTrack = this.localStream.getVideoTracks()[0];
            const currentDeviceId = currentTrack ? currentTrack.getSettings().deviceId : undefined;

            const newStream = await navigator.mediaDevices.getUserMedia({
                video: {
                    deviceId: currentDeviceId ? { exact: currentDeviceId } : undefined,
                    width: { ideal: dims.width },
                    height: { ideal: dims.height },
                    frameRate: { ideal: 30 }
                },
                audio: false
            });

            const newTrack = newStream.getVideoTracks()[0];
            if (currentTrack) {
                this.localStream.removeTrack(currentTrack);
                currentTrack.stop();
            }
            this.localStream.addTrack(newTrack);

            const localVideo = document.getElementById('localVideo');
            if (localVideo) {
                localVideo.srcObject = this.localStream;
            }

            Object.values(this.peers).forEach(pc => {
                const sender = pc.getSenders().find(s => s.track && s.track.kind === 'video');
                if (sender) {
                    sender.replaceTrack(newTrack);
                }
            });
        } catch (error) {
            console.error('Error changing video quality:', error);
            this.showError('Failed to change video quality');
        }
    }

    async switchMicrophone(deviceId) {
        try {
            const newStream = await navigator.mediaDevices.getUserMedia({
                video: false,
                audio: {
                    deviceId: deviceId ? { exact: deviceId } : undefined,
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                }
            });

            // Update local audio track
            const oldTrack = this.localStream.getAudioTracks()[0];
            const newTrack = newStream.getAudioTracks()[0];
            this.localStream.removeTrack(oldTrack);
            this.localStream.addTrack(newTrack);
            oldTrack.stop();

            // Update track for all peer connections
            Object.values(this.peers).forEach(pc => {
                const sender = pc.getSenders().find(s => s.track && s.track.kind === 'audio');
                if (sender) {
                    sender.replaceTrack(newTrack);
                }
            });

            this.isAudioEnabled = true;
            const audioButton = document.getElementById('toggle-audio');
            if (audioButton) {
                audioButton.innerHTML = '<i class="fas fa-microphone"></i>';
                audioButton.classList.add('active');
            }
        } catch (error) {
            console.error('Error switching microphone:', error);
            this.showError('Failed to switch microphone');
        }
    }

    startPredictionInterval() {
        if (this.predictionInterval) {
            clearInterval(this.predictionInterval);
        }

        this.predictionInterval = setInterval(() => {
            this.captureAndPredict();
        }, 2000); // Predict every 2 seconds
    }

    async captureAndPredict() {
        if (!this.isPredictionEnabled || !this.localStream) return;

        try {
            const video = document.getElementById('localVideo');
            if (!video) return;

            const canvas = document.createElement('canvas');
            canvas.width = 224;
            canvas.height = 224;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

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
            if (data.error) throw new Error(data.error);

            if (data.prediction) {
                // Add prediction to UI
                this.addPredictionToUI(data);
                // Broadcast prediction to room
                this.socket.emit('sign_prediction', {
                    room: this.roomId,
                    username: this.username,
                    prediction: data.prediction,
                    confidence: data.confidence,
                    timestamp: data.timestamp
                });
            }
        } catch (error) {
            console.error('Prediction error:', error);
        }
    }

    addPredictionToUI(data) {
        const container = document.getElementById('predictions-container');
        if (!container) return;

        const predictionElement = document.createElement('div');
        predictionElement.className = 'prediction-item';
        const timestamp = data.timestamp ? new Date(data.timestamp).toLocaleTimeString() : new Date().toLocaleTimeString();
        const confidence = typeof data.confidence === 'number' ? Math.round(data.confidence) : null;

        predictionElement.innerHTML = `
            <div class="prediction-content">
                <div class="prediction-header">
                    <span class="prediction-user">${escapeHtml(data.username || this.username)}</span>
                    <span class="prediction-time">${timestamp}</span>
                </div>
                <div class="prediction-text">
                    <strong>${escapeHtml(data.prediction)}</strong>
                    ${confidence !== null ? `<span class="prediction-confidence">${confidence}%</span>` : ''}
                </div>
            </div>
        `;

        container.insertBefore(predictionElement, container.firstChild);

        // Keep only last 10 predictions
        while (container.children.length > 10) {
            container.removeChild(container.lastChild);
        }
    }

    updateParticipantCount(count) {
        const countElement = document.getElementById('participantCount');
        if (countElement) {
            countElement.textContent = count;
        }
        const videoGrid = document.getElementById('video-grid');
        if (videoGrid) {
            videoGrid.setAttribute('data-count', count);
        }
    }

    showConnectionStatus(message) {
        const status = document.getElementById('connectionStatus');
        if (status) {
            status.textContent = message;
            status.style.display = '';
        }
    }

    hideConnectionStatus() {
        const status = document.getElementById('connectionStatus');
        if (status) {
            status.style.display = 'none';
        }
    }

    showError(message) {
        const errorModal = new bootstrap.Modal(document.getElementById('errorModal'));
        document.getElementById('errorMessage').textContent = message;
        errorModal.show();
    }

    disconnect() {
        // Stop all media tracks
        if (this.localStream) {
            this.localStream.getTracks().forEach(track => track.stop());
        }

        // Close all peer connections
        this.teardownPeers();

        // Clear prediction interval
        if (this.predictionInterval) {
            clearInterval(this.predictionInterval);
        }

        // Disconnect socket
        this.socket.emit('leave_room', {
            room: this.roomId,
            username: this.username
        });
        this.socket.disconnect();
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    if (!ROOM_ID || !USERNAME) {
        console.error('Room ID or Username not defined');
        return;
    }

    // Create video call instance
    window.videoCall = new VideoCall(ROOM_ID, USERNAME);

    // Setup control buttons
    document.getElementById('toggle-video')?.addEventListener('click', function() {
        const isEnabled = window.videoCall.toggleVideo();
        this.innerHTML = isEnabled ?
            '<i class="fas fa-video"></i>' :
            '<i class="fas fa-video-slash"></i>';
        this.classList.toggle('active', isEnabled);
    });

    document.getElementById('toggle-audio')?.addEventListener('click', function() {
        const isEnabled = window.videoCall.toggleAudio();
        this.innerHTML = isEnabled ?
            '<i class="fas fa-microphone"></i>' :
            '<i class="fas fa-microphone-slash"></i>';
        this.classList.toggle('active', isEnabled);
    });

    document.getElementById('toggle-prediction')?.addEventListener('click', function() {
        const isEnabled = window.videoCall.togglePrediction();
        this.classList.toggle('active', isEnabled);
        const checkbox = document.getElementById('predictionEnabled');
        if (checkbox) checkbox.checked = isEnabled;
    });

    document.getElementById('leave-room')?.addEventListener('click', () => {
        window.videoCall.disconnect();
        window.location.href = '/dashboard';
    });

    // Handle page unload
    window.addEventListener('beforeunload', () => {
        if (window.videoCall) {
            window.videoCall.disconnect();
        }
    });
});
