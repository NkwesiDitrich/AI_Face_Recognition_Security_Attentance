// frontend/lib/screens/attendance_screen.dart
// ✅ FIXED: Complete attendance screen with proper state management

import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'dart:async';
import 'dart:convert';
import 'package:ai_face_attendance_frontend/utils/image_converter.dart';

enum AttendancePhase {
  preparation,
  faceRecognition,
  livenessTransition,
  livenessDetection,
  finalResult
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
  String _statusMessage = "";
  Timer? _streamTimer;
  AttendancePhase _currentPhase = AttendancePhase.preparation;

  bool _isFaceRecognized = false;
  bool _isFaceDetected = false;
  String? _recognizedUserName;
  bool _isConnected = false;
  bool _isReconnecting = false;
  int _reconnectAttempts = 0;
  Map<String, dynamic>? _faceCoords;

  // ✅ ADDED: Track recognition state to prevent reset
  bool _hasShownSuccess = false;
  Timer? _successDelayTimer;
  Timer? _reconnectionTimer;

  // CHANGE THIS to your computer's IP address when testing on a real phone!
  static const String _serverIp =
      '192.168.124.202'; // Use 'localhost' or your PC IP
  static const String _wsUrl = 'ws://$_serverIp:8000/api/v1/ws/attendance';

  @override
  void initState() {
    super.initState();
    _startPreparationPhase();
  }

  void _startPreparationPhase() {
    setState(() {
      _statusMessage = "Step 1 of 2\nFace Recognition";
    });

    Timer(const Duration(seconds: 2), () {
      if (mounted) {
        setState(() => _currentPhase = AttendancePhase.faceRecognition);
        _statusMessage = "Place your face inside the frame";
        _initializeCamera();
      }
    });
  }

  void _initializeCamera() {
    final frontCamera = widget.cameras.firstWhere(
      (c) => c.lensDirection == CameraLensDirection.front,
      orElse: () => widget.cameras.first,
    );

    _controller = CameraController(
      frontCamera,
      ResolutionPreset.high,
      enableAudio: false,
      imageFormatGroup: ImageFormatGroup.yuv420,
    );

    _initializeControllerFuture = _controller.initialize().then((_) {
      if (mounted) {
        setState(() {});
        _connectWebSocket();
        _startFrameStream();
      }
    });
  }

  void _connectWebSocket() {
    if (_isReconnecting) return;

    // Cancel any pending reconnection
    _reconnectionTimer?.cancel();

    try {
      print("🔌 Connecting to WebSocket: $_wsUrl");
      _isReconnecting = true;
      _channel = WebSocketChannel.connect(Uri.parse(_wsUrl));

      _channel!.stream.listen(
        (data) {
          if (data is String) {
            try {
              final response = jsonDecode(data);
              _processWebSocketMessage(response);
            } catch (e) {
              print("❌ Error parsing WebSocket message: $e");
            }
          }
        },
        onDone: () {
          print("👋 WebSocket disconnected");
          if (mounted) {
            setState(() {
              _isConnected = false;
              _isReconnecting = false;
            });
          }
          _reconnectWebSocket();
        },
        onError: (error) {
          print("❌ WebSocket error: $error");
          if (mounted) {
            setState(() {
              _isConnected = false;
              _isReconnecting = false;
            });
          }
          _reconnectWebSocket();
        },
      );

      if (mounted) {
        setState(() {
          _isConnected = true;
          _reconnectAttempts = 0;
          _isReconnecting = false;
        });
      }
    } catch (e) {
      print("❌ WebSocket connection failed: $e");
      if (mounted) {
        setState(() {
          _isConnected = false;
          _isReconnecting = false;
        });
      }
      _reconnectWebSocket();
    }
  }

  void _reconnectWebSocket() {
    if (_reconnectAttempts > 5) {
      print("❌ Max reconnection attempts reached");
      if (mounted) {
        setState(() {
          _statusMessage = "Connection failed. Please restart the app.";
        });
      }
      return;
    }

    _reconnectAttempts++;
    print("🔄 Reconnection attempt $_reconnectAttempts...");

    _reconnectionTimer = Timer(Duration(seconds: 2), () {
      if (mounted && !_isConnected && !_isReconnecting) {
        _connectWebSocket();
      }
    });
  }

  void _processWebSocketMessage(Map<String, dynamic> response) {
    if (!mounted) return;

    // ✅ Don't process if already shown success
    if (_hasShownSuccess) return;

    final status = response['status'];
    final faceDetected = response['face_detected'] ?? false;
    final message = response['message'] ?? "";
    final user = response['user'];

    print(
        "📨 WebSocket response: status=$status, face_detected=$faceDetected, user=$user");

    setState(() {
      _isFaceDetected = faceDetected;
      _faceCoords = response['coords'];

      if (status == 'success' && user != null) {
        // ✅ FACE RECOGNIZED!
        _hasShownSuccess = true;
        _recognizedUserName = user;
        _isFaceRecognized = true;
        _statusMessage = "✔ Face recognized\nWelcome, $user";

        // Cancel any pending timers
        _successDelayTimer?.cancel();
        _reconnectionTimer?.cancel();

        // Move to next phase after a delay
        _successDelayTimer = Timer(const Duration(milliseconds: 1500), () {
          if (mounted) {
            _handleFaceRecognized();
          }
        });
      } else if (status == 'fail' && faceDetected) {
        // Face detected but NOT registered
        _statusMessage = "❌ Face not registered\nPlease enroll first";
      } else if (status == 'no_face' || !faceDetected) {
        // No face detected - only update if not already detected
        if (!_isFaceDetected) {
          _statusMessage = "Place your face inside the frame";
        }
      } else if (status == 'processing') {
        // Still processing previous frame
        _statusMessage = "Processing...";
      } else if (status == 'error') {
        // Error occurred
        _statusMessage = "Error: $message";
      } else {
        // Other status
        _statusMessage = message;
      }
    });
  }

