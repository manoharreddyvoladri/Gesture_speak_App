class VideoCall {
    constructor(roomId, username) {
        this.roomId = roomId;
        this.username = username;
        this.peers = {};
        this.localStream = null;
        this.socket = io({
            transports: ['websocket'],
            upgrade: false
        });

        // State
        this.isVideoEnabled = true;
        this.isAudioEnabled = true;
        this.isPredictionEnabled = false;
        this.isInitialized = false;

        // Debug mode
        this.debug = true;
        this.log('Initializing VideoCall');

        // Bind socket events
        this.socket.on('connect', () => {
            this.log('Socket connected');
            this.initializeMedia()
                .then(() => this.joinRoom())
                .catch(err => this.handleError('Failed to initialize media', err));
        });

        this.socket.on('connect_error', (error) => {
            this.handleError('Socket connection error', error);
        });

        this.socket.on('user_joined', (data) => {
            this.log('User joined:', data);
            this.updateParticipantCount(data.participant_count);
            if (data.username !== this.username) {
                this.handleUserJoined(data);
            }
        });

        this.socket.on('user_left', (data) => {
            this.log('User left:', data);
            this.handleUserLeft(data);
            this.updateParticipantCount(data.participant_count);
        });
    }

    log(...args) {
        if (this.debug) {
            console.log('[VideoCall]', ...args);
        }
    }

    handleError(message, error = null) {
        console.error('[VideoCall Error]', message, error);
        const errorDiv = document.createElement('div');
        errorDiv.className = 'alert alert-danger';
        errorDiv.textContent = `Error: ${message}. ${error?.message || ''}`;
        document.body.insertBefore(errorDiv, document.body.firstChild);
    }

    async checkMediaPermissions() {
        try {
            this.log('Checking media permissions...');
            const result = await navigator.permissions.query({ name: 'camera' });
            if (result.state === 'denied') {
                throw new Error('Camera permission denied');
            }
            return true;
        } catch (err) {
            this.handleError('Media permission check failed', err);
            return false;
        }
    }

    async initializeMedia() {
        try {
            this.log('Initializing media devices...');
            
            // Check permissions first
            await this.checkMediaPermissions();

            // Get media stream with specific constraints
            const constraints = {
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true
                },
                video: {
                    width: { ideal: 1280 },
                    height: { ideal: 720 },
                    facingMode: 'user',
                    frameRate: { ideal: 30 }
                }
            };

            this.log('Requesting media with constraints:', constraints);
            this.localStream = await navigator.mediaDevices.getUserMedia(constraints);
            this.log('Media stream obtained');

            // Add local video to grid
            await this.displayLocalVideo();
            this.isInitialized = true;
            this.log('Media initialization complete');

            return true;
        } catch (err) {
            this.handleError('Failed to initialize media devices', err);
            throw err;
        }
    }

    async displayLocalVideo() {
        try {
            this.log('Displaying local video...');
            const videoGrid = document.getElementById('video-grid');
            if (!videoGrid) {
                throw new Error('Video grid element not found');
            }

            // Create video container
            const videoContainer = document.createElement('div');
            videoContainer.className = 'video-container';
            videoContainer.id = `video-container-${this.username}`;

            // Create video element
            const videoElement = document.createElement('video');
            videoElement.id = `video-${this.username}`;
            videoElement.autoplay = true;
            videoElement.playsInline = true;
            videoElement.muted = true; // Mute local video to prevent feedback

            // Create name tag overlay
            const overlay = document.createElement('div');
            overlay.className = 'video-overlay';
            const nameTag = document.createElement('div');
            nameTag.className = 'name-tag';
            nameTag.textContent = `${this.username} (You)`;
            overlay.appendChild(nameTag);

            // Add video stats display
            const statsDisplay = document.createElement('div');
            statsDisplay.className = 'video-stats';
            overlay.appendChild(statsDisplay);

            // Assemble and add to grid
            videoContainer.appendChild(videoElement);
            videoContainer.appendChild(overlay);
            videoGrid.appendChild(videoContainer);

            // Set stream
            videoElement.srcObject = this.localStream;
            await videoElement.play().catch(err => {
                this.log('Autoplay failed, trying with user interaction', err);
                videoElement.controls = true;
            });

            this.log('Local video displayed successfully');
            
            // Monitor video stream status
            this.monitorVideoStream(videoElement);
            
            return true;
        } catch (err) {
            this.handleError('Failed to display local video', err);
            return false;
        }
    }

    monitorVideoStream(videoElement) {
        // Monitor video element events
        videoElement.addEventListener('loadedmetadata', () => {
            this.log('Video metadata loaded:', {
                width: videoElement.videoWidth,
                height: videoElement.videoHeight
            });
        });

        videoElement.addEventListener('playing', () => {
            this.log('Video started playing');
        });

        videoElement.addEventListener('pause', () => {
            this.log('Video paused');
        });

        videoElement.addEventListener('error', (err) => {
            this.handleError('Video element error', err);
        });

        // Monitor stream status
        this.localStream.getTracks().forEach(track => {
            track.addEventListener('ended', () => {
                this.handleError('Media track ended', { trackKind: track.kind });
            });
        });
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

    async joinRoom() {
        if (!this.isInitialized) {
            this.handleError('Cannot join room: Media not initialized');
            return;
        }

        this.log('Joining room:', this.roomId);
        this.socket.emit('join_room', {
            room: this.roomId,
            username: this.username
        });
    }

    toggleVideo() {
        if (!this.localStream) return false;
        const videoTrack = this.localStream.getVideoTracks()[0];
        if (videoTrack) {
            this.isVideoEnabled = !videoTrack.enabled;
            videoTrack.enabled = this.isVideoEnabled;
            this.log('Video toggled:', this.isVideoEnabled);
            return this.isVideoEnabled;
        }
        return false;
    }

    toggleAudio() {
        if (!this.localStream) return false;
        const audioTrack = this.localStream.getAudioTracks()[0];
        if (audioTrack) {
            this.isAudioEnabled = !audioTrack.enabled;
            audioTrack.enabled = this.isAudioEnabled;
            this.log('Audio toggled:', this.isAudioEnabled);
            return this.isAudioEnabled;
        }
        return false;
    }

    async switchCamera() {
        try {
            const devices = await navigator.mediaDevices.enumerateDevices();
            const videoDevices = devices.filter(device => device.kind === 'videoinput');
            
            if (videoDevices.length < 2) {
                this.log('No alternative camera found');
                return;
            }

            // Get current video track
            const currentTrack = this.localStream.getVideoTracks()[0];
            const currentDeviceId = currentTrack.getSettings().deviceId;

            // Find next device
            const currentIndex = videoDevices.findIndex(device => device.deviceId === currentDeviceId);
            const nextDevice = videoDevices[(currentIndex + 1) % videoDevices.length];

            // Get new stream
            const newStream = await navigator.mediaDevices.getUserMedia({
                video: { deviceId: { exact: nextDevice.deviceId } },
                audio: false
            });

            // Replace track
            const newTrack = newStream.getVideoTracks()[0];
            const sender = this.peers[Object.keys(this.peers)[0]]
                ?.getSenders()
                .find(sender => sender.track?.kind === 'video');

            if (sender) {
                await sender.replaceTrack(newTrack);
            }

            // Update local stream
            currentTrack.stop();
            this.localStream.removeTrack(currentTrack);
            this.localStream.addTrack(newTrack);

            // Update local video
            const videoElement = document.getElementById(`video-${this.username}`);
            if (videoElement) {
                videoElement.srcObject = this.localStream;
            }

            this.log('Camera switched successfully');
        } catch (err) {
            this.handleError('Failed to switch camera', err);
        }
    }

    leaveRoom() {
        this.log('Leaving room');
        if (this.localStream) {
            this.localStream.getTracks().forEach(track => track.stop());
        }
        Object.values(this.peers).forEach(peer => peer.close());
        this.socket.disconnect();
        window.location.href = '/dashboard';
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    const videoCall = new VideoCall(ROOM_ID, USERNAME);
    window.videoCall = videoCall; // Make it globally accessible

    // Set up control buttons
    const controls = {
        video: document.getElementById('toggle-video'),
        audio: document.getElementById('toggle-audio'),
        leave: document.getElementById('leave-room')
    };

    if (controls.video) {
        controls.video.addEventListener('click', function() {
            const isEnabled = videoCall.toggleVideo();
            this.innerHTML = isEnabled ? 
                '<i class="fas fa-video"></i>' : 
                '<i class="fas fa-video-slash"></i>';
            this.classList.toggle('active', isEnabled);
        });
    }

    if (controls.audio) {
        controls.audio.addEventListener('click', function() {
            const isEnabled = videoCall.toggleAudio();
            this.innerHTML = isEnabled ? 
                '<i class="fas fa-microphone"></i>' : 
                '<i class="fas fa-microphone-slash"></i>';
            this.classList.toggle('active', isEnabled);
        });
    }

    if (controls.leave) {
        controls.leave.addEventListener('click', () => videoCall.leaveRoom());
    }
});