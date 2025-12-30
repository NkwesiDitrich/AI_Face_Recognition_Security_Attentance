// frontend/lib/screens/attendance_screen.dart
// ✅ COMPLETE FIXED: 3x larger frame + proper recognition flow

import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'dart:async';
import 'dart:convert';
import 'package:ai_face_attendance_frontend/utils/image_converter.dart';

enum AttendancePhase {
  preparation,
  faceDetection,
  recognitionTrigger,
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

  bool _isConnected = false;
  bool _isReconnecting = false;
  int _reconnectAttempts = 0;

  // Face detection state
  bool _faceDetected = false;
  Map<String, dynamic>? _faceData;

  // Frame settings - 3x LARGER (135% of screen width)
  static const double FRAME_SIZE_RATIO = 1.35;

  // Face size thresholds
  static const double MIN_FACE_SIZE_PERCENT = 15;
  static const double MAX_FACE_SIZE_PERCENT = 50;

  // Stability detection
  DateTime? _faceStableStartTime;
  static const Duration STABLE_DURATION = Duration(milliseconds: 800);
  bool _isFaceStable = false;

  // Recognition state
  bool _recognitionTriggered = false;
  bool _hasShownSuccess = false;
  String? _recognizedUserName;
  Timer? _successDelayTimer;
  Timer? _reconnectionTimer;

  // CHANGE THIS to your computer's IP address
  static const String _serverIp = '192.168.124.202';
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
        setState(() {
          _currentPhase = AttendancePhase.faceDetection;
          _statusMessage = "Place your face inside the frame";
        });
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
    if (_hasShownSuccess) return;

    final status = response['status'];
    final faceDetected = response['face_detected'] ?? false;
    final message = response['message'] ?? "";
    final user = response['user'];
    final face = response['face'];

    print(
        "📨 WebSocket: status=$status, face_detected=$faceDetected, user=$user");

