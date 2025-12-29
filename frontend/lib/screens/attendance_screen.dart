// frontend/lib/screens/attendance_screen.dart
import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:ai_face_attendance_frontend/utils/image_converter.dart';

enum AttendancePhase {
  preparation,
  faceRecognition,
  livenessTransition,
  livenessDetection
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

  static const String _wsUrl = 'ws://localhost:8000/api/v1/ws/attendance';

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
    _controller = CameraController(
        widget.cameras
            .firstWhere((c) => c.lensDirection == CameraLensDirection.front),
        ResolutionPreset.medium,
        enableAudio: false);
    _initializeControllerFuture = _controller.initialize().then((_) {
      if (mounted) _startFrameStream();
    });
  }

  void _connectWebSocket() {
    try {
      _channel = WebSocketChannel.connect(Uri.parse(_wsUrl));
      setState(() => _isConnected = true);
      _channel!.stream.listen((data) {
        if (_currentPhase != AttendancePhase.faceRecognition ||
            _isFaceRecognized) return;
        final response = jsonDecode(data);
        setState(() {
          _statusMessage = response['message'] ?? "Processing...";
          _isFaceDetected = response['face_detected'] ?? false;
          if (response['status'] == 'success') {
            _isFaceRecognized = true;
            _recognizedUserName = response['user'];
            _handleFaceRecognized();
          }
        });
      },
          onDone: () => setState(() => _isConnected = false),
          onError: (_) => setState(() => _isConnected = false));
    } catch (e) {
      setState(() => _isConnected = false);
    }
  }

  void _handleFaceRecognized() {
    Timer(const Duration(milliseconds: 1000), () {
      if (mounted)
        setState(() => _currentPhase = AttendancePhase.livenessTransition);
    });
  }

  void _startFrameStream() {
    _controller.startImageStream((image) {
      if (_currentPhase != AttendancePhase.faceRecognition || _isFaceRecognized)
        return;
      if (_streamTimer == null || !_streamTimer!.isActive) {
        _streamTimer = Timer(const Duration(milliseconds: 500), () {
          final bytes = convertYUV420toImage(image);
          if (bytes != null && _isConnected) _channel?.sink.add(bytes);
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
          child: _buildCurrentUI()),
    );
  }

  Widget _buildCurrentUI() {
    if (_currentPhase == AttendancePhase.preparation) return _buildPrepUI();
    if (_currentPhase == AttendancePhase.livenessTransition)
      return _buildTransitionUI();
    return _buildRecognitionUI();
  }

  Widget _buildPrepUI() {
    return Container(
        color: Colors.blueAccent,
        child: const Center(
            child: Text("Step 1: Face Recognition",
                style: TextStyle(color: Colors.white, fontSize: 24))));
  }

  Widget _buildRecognitionUI() {
    return FutureBuilder(
      future: _initializeControllerFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done)
          return const Center(child: CircularProgressIndicator());
        return Stack(
          children: [
            SizedBox.expand(child: CameraPreview(_controller)),
            Positioned(
                top: 40,
                right: 20,
                child: CircleAvatar(
                    backgroundColor: _isConnected ? Colors.green : Colors.red,
                    radius: 8)),
            Center(
                child: Container(
                    width: 280,
                    height: 380,
                    decoration: BoxDecoration(
                        border: Border.all(
                            color: _isFaceRecognized
                                ? Colors.green
                                : (_isFaceDetected
                                    ? Colors.blue
                                    : Colors.white30),
                            width: 3),
                        borderRadius: BorderRadius.circular(20)))),
            if (_isFaceRecognized)
              Center(
                  child: Container(
                      padding: const EdgeInsets.all(20),
                      color: Colors.green.withOpacity(0.8),
                      child: Text("Welcome, $_recognizedUserName",
                          style: const TextStyle(
                              color: Colors.white, fontSize: 20)))),
            Positioned(
                bottom: 40,
                left: 20,
                right: 20,
                child: Text(_statusMessage,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                        color: Colors.white,
                        fontSize: 18,
                        backgroundColor: Colors.black54))),
          ],
        );
      },
    );
  }

  Widget _buildTransitionUI() {
    return Container(
        color: Colors.deepPurpleAccent,
        child: const Center(
            child: Text("Step 2: Liveness Check",
                style: TextStyle(color: Colors.white, fontSize: 24))));
  }

  @override
  void dispose() {
    _controller.dispose();
    _channel?.sink.close();
    super.dispose();
  }
}
