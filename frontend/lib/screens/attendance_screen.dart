// frontend/lib/screens/attendance_screen.dart
// ✅ FIXED PHASE 1 - WITH ML KIT FACE DETECTION (Simple File-Based Approach)

import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:google_mlkit_face_detection/google_mlkit_face_detection.dart';
import 'package:path_provider/path_provider.dart';
import 'package:path/path.dart' as path;
import 'dart:io';
import 'dart:async';
import 'dart:convert';
import 'dart:ui';
import 'package:image/image.dart' as img;
import 'package:ai_face_attendance_frontend/utils/image_converter.dart';

enum AttendancePhase {
  phase0, // Entry Animation (1.5s)
  phase1, // Face Recognition (Camera + ML Kit + Send)
  phase2, // Transition Animation (1s)
  liveness, // Liveness Detection (Next)
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

  // ML Kit Face Detector
  late FaceDetector _faceDetector;

  WebSocketChannel? _channel;
  String _statusMessage = "";
  Timer? _streamTimer;
  Timer? _successTimer;
  AttendancePhase _currentPhase = AttendancePhase.phase0;

  // WebSocket state
  bool _isConnected = false;
  bool _isReconnecting = false;
  int _reconnectAttempts = 0;
  Timer? _reconnectionTimer;

  // Recognition state
  bool _hasShownSuccess = false;
  String? _recognizedUserName;

  // Face detection state
  bool _faceDetected = false;
  bool _faceIsValid = false;
  Size? _faceSize;
  Offset? _facePosition;
  double? _headAngle;

  // ML Kit quality thresholds
  static const double MIN_FACE_SIZE = 120.0;
  static const double CENTER_TOLERANCE = 0.20;
  static const double MAX_HEAD_ANGLE = 15.0;

  // CHANGE THIS to your computer's IP address
  static const String _serverIp = '192.168.165.202';
  static const String _wsUrl = 'ws://$_serverIp:8000/api/v1/ws/attendance';

  @override
  void initState() {
    super.initState();

    // Initialize ML Kit Face Detector
    _faceDetector = FaceDetector(
      options: FaceDetectorOptions(
        enableLandmarks: true,
        enableContours: true,
        enableClassification: true,
        minFaceSize: 0.1,
      ),
    );

    _startPhase0();
  }

  @override
  void dispose() {
    _streamTimer?.cancel();
    _successTimer?.cancel();
    _reconnectionTimer?.cancel();
    _faceDetector.close();
    _controller.dispose();
    _channel?.sink.close();
    super.dispose();
  }

  // ═══════════════════════════════════════════════════════════════════
  // PHASE 0: ENTRY ANIMATION (Preparation)
  // ═══════════════════════════════════════════════════════════════════
  void _startPhase0() {
    setState(() {
      _currentPhase = AttendancePhase.phase0;
      _statusMessage = "Step 1 of 2\nFace Recognition";
    });

    Timer(const Duration(milliseconds: 1500), () {
      if (mounted) {
        _startPhase1();
      }
    });
  }