  void _handleFaceRecognized() {
    if (!mounted) return;

    setState(() => _currentPhase = AttendancePhase.livenessTransition);

    // Show transition screen
    Timer(const Duration(seconds: 1), () {
      if (mounted) {
        setState(() => _currentPhase = AttendancePhase.livenessDetection);
      }
    });
  }

  void _startFrameStream() {
    if (!_controller.value.isInitialized) return;

    _controller.startImageStream((CameraImage image) {
      // Only process frames during face recognition phase
      // ✅ And only if not already recognized
      if (_currentPhase != AttendancePhase.faceRecognition ||
          _hasShownSuccess ||
          !_isConnected ||
          _channel == null) {
        return;
      }

      // Rate limiting: process one frame every 500ms
      if (_streamTimer != null && _streamTimer!.isActive) {
        return;
      }

      _streamTimer = Timer(const Duration(milliseconds: 500), () {
        try {
          final bytes = convertYUV420toImage(image);
          if (bytes != null && _isConnected && _channel != null) {
            _channel!.sink.add(bytes);
          }
        } catch (e) {
          print("❌ Error sending frame: $e");
        }
        _streamTimer = null;
      });
    });
  }

  @override
  void dispose() {
    _streamTimer?.cancel();
    _successDelayTimer?.cancel();
    _reconnectionTimer?.cancel();
    _controller.dispose();
    _channel?.sink.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: AnimatedSwitcher(
        duration: const Duration(milliseconds: 500),
        child: _buildCurrentUI(),
      ),
    );
  }

  Widget _buildCurrentUI() {
    switch (_currentPhase) {
      case AttendancePhase.preparation:
        return _buildPrepUI();
      case AttendancePhase.livenessTransition:
        return _buildTransitionUI();
      case AttendancePhase.livenessDetection:
        return _buildLivenessUI();
      case AttendancePhase.faceRecognition:
      default:
        return _buildRecognitionUI();
    }
  }

  Widget _buildPrepUI() {
    return Container(
      key: const ValueKey("prep"),
      color: Colors.blueAccent,
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text("Step 1 of 2",
                style: TextStyle(color: Colors.white70, fontSize: 18)),
            const SizedBox(height: 10),
            const Text("Face Recognition",
                style: TextStyle(
                    color: Colors.white,
                    fontSize: 28,
                    fontWeight: FontWeight.bold)),
          ],
        ),
      ),
    );
  }

  Widget _buildRecognitionUI() {
    return Stack(
      children: [
        // Camera preview
        SizedBox.expand(
          child: CameraPreview(_controller),
        ),

        // Face frame overlay
        if (_faceCoords != null)
          Positioned(
            left: _faceCoords!['x'] * MediaQuery.of(context).size.width,
            top: _faceCoords!['y'] * MediaQuery.of(context).size.height,
            width: _faceCoords!['w'] * MediaQuery.of(context).size.width,
            height: _faceCoords!['h'] * MediaQuery.of(context).size.height,
            child: Container(
              decoration: BoxDecoration(
                border: Border.all(color: Colors.green, width: 3),
                borderRadius: BorderRadius.circular(10),
              ),
            ),
          ),

        // Status overlay
        Positioned(
          bottom: 20,
          left: 20,
          right: 20,
          child: Container(
            padding: const EdgeInsets.all(15),
            decoration: BoxDecoration(
              color: Colors.black54,
              borderRadius: BorderRadius.circular(10),
            ),
            child: Column(
              children: [
                Text(
                  _statusMessage,
                  textAlign: TextAlign.center,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 18,
                  ),
                ),
                const SizedBox(height: 10),
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(
                      _isConnected ? Icons.cloud_done : Icons.cloud_off,
                      color: _isConnected ? Colors.green : Colors.red,
                    ),
                    const SizedBox(width: 5),
                    Text(
                      _isConnected ? "Connected" : "Disconnected",
                      style: TextStyle(
                        color: _isConnected ? Colors.green : Colors.red,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildTransitionUI() {
    return Container(
      color: Colors.purpleAccent,
      child: const Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text("Step 2 of 2",
                style: TextStyle(color: Colors.white70, fontSize: 18)),
            SizedBox(height: 10),
            Text("Liveness Detection",
                style: TextStyle(
                    color: Colors.white,
                    fontSize: 28,
                    fontWeight: FontWeight.bold)),
          ],
        ),
      ),
    );
  }

  Widget _buildLivenessUI() {
    return Container(
      color: Colors.purple,
      child: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.face, size: 100, color: Colors.white),
            const SizedBox(height: 20),
            const Text("Liveness Detection",
                style: TextStyle(
                    color: Colors.white,
                    fontSize: 28,
                    fontWeight: FontWeight.bold)),
            const SizedBox(height: 10),
            const Text("Please reproduce the emoji expression",
                style: TextStyle(color: Colors.white70, fontSize: 16)),
          ],
        ),
      ),
    );
  }
}
