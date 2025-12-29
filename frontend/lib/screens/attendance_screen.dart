// frontend/lib/screens/attendance_screen.dart

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
  String _statusMessage = "Place your face inside the frame";
  Timer? _streamTimer;
  AttendancePhase _currentPhase = AttendancePhase.preparation;

  bool _isFaceRecognized = false;
  bool _isFaceDetected = false;
  String? _recognizedUserName;
  bool _isConnected = false;
  Map<String, dynamic>? _faceCoords;

  // CHANGE THIS to your computer's IP address when testing on a real phone!
  static const String _serverIp = '127.0.0.1'; // Use 'localhost' or your PC IP
  static const String _wsUrl = 'ws://$_serverIp:8000/api/v1/ws/attendance';

  @override
  void initState() {
    super.initState();
    _startPreparationPhase();
  }

  void _startPreparationPhase() {
    Timer(const Duration(seconds: 2), () {
      if (mounted) {
        setState(() => _currentPhase = AttendancePhase.faceRecognition);
        _initializeCamera();
        _connectWebSocket();
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
      ResolutionPreset.high, // Increased resolution for better detection
      enableAudio: false,
      imageFormatGroup: ImageFormatGroup.yuv420,
    );

    _initializeControllerFuture = _controller.initialize().then((_) {
      if (mounted) _startFrameStream();
    });
  }

  void _connectWebSocket() {
    try {
      print("🔗 Connecting to WebSocket: $_wsUrl");
      _channel = WebSocketChannel.connect(Uri.parse(_wsUrl));
      setState(() => _isConnected = true);

      _channel!.stream.listen(
        (data) {
          if (_currentPhase != AttendancePhase.faceRecognition ||
              _isFaceRecognized) return;

          final response = jsonDecode(data);
          if (mounted) {
            setState(() {
              _isFaceDetected = response['face_detected'] ?? false;
              _faceCoords = response['coords'];

              if (response['status'] == 'success') {
                _isFaceRecognized = true;
                _recognizedUserName = response['user'];
                _statusMessage = "✔ Face recognized";
                _handleFaceRecognized();
              } else {
                _statusMessage = response['message'] ?? "Processing...";
              }
            });
          }
        },
        onDone: () {
          print("🔌 WebSocket disconnected");
          if (mounted) setState(() => _isConnected = false);
        },
        onError: (error) {
          print("❌ WebSocket error: $error");
          if (mounted) setState(() => _isConnected = false);
        },
      );
    } catch (e) {
      print("❌ WebSocket connection failed: $e");
      setState(() => _isConnected = false);
    }
  }

  void _handleFaceRecognized() {
    Timer(const Duration(milliseconds: 1000), () {
      if (mounted) {
        setState(() => _currentPhase = AttendancePhase.livenessTransition);
        _startTransitionPhase();
      }
    });
  }

  void _startTransitionPhase() {
    Timer(const Duration(seconds: 1), () {
      if (mounted) {
        setState(() => _currentPhase = AttendancePhase.livenessDetection);
      }
    });
  }

  void _startFrameStream() {
    _controller.startImageStream((image) {
      if (_currentPhase != AttendancePhase.faceRecognition || _isFaceRecognized)
        return;

      // Stream every 400ms for a good balance of speed and detection
      if (_streamTimer == null || !_streamTimer!.isActive) {
        _streamTimer = Timer(const Duration(milliseconds: 400), () {
          final bytes = convertYUV420toImage(image);
          if (bytes != null && _isConnected) {
            _channel?.sink.add(bytes);
          }
          _streamTimer = null;
        });
      }
    });
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

  Widget _buildRecognitionUI() {
    return FutureBuilder(
      future: _initializeControllerFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        return Stack(
          children: [
            SizedBox.expand(child: CameraPreview(_controller)),

            // DYNAMIC GREEN FRAME
            if (_isFaceDetected && _faceCoords != null)
              Positioned(
                left: _faceCoords!['x'] * MediaQuery.of(context).size.width,
                top: _faceCoords!['y'] * MediaQuery.of(context).size.height,
                width: _faceCoords!['w'] * MediaQuery.of(context).size.width,
                height: _faceCoords!['h'] * MediaQuery.of(context).size.height,
                child: Container(
                  decoration: BoxDecoration(
                    border: Border.all(color: Colors.green, width: 3),
                    borderRadius: BorderRadius.circular(8),
                  ),
                ),
              ),

            Positioned(
              top: 40,
              right: 20,
              child: CircleAvatar(
                backgroundColor: _isConnected ? Colors.green : Colors.red,
                radius: 8,
              ),
            ),

            if (_isFaceRecognized)
              Center(
                child: Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 30, vertical: 20),
                  decoration: BoxDecoration(
                    color: Colors.green.withOpacity(0.9),
                    borderRadius: BorderRadius.circular(15),
                  ),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.check_circle,
                          color: Colors.white, size: 60),
                      const SizedBox(height: 10),
                      Text(
                        "Welcome, $_recognizedUserName",
                        style: const TextStyle(
                            color: Colors.white,
                            fontSize: 22,
                            fontWeight: FontWeight.bold),
                      ),
                    ],
                  ),
                ),
              ),

            Positioned(
              bottom: 60,
              left: 30,
              right: 30,
              child: Container(
                padding: const EdgeInsets.symmetric(vertical: 12),
                decoration: BoxDecoration(
                  color: Colors.black54,
                  borderRadius: BorderRadius.circular(25),
                ),
                child: Text(
                  _statusMessage,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.white, fontSize: 16),
                ),
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _buildTransitionUI() {
    return Container(
      key: const ValueKey("transition"),
      color: Colors.deepPurpleAccent,
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
      color: Colors.black,
      child: const Center(
        child: Text(
          "Liveness Detection Phase\n(Coming Soon)",
          textAlign: TextAlign.center,
          style: TextStyle(color: Colors.white, fontSize: 20),
        ),
      ),
    );
  }

  @override
  void dispose() {
    _streamTimer?.cancel();
    _controller.dispose();
    _channel?.sink.close();
    super.dispose();
  }
}