  void _startPhase1() {
    setState(() {
      _currentPhase = AttendancePhase.phase1;
      _statusMessage = "Place your face inside the frame";
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
        _startFrameAnalysis();
      }
    });
  }

  // ═══════════════════════════════════════════════════════════════════
  // ML KIT FACE DETECTION & QUALITY VALIDATION
  // ═══════════════════════════════════════════════════════════════════
  void _startFrameAnalysis() {
    if (!_controller.value.isInitialized) return;

    _controller.startImageStream((CameraImage image) {
      if (_currentPhase != AttendancePhase.phase1 ||
          _hasShownSuccess ||
          !_isConnected ||
          _channel == null) {
        return;
      }

      if (_streamTimer != null && _streamTimer!.isActive) {
        return;
      }

      _streamTimer = Timer(const Duration(milliseconds: 300), () async {
        await _analyzeFrameWithMLKit(image);
        _streamTimer = null;
      });
    });
  }

  Future<void> _analyzeFrameWithMLKit(CameraImage image) async {
    try {
      // Save image to temp file
      final imageFile = await _saveImageToTempFile(image);

      // Create InputImage from file
      final inputImage = InputImage.fromFile(imageFile);

      // Detect faces
      final List<Face> faces = await _faceDetector.processImage(inputImage);

      // Delete temp file
      imageFile.deleteSync();

      if (!mounted) return;

      if (faces.isEmpty) {
        setState(() {
          _faceDetected = false;
          _faceIsValid = false;
          _faceSize = null;
          _facePosition = null;
          _headAngle = null;
          _statusMessage = "Place your face inside the frame";
        });
        return;
      }

      // Get the largest face
      final face = faces.reduce((a, b) =>
          (a.boundingBox.width * a.boundingBox.height) >
                  (b.boundingBox.width * b.boundingBox.height)
              ? a
              : b);

      final faceRect = face.boundingBox;
      final faceWidth = faceRect.width;
      final faceHeight = faceRect.height;
      final faceCenterX = faceRect.center.dx;
      final faceCenterY = faceRect.center.dy;

      final headAngleY = face.headEulerAngleY;
      final headAngleX = face.headEulerAngleX;

      final screenSize = MediaQuery.of(context).size;
      final screenCenterX = screenSize.width / 2;
      final screenCenterY = screenSize.height / 2;

      final offsetX = (faceCenterX - screenCenterX) / screenCenterX;
      final offsetY = (faceCenterY - screenCenterY) / screenCenterY;

      setState(() {
        _faceDetected = true;
        _faceSize = Size(faceWidth, faceHeight);
        _facePosition = Offset(faceCenterX, faceCenterY);
        _headAngle = headAngleY;
      });

      // Quality validation
      bool isValid = true;
      List<String> validationErrors = [];

      // Check 1: Face size
      if (faceWidth < MIN_FACE_SIZE || faceHeight < MIN_FACE_SIZE) {
        isValid = false;
        validationErrors.add("Move closer");
      }

      // Check 2: Face centered
      if (offsetX.abs() > CENTER_TOLERANCE ||
          offsetY.abs() > CENTER_TOLERANCE) {
        isValid = false;
        if (offsetX.abs() > CENTER_TOLERANCE) {
          validationErrors.add(offsetX > 0 ? "Move left" : "Move right");
        }
        if (offsetY.abs() > CENTER_TOLERANCE) {
          validationErrors.add(offsetY > 0 ? "Move up" : "Move down");
        }
      }

      // Check 3: Head not tilted
      if (headAngleY != null && headAngleY.abs() > MAX_HEAD_ANGLE) {
        isValid = false;
        validationErrors.add("Don't turn your head");
      }

      // Check 4: Eyes open
      if (face.leftEyeOpenProbability != null &&
          face.rightEyeOpenProbability != null) {
        final avgEyeOpen =
            (face.leftEyeOpenProbability! + face.rightEyeOpenProbability!) / 2;
        if (avgEyeOpen < 0.3) {
          validationErrors.add("Open your eyes");
        }
      }

      _faceIsValid = isValid;

      if (!isValid) {
        setState(() {
          _statusMessage = validationErrors.isNotEmpty
              ? validationErrors.join("\n")
              : "Adjust your face position";
        });
        return;
      }

      // Valid face - send to backend
      setState(() {
        _statusMessage = "Hold still...";
      });

      await _sendFrameToBackend(image);
    } catch (e) {
      debugPrint("❌ ML Kit analysis error: $e");
    }
  }

  // Save camera image to temp file
  Future<File> _saveImageToTempFile(CameraImage image) async {
    // Convert YUV to JPEG
    final bytes = convertYUV420toImage(image);
    if (bytes == null) {
      throw Exception("Failed to convert image");
    }

    // Decode image
    final img.Image? decodedImage = img.decodeImage(bytes);
    if (decodedImage == null) {
      throw Exception("Failed to decode image");
    }

    // Encode as JPEG
    final jpegBytes = img.encodeJpg(decodedImage, quality: 85);

    // Save to temp directory
    final tempDir = await getTemporaryDirectory();
    final tempFile = File(
        '${tempDir.path}/mlkit_${DateTime.now().millisecondsSinceEpoch}.jpg');
    await tempFile.writeAsBytes(jpegBytes);

    return tempFile;
  }

  // ═══════════════════════════════════════════════════════════════════
  // SEND TO BACKEND (Only for valid faces!)
  // ═══════════════════════════════════════════════════════════════════
  Future<void> _sendFrameToBackend(CameraImage image) async {
    if (!_isConnected || _channel == null || _hasShownSuccess) return;

    try {
      final bytes = convertYUV420toImage(image);
      if (bytes != null) {
        _channel!.sink.add(bytes);
        debugPrint("📤 Sent VALID face frame to backend");
      }
    } catch (e) {
      debugPrint("❌ Error sending frame: $e");
    }
  }

  // ═══════════════════════════════════════════════════════════════════
  // WEBSOCKET CONNECTION
  // ═══════════════════════════════════════════════════════════════════
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
              debugPrint("❌ Error parsing WebSocket message: $e");
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
      if (mounted) {
        setState(() {
          _statusMessage = "Connection failed. Please restart.";
        });
      }
      return;
    }

    _reconnectAttempts++;
    print("🔄 Reconnection attempt $_reconnectAttempts...");

    _reconnectionTimer = Timer(const Duration(seconds: 2), () {
      if (mounted && !_isConnected && !_isReconnecting) {
        _connectWebSocket();
      }
    });
  }

  // ═══════════════════════════════════════════════════════════════════
  // BACKEND RESPONSE HANDLING
  // ═══════════════════════════════════════════════════════════════════
  void _processWebSocketMessage(Map<String, dynamic> response) {
    if (!mounted) return;
    if (_hasShownSuccess) return;

    final status = response['status'];
    final user = response['user'];
    final message = response['message'] ?? "";

    print("📨 WebSocket: status=$status, message=$message");

    setState(() {
      if (status == 'recognized' && user != null) {
        _hasShownSuccess = true;
        _recognizedUserName = user['name'];
        _statusMessage = "✔ Face recognized";

        _streamTimer?.cancel();

        _successTimer?.cancel();
        _successTimer = Timer(const Duration(milliseconds: 1000), () {
          if (mounted) {
            _startPhase2();
          }
        });
      } else if (status == 'not_recognized') {
        _statusMessage = "Face not registered\nPlease enroll first";
      } else if (status == 'no_face' || status == 'no_embedding') {
        _statusMessage = "Try again";
      } else if (status == 'processing') {
        // Keep current message
      } else {
        _statusMessage = message;
      }
    });
  }

  // ═══════════════════════════════════════════════════════════════════
  // PHASE 2: TRANSITION
  // ═══════════════════════════════════════════════════════════════════
  void _startPhase2() {
    if (!mounted) return;

    setState(() {
      _currentPhase = AttendancePhase.phase2;
      _statusMessage = "Step 2 of 2\nLiveness Detection";
    });

    Timer(const Duration(milliseconds: 1000), () {
      if (mounted) {
        setState(() {
          _currentPhase = AttendancePhase.liveness;
        });
      }
    });
  }

  // ═══════════════════════════════════════════════════════════════════
  // UI BUILDERS
  // ═══════════════════════════════════════════════════════════════════
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
            Icon(Icons.face, size: 80, color: Colors.white),
            SizedBox(height: 20),
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

    Color statusColor;
    IconData statusIcon;
    String statusText;

    if (_hasShownSuccess) {
      statusColor = Colors.green;
      statusIcon = Icons.check_circle;
      statusText = "✔ Face recognized\nWelcome, $_recognizedUserName";
    } else if (_faceIsValid) {
      statusColor = Colors.orange;
      statusIcon = Icons.hourglass_empty;
      statusText = "Hold still...";
    } else if (_faceDetected) {
      statusColor = Colors.red;
      statusIcon = Icons.warning;
      statusText = _statusMessage;
    } else {
      statusColor = Colors.blue;
      statusIcon = Icons.face;
      statusText = _statusMessage;
    }

    final screenSize = MediaQuery.of(context).size;
    final frameSize = screenSize.width * 0.80;
    final frameLeft = (screenSize.width - frameSize) / 2;
    final frameTop = (screenSize.height - frameSize) / 2;

    return Stack(
      children: [
        SizedBox.expand(
          child: CameraPreview(_controller),
        ),
        Positioned(
          left: frameLeft,
          top: frameTop,
          child: Container(
            width: frameSize,
            height: frameSize,
            decoration: BoxDecoration(
              border: Border.all(
                color: _hasShownSuccess
                    ? Colors.green
                    : (_faceIsValid
                        ? Colors.orange
                        : (_faceDetected ? Colors.red : Colors.white)),
                width: 4,
              ),
              borderRadius: BorderRadius.circular(20),
            ),
          ),
        ),
        if (_faceSize != null && _facePosition != null && !_hasShownSuccess)
          Positioned(
            left: _facePosition!.dx - (_faceSize!.width / 2),
            top: _facePosition!.dy - (_faceSize!.height / 2),
            child: Container(
              width: _faceSize!.width,
              height: _faceSize!.height,
              decoration: BoxDecoration(
                border:
                    Border.all(color: Colors.green.withOpacity(0.8), width: 2),
                borderRadius: BorderRadius.circular(10),
              ),
            ),
          ),
        Positioned(
          bottom: 30,
          left: 20,
          right: 20,
          child: Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: Colors.black54,
              borderRadius: BorderRadius.circular(10),
            ),
            child: Column(
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(statusIcon, color: statusColor, size: 24),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        statusText,
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                  ],
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
                    const SizedBox(width: 20),
                    Icon(
                      _faceIsValid
                          ? Icons.check_circle
                          : (_faceDetected ? Icons.warning : Icons.face),
                      color: _faceIsValid
                          ? Colors.green
                          : (_faceDetected ? Colors.orange : Colors.white54),
                    ),
                    const SizedBox(width: 5),
                    Text(
                      _faceIsValid
                          ? "Valid face"
                          : (_faceDetected ? "Adjust position" : "No face"),
                      style: TextStyle(
                        color: _faceIsValid
                            ? Colors.green
                            : (_faceDetected ? Colors.orange : Colors.white54),
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

  Widget _buildPhase2UI() {
    return Container(
      key: const ValueKey("phase2"),
      color: Colors.blueGrey,
      child: const Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.security, size: 80, color: Colors.white),
            SizedBox(height: 20),
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
        child: Text(
          "Liveness Detection\n(Coming next...)",
          style: TextStyle(
              color: Colors.white, fontSize: 24, fontWeight: FontWeight.bold),
          textAlign: TextAlign.center,
        ),
      ),
    );
  }
}
