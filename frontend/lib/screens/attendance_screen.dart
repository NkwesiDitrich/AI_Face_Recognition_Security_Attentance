// frontend/lib/screens/attendance_screen.dart

import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'dart:async';
import 'dart:convert';
import 'package:ai_face_attendance_frontend/utils/image_converter.dart';

enum AttendancePhase {
  phase0, // Entry Animation
  phase1, // Face Recognition
  phase2, // Transition Animation
  liveness, // Liveness Detection (Next stage)
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
  AttendancePhase _currentPhase = AttendancePhase.phase0;

  bool _isConnected = false;
  bool _isReconnecting = false;
  int _reconnectAttempts = 0;

  // Recognition state
  bool _faceDetected = false;
  bool _isRecognized = false;
  String? _recognizedUserName;
  String? _recognizedUserId;

  // CHANGE THIS to your computer's IP address
  static const String _serverIp = '192.168.156.202';
  static const String _wsUrl = 'ws://$_serverIp:8000/api/v1/ws/attendance';

  @override
  void initState() {
    super.initState();
    _startPhase0();
  }

  void _startPhase0() {
    setState(() {
      _currentPhase = AttendancePhase.phase0;
    });

    Timer(const Duration(seconds: 2), () {
      if (mounted) {
        _startPhase1();
      }
    });
  }

