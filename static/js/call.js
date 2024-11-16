// class VideoCall {
//     constructor(roomId, username) {
//         this.roomId = roomId;
//         this.username = username;
//         this.peers = {};
//         this.localStream = null;
        
//     // Updated socket connection options
//     this.socket = io({
//         transports: ['websocket', 'polling'],
//         upgrade: true,
//         reconnection: true,
//         reconnectionAttempts: 5,
//         reconnectionDelay: 1000,
//         timeout: 20000
//     });
//         // State
//         this.isVideoEnabled = true;
//         this.isAudioEnabled = true;
//         this.isPredictionEnabled = false;
//         this.predictionInterval = null;
//         this.predictionDelay = 1000;
//         this.lastPredictionTime = 0;
//         this.predictionConfidenceThreshold = 0.6;

//         // Debug mode
//         this.debug = true;
//         this.log('Initializing VideoCall');

//         // Initialize UI elements
//         this.initializeUI();
//         this.initializeSocketEvents();
//     }

//     log(...args) {
//         if (this.debug) {
//             console.log('[VideoCall]', ...args);
//         }
//     }

//     initializeUI() {
//         this.predictionContainer = document.getElementById('predictions-container');
//         this.predictionStatus = document.getElementById('predictionStatus');
        
//         // Initialize prediction toggle
//         const predictionToggle = document.getElementById('toggle-prediction');
//         if (predictionToggle) {
//             predictionToggle.addEventListener('click', () => this.togglePrediction());
//         }
//     }

//     initializeSocketEvents() {
//         this.socket.on('connect', () => {
//             this.log('Socket connected');
//             this.initializeMedia()
//                 .then(() => this.joinRoom())
//                 .catch(err => this.showError('Failed to initialize media', err));
//         });

//         this.socket.on('sign_prediction', (data) => {
//             if (data.username !== this.username) {
//                 this.addPredictionToUI(data);
//             }
//         });

//         this.socket.on('user_joined', (data) => {
//             this.log('User joined:', data);
//             this.updateParticipantCount(data.participant_count);
//             if (data.username !== this.username) {
//                 this.handleUserJoined(data);
//             }
//         });

//         this.socket.on('user_left', (data) => {
//             this.log('User left:', data);
//             this.handleUserLeft(data);
//             this.updateParticipantCount(data.participant_count);
//         });
//     }

//     async initializeMedia() {
//         try {
//             const constraints = {
//                 audio: {
//                     echoCancellation: true,
//                     noiseSuppression: true,
//                     autoGainControl: true
//                 },
//                 video: {
//                     width: { ideal: 1280 },
//                     height: { ideal: 720 },
//                     facingMode: 'user',
//                     frameRate: { ideal: 30 }
//                 }
//             };

//             this.localStream = await navigator.mediaDevices.getUserMedia(constraints);
//             await this.displayLocalVideo();
//             return true;
//         } catch (err) {
//             this.showError('Failed to access camera/microphone', err);
//             throw err;
//         }
//     }

//     async displayLocalVideo() {
//         const videoGrid = document.getElementById('video-grid');
//         if (!videoGrid) return;

//         const videoContainer = document.createElement('div');
//         videoContainer.className = 'video-container';
//         videoContainer.id = `video-container-${this.username}`;

//         const video = document.createElement('video');
//         video.id = `video-${this.username}`;
//         video.autoplay = true;
//         video.playsInline = true;
//         video.muted = true;

//         const overlay = document.createElement('div');
//         overlay.className = 'video-overlay';
//         overlay.innerHTML = `
//             <div class="name-tag">${this.username} (You)</div>
//             <div class="sign-indicator"></div>
//         `;

//         videoContainer.appendChild(video);
//         videoContainer.appendChild(overlay);
//         videoGrid.appendChild(videoContainer);

//         video.srcObject = this.localStream;
//         await video.play();
//     }

//     togglePrediction() {
//         this.isPredictionEnabled = !this.isPredictionEnabled;
//         const toggleButton = document.getElementById('toggle-prediction');
        
