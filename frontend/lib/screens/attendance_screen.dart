// frontend/lib/screens/attendance_screen.dart

import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:ai_face_attendance_frontend/utils/image_converter.dart';

enum AttendancePhase {
  preparation, // Phase 0
  faceRecognition, // Phase 1
  livenessTransition, // Phase 2
  livenessDetection, // Phase 3
  finalResult // Phase 5
}

class AttendanceScreen extends StatefulWidget {
  final List<CameraDescription> cameras;

  const AttendanceScreen({super.key, required this.cameras});

  @override
  State<AttendanceScreen> createState() => _AttendanceScreenState();
}

class _AttendanceScreenState extends State<AttendanceScreen> {
  late CameraController _controller;
  late Future<void> _initializeControllerFuture;
  WebSocketChannel? _channel;
  String _statusMessage = "Place your face inside the frame";
  Timer? _streamTimer;
  AttendancePhase _currentPhase = AttendancePhase.preparation;

  // Phase 1 state
  bool _isFaceRecognized = false;
  bool _isFaceDetected = false;
  String? _recognizedUserName;
  bool _isConnected = false;

  /// WS endpoint from your FastAPI backend
  /// IMPORTANT: Use 'localhost:8000' if using 'adb reverse tcp:8000 tcp:8000'
  static const String _wsUrl = 'ws://localhost:8000/api/v1/ws/attendance';

  @override
  void initState() {
    super.initState();
    _startPreparationPhase();
  }

  // -----------------------
  // PHASE 0: PREPARATION
  // -----------------------
  void _startPreparationPhase() {
    Timer(const Duration(seconds: 2), () {
      if (mounted) {
        setState(() {
          _currentPhase = AttendancePhase.faceRecognition;
        });
        _initializeCamera();
        _connectWebSocket();
      }
    });
  }

  // -----------------------
  // CAMERA INITIALIZATION
  // -----------------------
  void _initializeCamera() {
    if (widget.cameras.isEmpty) {
      setState(() => _statusMessage = "No cameras available");
      return;
    }

    _controller = CameraController(
      widget.cameras.firstWhere(
        (camera) => camera.lensDirection == CameraLensDirection.front,
        orElse: () => widget.cameras.first,
      ),
      ResolutionPreset.medium,
      enableAudio: false,
    );

    _initializeControllerFuture = _controller.initialize().then((_) {
      if (!mounted) return;
      _startFrameStream();
    }).catchError((e) {
      setState(() => _statusMessage = "Camera initialization failed: $e");
    });
  }

  // -----------------------
  // WEBSOCKET CONNECTION
  // -----------------------
  void _connectWebSocket() {
    try {
      _channel = WebSocketChannel.connect(Uri.parse(_wsUrl));
      setState(() => _isConnected = true);

      _channel!.stream.listen(
        (data) {
          if (_currentPhase != AttendancePhase.faceRecognition ||
              _isFaceRecognized) return;

          final response = jsonDecode(data);
          final status = response['status'];

          if (mounted) {
            setState(() {
              _statusMessage = response['message'] ?? "Processing...";
              _isFaceDetected = response['face_detected'] ?? false;

              if (status == 'success') {
                _isFaceRecognized = true;
                _recognizedUserName = response['user'];
                _handleFaceRecognized();
              }
            });
          }
        },
        onDone: () {
          if (mounted) setState(() => _isConnected = false);
        },
        onError: (error) {
          if (mounted) setState(() => _isConnected = false);
        },
      );
    } catch (e) {
      if (mounted) setState(() => _isConnected = false);
    }
  }

  void _handleFaceRecognized() {
    Timer(const Duration(milliseconds: 1000), () {
      if (mounted) {
        setState(() {
          _currentPhase = AttendancePhase.livenessTransition;
        });
        _startLivenessTransition();
      }
    });
  }

  // -----------------------
  // PHASE 2: LIVENESS TRANSITION
  // -----------------------
  void _startLivenessTransition() {
    Timer(const Duration(seconds: 1), () {
      if (mounted) {
        setState(() {
          _currentPhase = AttendancePhase.livenessDetection;
        });
      }
    });
  }