  void _startPhase1() {
    setState(() {
      _currentPhase = AttendancePhase.phase1;
    });
    _initializeCamera();
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

    try {
      _isReconnecting = true;
      _channel = WebSocketChannel.connect(Uri.parse(_wsUrl));

      _channel!.stream.listen(
        (data) {
          if (data is String) {
            try {
              final response = jsonDecode(data);
              _processWebSocketMessage(response);
            } catch (e) {
              debugPrint("❌ Error parsing WebSocket message: $e");
            }
          }
        },
        onDone: () {
          if (mounted) {
            setState(() {
              _isConnected = false;
              _isReconnecting = false;
            });
          }
          _reconnectWebSocket();
        },
        onError: (error) {
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
    if (_reconnectAttempts > 5) return;
    _reconnectAttempts++;
    Timer(const Duration(seconds: 2), () {
      if (mounted && !_isConnected && !_isReconnecting) {
        _connectWebSocket();
      }
    });
  }

  void _processWebSocketMessage(Map<String, dynamic> response) {
    if (!mounted) return;
    if (_isRecognized) return;

    final status = response['status'];
    final name = response['name'];
    final userId = response['user_id'];
    final faceDetected = response['face_detected'] ?? false;

    setState(() {
      _faceDetected = faceDetected;

      if (status == 'success') {
        _isRecognized = true;
        _recognizedUserName = name;
        _recognizedUserId = userId;
        _statusMessage = "✔ Face recognized";

        // Stop recognition and proceed to Phase 2 after delay
        Timer(const Duration(milliseconds: 1000), () {
          if (mounted) {
            _startPhase2();
          }
        });
      } else if (status == 'no_face') {
        _statusMessage = "Place your face inside the frame";
      } else if (status == 'not_recognized') {
        _statusMessage = "Face detected but not registered";
      } else if (status == 'processing') {
        // Keep current message
      } else {
        _statusMessage =
            response['message'] ?? "Place your face inside the frame";
      }
    });
  }

  void _startPhase2() {
    setState(() {
      _currentPhase = AttendancePhase.phase2;
    });

    Timer(const Duration(seconds: 1), () {
      if (mounted) {
        setState(() {
          _currentPhase = AttendancePhase.liveness;
        });
      }
    });
  }

  void _startFrameStream() {
    if (!_controller.value.isInitialized) return;

    _controller.startImageStream((CameraImage image) {
      if (_currentPhase != AttendancePhase.phase1 ||
          _isRecognized ||
          !_isConnected ||
          _channel == null) {
        return;
      }

      if (_streamTimer != null && _streamTimer!.isActive) {
        return;
      }

      _streamTimer = Timer(const Duration(milliseconds: 300), () {
        try {
          final bytes = convertYUV420toImage(image);
          if (bytes != null && _isConnected && _channel != null) {
            _channel!.sink.add(bytes);
          }
        } catch (e) {
          debugPrint("❌ Error sending frame: $e");
        }
        _streamTimer = null;
      });
    });
  }

  @override
  void dispose() {
    _streamTimer?.cancel();
    _controller.dispose();
    _channel?.sink.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: _currentPhase == AttendancePhase.phase1
          ? AppBar(title: const Text("Real-time Attendance"), elevation: 0)
          : null,
      body: AnimatedSwitcher(
        duration: const Duration(milliseconds: 500),
        child: _buildCurrentUI(),
      ),
    );
  }

  Widget _buildCurrentUI() {
    switch (_currentPhase) {
      case AttendancePhase.phase0:
        return _buildPhase0UI();
      case AttendancePhase.phase1:
        return _buildPhase1UI();
      case AttendancePhase.phase2:
        return _buildPhase2UI();
      case AttendancePhase.liveness:
        return _buildLivenessUI();
    }
  }

  Widget _buildPhase0UI() {
    return Container(
      key: const ValueKey("phase0"),
      color: Colors.blueAccent,
      child: const Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text("Step 1 of 2",
                style: TextStyle(color: Colors.white70, fontSize: 18)),
            SizedBox(height: 10),
            Text("Face Recognition",
                style: TextStyle(
                    color: Colors.white,
                    fontSize: 28,
                    fontWeight: FontWeight.bold)),
          ],
        ),
      ),
    );
  }

  Widget _buildPhase1UI() {
    if (!_controller.value.isInitialized) {
      return const Center(child: CircularProgressIndicator());
    }

    Color frameColor = Colors.blue;
    if (_isRecognized) {
      frameColor = Colors.green;
    } else if (_statusMessage == "Face detected but not registered") {
      frameColor = Colors.red;
    } else if (_faceDetected) {
      frameColor = Colors.orange;
    }

    return SingleChildScrollView(
      key: const ValueKey("phase1"),
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // =====================================================
          // CAMERA PREVIEW SECTION (EXACT MATCH WITH ENROLLMENT)
          // =====================================================
          Container(
            decoration: BoxDecoration(
              border: Border.all(
                color: frameColor,
                width: 2,
              ),
              borderRadius: BorderRadius.circular(8),
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(6),
              child: SizedBox(
                height: 300, // Exact height from enrollment_screen.dart
                child: Stack(
                  fit: StackFit.expand, // Ensure children fill the box
                  children: [
                    CameraPreview(_controller),
                    if (_isRecognized)
                      Container(
                        color: Colors.green.withOpacity(0.3),
                        child: const Center(
                          child: Icon(Icons.check_circle,
                              color: Colors.white, size: 80),
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ),

          const SizedBox(height: 20),

          // =====================================================
          // STATUS MESSAGE SECTION
          // =====================================================
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: frameColor.withOpacity(0.1),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(
                color: frameColor.withOpacity(0.3),
              ),
            ),
            child: Column(
              children: [
                if (_faceDetected && !_isRecognized)
                  const Text(
                    "Face Detected! Hold still...",
                    style: TextStyle(
                        color: Colors.orange,
                        fontSize: 16,
                        fontWeight: FontWeight.bold),
                  ),
                const SizedBox(height: 8),
                Text(
                  _statusMessage,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                      color: frameColor == Colors.blue
                          ? Colors.black87
                          : frameColor,
                      fontSize: 18,
                      fontWeight: FontWeight.bold),
                ),
                if (_isRecognized) ...[
                  const SizedBox(height: 10),
                  Text(
                    "Welcome, $_recognizedUserName",
                    style: const TextStyle(
                        color: Colors.green,
                        fontSize: 20,
                        fontWeight: FontWeight.bold),
                  ),
                ]
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPhase2UI() {
    return Container(
      key: const ValueKey("phase2"),
      color: Colors.blueGrey,
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
      key: const ValueKey("liveness"),
      color: Colors.purple,
      child: const Center(
        child: Text("Liveness Detection Stage",
            style: TextStyle(
                color: Colors.white,
                fontSize: 24,
                fontWeight: FontWeight.bold)),
      ),
    );
  }
}