    setState(() {
      _faceDetected = faceDetected;
      _faceData = face != null ? Map<String, dynamic>.from(face) : null;

      if (status == 'success' && user != null) {
        _hasShownSuccess = true;
        _recognizedUserName = user;
        _statusMessage = "✔ Face recognized\nWelcome, $user";

        _successDelayTimer?.cancel();
        _reconnectionTimer?.cancel();

        _successDelayTimer = Timer(const Duration(milliseconds: 1500), () {
          if (mounted) {
            _handleFaceRecognized();
          }
        });
      } else if (status == 'fail' && faceDetected) {
        _statusMessage = "❌ Face not registered\nPlease enroll first";
        _faceStableStartTime = null;
        _isFaceStable = false;
        _recognitionTriggered = false;
      } else if (status == 'face_detected') {
        _handleFaceDetection(face);
      } else if (status == 'no_face' || !faceDetected) {
        _faceData = null;
        _faceStableStartTime = null;
        _isFaceStable = false;
        _recognitionTriggered = false;
        _statusMessage = "Place your face inside the frame";
      } else if (status == 'processing') {
        _statusMessage = "Processing...";
      } else if (status == 'error') {
        _statusMessage = "Error: $message";
      } else {
        _statusMessage = message;
      }
    });
  }

  void _handleFaceDetection(Map<String, dynamic>? faceData) {
    if (faceData == null) {
      _statusMessage = "Place your face inside the frame";
      return;
    }

    final faceX = faceData['x'] ?? 0;
    final faceY = faceData['y'] ?? 0;
    final faceW = faceData['w'] ?? 0;
    final faceH = faceData['h'] ?? 0;
    final faceSize = faceData['size_percent'] ?? 0;

    final frameLeft = (1.0 - FRAME_SIZE_RATIO) / 2;
    final frameRight = frameLeft + FRAME_SIZE_RATIO;
    final frameTop = (1.0 - FRAME_SIZE_RATIO) / 2;
    final frameBottom = frameTop + FRAME_SIZE_RATIO;

    final faceInsideFrame = faceX >= frameLeft &&
        faceX + faceW <= frameRight &&
        faceY >= frameTop &&
        faceY + faceH <= frameBottom;

    final faceTooSmall = faceSize < MIN_FACE_SIZE_PERCENT;
    final faceTooBig = faceSize > MAX_FACE_SIZE_PERCENT;

    if (!faceInsideFrame) {
      _statusMessage = "Center your face";
      _faceStableStartTime = null;
      _isFaceStable = false;
      _recognitionTriggered = false;
    } else if (faceTooSmall) {
      _statusMessage = "Move closer";
      _faceStableStartTime = null;
      _isFaceStable = false;
      _recognitionTriggered = false;
    } else if (faceTooBig) {
      _statusMessage = "Move back";
      _faceStableStartTime = null;
      _isFaceStable = false;
      _recognitionTriggered = false;
    } else {
      if (_faceStableStartTime == null) {
        _faceStableStartTime = DateTime.now();
        _statusMessage = "Hold still...";
      } else {
        final DateTime stableStart = _faceStableStartTime!;
        final elapsed = DateTime.now().difference(stableStart);
        if (elapsed >= STABLE_DURATION) {
          if (!_recognitionTriggered) {
            _recognitionTriggered = true;
            _isFaceStable = true;
            _statusMessage = "🔄 Recognizing...";
          }
        } else {
          final remaining = (STABLE_DURATION - elapsed).inMilliseconds;
          _statusMessage =
              "Hold still... ${(remaining / 1000).toStringAsFixed(1)}s";
        }
      }
    }
  }

  void _handleFaceRecognized() {
    if (!mounted) return;
    setState(() => _currentPhase = AttendancePhase.livenessTransition);

    Timer(const Duration(seconds: 1), () {
      if (mounted) {
        setState(() => _currentPhase = AttendancePhase.livenessDetection);
      }
    });
  }

  void _startFrameStream() {
    if (!_controller.value.isInitialized) return;

    _controller.startImageStream((CameraImage image) {
      if (_currentPhase != AttendancePhase.faceDetection ||
          _hasShownSuccess ||
          _recognitionTriggered ||
          !_isConnected ||
          _channel == null) {
        return;
      }

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
      case AttendancePhase.faceDetection:
      default:
        return _buildFaceDetectionUI();
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

  Widget _buildFaceDetectionUI() {
    final screenWidth = MediaQuery.of(context).size.width;
    final screenHeight = MediaQuery.of(context).size.height;
    final frameSize = screenWidth * FRAME_SIZE_RATIO;

    final frameLeft = (screenWidth - frameSize) / 2;
    final frameTop = (screenHeight - frameSize) / 2;

    Color frameColor;
    if (_recognitionTriggered) {
      frameColor = Colors.blue;
    } else if (_isFaceStable) {
      frameColor = Colors.green;
    } else if (_faceDetected) {
      frameColor = Colors.orange;
    } else {
      frameColor = Colors.white;
    }

    return Stack(
      children: [
        SizedBox.expand(
          child: CameraPreview(_controller),
        ),

        // 3x LARGER GUIDE FRAME (135% of screen width)
        Positioned(
          left: frameLeft,
          top: frameTop,
          child: Container(
            width: frameSize,
            height: frameSize,
            decoration: BoxDecoration(
              border: Border.all(color: frameColor, width: 4),
              borderRadius: BorderRadius.circular(30),
            ),
            child: Stack(
              children: [
                _buildCornerMarker(frameColor, true, true),
                _buildCornerMarker(frameColor, true, false),
                _buildCornerMarker(frameColor, false, true),
                _buildCornerMarker(frameColor, false, false),
                if (!_faceDetected)
                  Center(
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 15, vertical: 8),
                      decoration: BoxDecoration(
                        color: Colors.black54,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: const Text(
                        "Put your face here",
                        style: TextStyle(color: Colors.white, fontSize: 14),
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),

        // Size indicator
        Positioned(
          top: frameTop - 60,
          left: 0,
          right: 0,
          child: Center(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 5),
              decoration: BoxDecoration(
                color: Colors.black54,
                borderRadius: BorderRadius.circular(5),
              ),
              child: Text(
                _faceDetected
                    ? "Face size: ${_faceData?['size_percent']?.toStringAsFixed(0) ?? 0}%"
                    : "Frame: ${(FRAME_SIZE_RATIO * 100).toStringAsFixed(0)}% of screen",
                style: const TextStyle(color: Colors.white, fontSize: 12),
              ),
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
                    fontWeight: FontWeight.bold,
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

  Widget _buildCornerMarker(Color color, bool isTop, bool isLeft) {
    final width = isTop ? 40 : 30;
    final height = isTop ? 30 : 40;

    return Positioned(
      top: isTop ? -4 : null,
      bottom: isTop ? null : -4,
      left: isLeft ? -4 : null,
      right: isLeft ? null : -4,
      child: Container(
        width: width.toDouble(),
        height: height.toDouble(),
        decoration: BoxDecoration(
          border: Border(
            top: isTop ? BorderSide(color: color, width: 6) : BorderSide.none,
            bottom:
                isTop ? BorderSide.none : BorderSide(color: color, width: 6),
            left: isLeft ? BorderSide(color: color, width: 6) : BorderSide.none,
            right:
                isLeft ? BorderSide.none : BorderSide(color: color, width: 6),
          ),
          borderRadius: BorderRadius.circular(10),
        ),
      ),
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