//         if (this.isPredictionEnabled) {
//             toggleButton?.setAttribute('data-active', 'true');
//             this.startPredictions();
//             this.showStatus('Sign detection enabled');
//         } else {
//             toggleButton?.setAttribute('data-active', 'false');
//             this.stopPredictions();
//             this.showStatus('Sign detection disabled');
//         }
//     }

//     startPredictions() {
//         if (this.predictionInterval) {
//             clearInterval(this.predictionInterval);
//         }

//         this.predictionInterval = setInterval(() => {
//             this.captureAndPredict();
//         }, this.predictionDelay);
//     }

//     stopPredictions() {
//         if (this.predictionInterval) {
//             clearInterval(this.predictionInterval);
//             this.predictionInterval = null;
//         }
//     }

//     async captureAndPredict() {
//         if (!this.isPredictionEnabled || !this.localStream) return;

//         const now = Date.now();
//         if (now - this.lastPredictionTime < this.predictionDelay) return;
//         this.lastPredictionTime = now;

//         try {
//             const video = document.getElementById(`video-${this.username}`);
//             if (!video) return;

//             const canvas = document.createElement('canvas');
//             canvas.width = 224;
//             canvas.height = 224;
//             const ctx = canvas.getContext('2d');
//             ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

//             const imageData = canvas.toDataURL('image/jpeg', 0.8);

//             const response = await fetch('/predict', {
//                 method: 'POST',
//                 headers: {
//                     'Content-Type': 'application/json',
//                 },
//                 body: JSON.stringify({ image: imageData })
//             });

//             if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

//             const data = await response.json();
//             if (data.error) throw new Error(data.error);

//             if (data.confidence >= this.predictionConfidenceThreshold * 100) {
//                 this.handlePrediction(data);
//             }

//         } catch (error) {
//             this.log('Prediction error:', error);
//             this.showStatus('Sign detection error: ' + error.message);
//         }
//     }

//     handlePrediction(predictionData) {
//         this.addPredictionToUI(predictionData);
//         this.updateSignIndicator(predictionData.prediction);

//         this.socket.emit('sign_prediction', {
//             room: this.roomId,
//             username: this.username,
//             ...predictionData
//         });
//     }

//     addPredictionToUI(predictionData) {
//         if (!this.predictionContainer) return;

//         const predictionElement = document.createElement('div');
//         predictionElement.className = 'prediction-item';
        
//         const timestamp = new Date(predictionData.timestamp).toLocaleTimeString();
//         const confidence = Math.round(predictionData.confidence);

//         predictionElement.innerHTML = `
//             <div class="prediction-avatar">
//                 ${predictionData.username?.[0]?.toUpperCase() || 'U'}
//             </div>
//             <div class="prediction-content">
//                 <div class="prediction-letter">${predictionData.prediction}</div>
//                 <div class="prediction-word">${this.getWordForLetter(predictionData.prediction)}</div>
//                 <div class="prediction-meta">
//                     <span class="prediction-user">${predictionData.username}</span>
//                     <span class="prediction-confidence">${confidence}%</span>
//                     <span class="prediction-time">${timestamp}</span>
//                 </div>
//             </div>
//             </div>
//         `;

//         this.predictionContainer.insertBefore(predictionElement, this.predictionContainer.firstChild);

//         // Keep only last 20 predictions
//         while (this.predictionContainer.children.length > 20) {
//             this.predictionContainer.removeChild(this.predictionContainer.lastChild);
//         }
//     }

//     updateSignIndicator(prediction) {
//         const container = document.querySelector(`#video-container-${this.username} .sign-indicator`);
//         if (!container) return;

//         container.textContent = `Sign: ${prediction}`;
//         container.classList.add('visible');

//         setTimeout(() => {
//             container.classList.remove('visible');
//         }, 2000);
//     }