  // -----------------------
  // SEND CAMERA FRAMES
  // -----------------------
  void _startFrameStream() {
    _controller.startImageStream((CameraImage image) async {
      if (_currentPhase != AttendancePhase.faceRecognition || _isFaceRecognized)
        return;

      if (_streamTimer == null || !_streamTimer!.isActive) {
        _streamTimer = Timer(const Duration(milliseconds: 500), () async {
          final Uint8List? jpegBytes = convertYUV420toImage(image);
          if (jpegBytes != null && _channel != null && _isConnected) {
            _channel!.sink.add(jpegBytes);
          }
          _streamTimer = null;
        });
      }
    });
  }

  @override
  void dispose() {
    if (_currentPhase != AttendancePhase.preparation) {
      _controller.dispose();
    }
    _channel?.sink.close();
    _streamTimer?.cancel();
    super.dispose();
  }

  // -----------------------
  // UI BUILDERS
  // -----------------------

  Widget _buildPreparationUI() {
    return Container(
      key: const ValueKey("prep"),
      color: Colors.blueAccent,
      width: double.infinity,
      height: double.infinity,
      child: const Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text("Step 1 of 2",
              style: TextStyle(color: Colors.white70, fontSize: 20)),
          SizedBox(height: 10),
          Text("Face Recognition",
              style: TextStyle(
                  color: Colors.white,
                  fontSize: 32,
                  fontWeight: FontWeight.bold)),
          SizedBox(height: 40),
          CircularProgressIndicator(
              valueColor: AlwaysStoppedAnimation<Color>(Colors.white)),
        ],
      ),
    );
  }

  Widget _buildFaceRecognitionUI() {
    return FutureBuilder<void>(
      future: _initializeControllerFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.done) {
          return Stack(
            children: [
              SizedBox.expand(child: CameraPreview(_controller)),
              // Connection Status Indicator
              Positioned(
                top: 40,
                right: 20,
                child: Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: _isConnected ? Colors.green : Colors.red,
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text(
                    _isConnected ? "Connected" : "Disconnected",
                    style: const TextStyle(color: Colors.white, fontSize: 12),
                  ),
                ),
              ),
              // Face Frame
              Center(
                child: Container(
                  width: 280,
                  height: 380,
                  decoration: BoxDecoration(
                    border: Border.all(
                      color: _isFaceRecognized
                          ? Colors.green
                          : (_isFaceDetected ? Colors.blue : Colors.white30),
                      width: 3,
                    ),
                    borderRadius: BorderRadius.circular(20),
                  ),
                ),
              ),
              // Success Overlay
              if (_isFaceRecognized)
                Center(
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 24, vertical: 12),
                    decoration: BoxDecoration(
                      color: Colors.green.withOpacity(0.8),
                      borderRadius: BorderRadius.circular(30),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.check_circle,
                            color: Colors.white, size: 28),
                        const SizedBox(width: 10),
                        Text(
                          "Welcome, $_recognizedUserName",
                          style: const TextStyle(
                              color: Colors.white,
                              fontSize: 20,
                              fontWeight: FontWeight.bold),
                        ),
                      ],
                    ),
                  ),
                ),
              // Status Message
              Positioned(
                bottom: 40,
                left: 20,
                right: 20,
                child: Container(
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    color: Colors.black54,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    _statusMessage,
                    style: const TextStyle(color: Colors.white, fontSize: 18),
                    textAlign: TextAlign.center,
                  ),
                ),
              ),
            ],
          );
        } else {
          return const Center(child: CircularProgressIndicator());
        }
      },
    );
  }

  Widget _buildLivenessTransitionUI() {
    return Container(
      key: const ValueKey("liveness_trans"),
      color: Colors.deepPurpleAccent,
      width: double.infinity,
      height: double.infinity,
      child: const Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text("Step 2 of 2",
              style: TextStyle(color: Colors.white70, fontSize: 20)),
          SizedBox(height: 10),
          Text("Liveness Detection",
              style: TextStyle(
                  color: Colors.white,
                  fontSize: 32,
                  fontWeight: FontWeight.bold)),
          SizedBox(height: 20),
          Text("Signals increased security",
              style: TextStyle(color: Colors.white60, fontSize: 16)),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: AnimatedSwitcher(
        duration: const Duration(milliseconds: 500),
        child: _buildCurrentPhaseUI(),
      ),
    );
  }

  Widget _buildCurrentPhaseUI() {
    switch (_currentPhase) {
      case AttendancePhase.preparation:
        return _buildPreparationUI();
      case AttendancePhase.faceRecognition:
        return _buildFaceRecognitionUI();
      case AttendancePhase.livenessTransition:
        return _buildLivenessTransitionUI();
      default:
        return const Center(child: Text("Next Phases Coming Soon"));
    }
  }
}
