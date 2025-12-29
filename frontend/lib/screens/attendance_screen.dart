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

  bool _isFaceRecognized = false;
  String? _recognizedUserName;
  String? _recognizedUserId;

  static const String _wsUrl = 'ws://10.0.2.2:8000/api/v1/ws/attendance';

  @override
  void initState() {
    super.initState();
    _startPreparationPhase();
  }

  // PHASE 0: PREPARATION (1-2 seconds)
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
    _controller = CameraController(
      widget.cameras
          .firstWhere((c) => c.lensDirection == CameraLensDirection.front),
      ResolutionPreset.medium,
      enableAudio: false,
    );
    _initializeControllerFuture = _controller.initialize().then((_) {
      if (mounted) _startFrameStream();
    });
  }

  void _connectWebSocket() {
    _channel = WebSocketChannel.connect(Uri.parse(_wsUrl));
    _channel!.stream.listen((data) {
      if (_currentPhase != AttendancePhase.faceRecognition || _isFaceRecognized)
        return;
      final response = jsonDecode(data);
      setState(() {
        _statusMessage = response['message'] ?? "Processing...";
        if (response['status'] == 'success') {
          _isFaceRecognized = true;
          _recognizedUserName = response['user'];
          _recognizedUserId = response['user_id'];
          _handleFaceRecognized();
        }
      });
    });
  }

  void _handleFaceRecognized() {
    // Show success overlay for 1 second then transition to Phase 2
    Timer(const Duration(milliseconds: 1000), () {
      if (mounted) {
        setState(() => _currentPhase = AttendancePhase.livenessTransition);
        _startLivenessTransition();
      }
    });
  }

  // PHASE 2: LIVENESS TRANSITION (1 second)
  void _startLivenessTransition() {
    Timer(const Duration(seconds: 1), () {
      if (mounted) {
        setState(() => _currentPhase = AttendancePhase.livenessDetection);
        // Next: Implement Emoji Challenge logic here
      }
    });
  }

  void _startFrameStream() {
    _controller.startImageStream((image) {
      if (_currentPhase != AttendancePhase.faceRecognition || _isFaceRecognized)
        return;
      if (_streamTimer == null || !_streamTimer!.isActive) {
        _streamTimer = Timer(const Duration(milliseconds: 500), () {
          final bytes = convertYUV420toImage(image);
          if (bytes != null) _channel?.sink.add(bytes);
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
        return const Center(child: Text("Liveness Detection Coming Soon"));
    }
  }

  Widget _buildPreparationUI() {
    return Container(
      key: const ValueKey("prep"),
      color: Colors.blueAccent,
      width: double.infinity,
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
              valueColor: AlwaysStoppedAnimation(Colors.white)),
        ],
      ),
    );
  }

  Widget _buildFaceRecognitionUI() {
    return FutureBuilder(
      future: _initializeControllerFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done)
          return const Center(child: CircularProgressIndicator());
        return Stack(
          children: [
            SizedBox.expand(child: CameraPreview(_controller)),
            // Face Frame
            Center(
              child: Container(
                width: 280,
                height: 380,
                decoration: BoxDecoration(
                  border: Border.all(
                      color: _isFaceRecognized ? Colors.green : Colors.blue,
                      width: 3),
                  borderRadius: BorderRadius.circular(20),
                ),
              ),
            ),
            // Success Overlay
            if (_isFaceRecognized)
              Center(
                child: Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                  decoration: BoxDecoration(
                      color: Colors.green.withOpacity(0.8),
                      borderRadius: BorderRadius.circular(30)),
                  child: const Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.check_circle, color: Colors.white, size: 28),
                      SizedBox(width: 10),
                      Text("Face recognized",
                          style: TextStyle(
                              color: Colors.white,
                              fontSize: 20,
                              fontWeight: FontWeight.bold)),
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
                    borderRadius: BorderRadius.circular(12)),
                child: Text(_statusMessage,
                    style: const TextStyle(color: Colors.white, fontSize: 18),
                    textAlign: TextAlign.center),
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _buildLivenessTransitionUI() {
    return Container(
      key: const ValueKey("liveness_trans"),
      color: Colors.deepPurpleAccent,
      width: double.infinity,
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
        ],
      ),
    );
  }
}