//     getWordForLetter(letter) {
//         const words = {
//             'A': 'APPLE', 'B': 'BOOK', 'C': 'CAT', 'D': 'DOG',
//             'E': 'ELEPHANT', 'F': 'FRIEND', 'G': 'GOOD', 'H': 'HELLO',
//             'I': 'ICE CREAM', 'J': 'JUMP', 'K': 'KING', 'L': 'LOVE',
//             'M': 'MOTHER', 'N': 'NICE', 'O': 'ORANGE', 'P': 'PLEASE',
//             'Q': 'QUEEN', 'R': 'RAINBOW', 'S': 'SUN', 'T': 'THANK YOU',
//             'U': 'UMBRELLA', 'V': 'VICTORY', 'W': 'WATER', 'X': 'X-RAY',
//             'Y': 'YELLOW', 'Z': 'ZEBRA'
//         };
//         return words[letter] || letter;
//     }

//     showStatus(message, type = 'info') {
//         if (!this.predictionStatus) return;

//         this.predictionStatus.textContent = message;
//         this.predictionStatus.className = `prediction-status ${type} visible`;

//         setTimeout(() => {
//             this.predictionStatus.classList.remove('visible');
//         }, 3000);
//     }

//     async joinRoom() {
//         this.log('Joining room:', this.roomId);
//         this.socket.emit('join_room', {
//             room: this.roomId,
//             username: this.username
//         });
//     }

//     async handleUserJoined(data) {
//         this.log('Creating peer connection for:', data.username);
//         const pc = new RTCPeerConnection(peerConfiguration);
//         this.peers[data.username] = pc;

//         // Add local tracks
//         this.localStream.getTracks().forEach(track => {
//             pc.addTrack(track, this.localStream);
//         });

//         // Handle ICE candidates
//         pc.onicecandidate = (event) => {
//             if (event.candidate) {
//                 this.socket.emit('ice_candidate', {
//                     room: this.roomId,
//                     target: data.username,
//                     username: this.username,
//                     candidate: event.candidate
//                 });
//             }
//         };

//         // Handle incoming tracks
//         pc.ontrack = (event) => {
//             const remoteVideo = this.createVideoElement(data.username);
//             remoteVideo.srcObject = event.streams[0];
//             document.getElementById('video-grid').appendChild(remoteVideo);
//         };

//         // Create and send offer
//         try {
//             const offer = await pc.createOffer();
//             await pc.setLocalDescription(offer);
//             this.socket.emit('offer', {
//                 room: this.roomId,
//                 target: data.username,
//                 username: this.username,
//                 sdp: offer
//             });
//         } catch (err) {
//             console.error('Error creating offer:', err);
//         }
//     }

//     handleUserLeft(data) {
//         const pc = this.peers[data.username];
//         if (pc) {
//             pc.close();
//             delete this.peers[data.username];
//         }
        
//         const videoElement = document.getElementById(`video-container-${data.username}`);
//         if (videoElement) {
//             videoElement.remove();
//         }
//     }

//     updateParticipantCount(count) {
//         const countElement = document.getElementById('participantCount');
//         if (countElement) {
//             countElement.textContent = count;
//         }
//         const videoGrid = document.getElementById('video-grid');
//         if (videoGrid) {
//             videoGrid.setAttribute('data-count', count);
//         }
//     }

//     toggleVideo() {
//         if (!this.localStream) return false;
//         const videoTrack = this.localStream.getVideoTracks()[0];
//         if (videoTrack) {
//             this.isVideoEnabled = !videoTrack.enabled;
//             videoTrack.enabled = this.isVideoEnabled;
//             if (!videoTrack.enabled && this.isPredictionEnabled) {
//                 this.togglePrediction();
//             }
//             return this.isVideoEnabled;
//         }
//         return false;
//     }

//     toggleAudio() {
//         if (!this.localStream) return false;
//         const audioTrack = this.localStream.getAudioTracks()[0];
//         if (audioTrack) {
//             this.isAudioEnabled = !audioTrack.enabled;
//             audioTrack.enabled = this.isAudioEnabled;
//             return this.isAudioEnabled;
//         }
//         return false;
//     }

//     cleanup() {
//         this.stopPredictions();
//         if (this.localStream) {
//             this.localStream.getTracks().forEach(track => track.stop());
//         }
//         Object.values(this.peers).forEach(peer => peer.close());
//         this.socket.disconnect();
//     }
// }

// // WebRTC Configuration
// const peerConfiguration = {
//     iceServers: [
//         {
//             urls: [
//                 'stun:stun.l.google.com:19302',
//                 'stun:stun1.l.google.com:19302',
//                 'stun:stun2.l.google.com:19302',
//                 'stun:stun3.l.google.com:19302',
//                 'stun:stun4.l.google.com:19302'
//             ]
//         },
//         {
//             urls: 'turn:numb.viagenie.ca',
//             username: 'webrtc@live.com',
//             credential: 'muazkh'
//         },
//         {
//             urls: 'turn:turn.anyfirewall.com:443?transport=tcp',
//             username: 'webrtc',
//             credential: 'webrtc'
//         }
//     ],
//     iceCandidatePoolSize: 10,
//     bundlePolicy: 'max-bundle',
//     rtcpMuxPolicy: 'require',
//     iceTransportPolicy: 'all'
// };

// // Initialize on page load
// document.addEventListener('DOMContentLoaded', () => {
//     const videoCall = new VideoCall(ROOM_ID, USERNAME);
//     window.videoCall = videoCall;

//     // Handle page unload
//     window.addEventListener('beforeunload', () => {
//         videoCall.cleanup();
//     });

//     // Initialize control buttons
//     const controls = {
//         video: document.getElementById('toggle-video'),
//         audio: document.getElementById('toggle-audio'),
//         prediction: document.getElementById('toggle-prediction'),
//         leave: document.getElementById('leave-room')
//     };

//     if (controls.video) {
//         controls.video.addEventListener('click', function() {
//             const isEnabled = videoCall.toggleVideo();
//             this.innerHTML = isEnabled ? 
//                 '<i class="fas fa-video"></i>' : 
//                 '<i class="fas fa-video-slash"></i>';
//             this.classList.toggle('active', isEnabled);
//         });
//     }

//     if (controls.audio) {
//         controls.audio.addEventListener('click', function() {
//             const isEnabled = videoCall.toggleAudio();
//             this.innerHTML = isEnabled ? 
//                 '<i class="fas fa-microphone"></i>' : 
//                 '<i class="fas fa-microphone-slash"></i>';
//             this.classList.toggle('active', isEnabled);
//         });
//     }

//     if (controls.leave) {
//         controls.leave.addEventListener('click', () => {
//             videoCall.cleanup();
//             window.location.href = '/dashboard';
//         });
//     }
// });






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
            reconnectionAttempts: 5,
            reconnectionDelay: 1000,
            timeout: 20000
        });

        this.isVideoEnabled = true;
        this.isAudioEnabled = true;
        this.isPredictionEnabled = false;
        this.predictionInterval = null;
        this.debug = true;

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

        this.socket.on('sign_prediction', (data) => {
            if (data.username !== this.username) {
                this.addPredictionToUI(data);
            }
        });

        this.socket.on('user_joined', async (data) => {
            console.log('User joined:', data);
            if (data.username !== this.username) {
                await this.handleUserJoined(data);
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

        this.updateParticipantCount(data.participant_count);
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
// Add after your existing methods in VideoCall class

async initializeSettings() {
    try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const cameraSelect = document.getElementById('cameraSelect');
        const microphoneSelect = document.getElementById('microphoneSelect');

        if (cameraSelect) {
            const videoDevices = devices.filter(device => device.kind === 'videoinput');
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


    // Add these methods to your VideoCall class right after togglePrediction():



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

        if (data.prediction) {
            // Add prediction to UI
            this.addPredictionToUI(data);
            // Broadcast prediction to room
            this.socket.emit('sign_prediction', {
                room: this.roomId,
                username: this.username,
                prediction: data.prediction,
                confidence: data.confidence
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
    const timestamp = new Date().toLocaleTimeString();

    predictionElement.innerHTML = `
        <div class="prediction-content">
            <div class="prediction-header">
                <span class="prediction-user">${data.username || this.username}</span>
                <span class="prediction-time">${timestamp}</span>
            </div>
            <div class="prediction-text">
                <strong>${data.prediction}</strong>
                <span class="prediction-confidence">${Math.round(data.confidence)}%</span>
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
        Object.values(this.peers).forEach(pc => pc.close());
        this.peers = {};

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