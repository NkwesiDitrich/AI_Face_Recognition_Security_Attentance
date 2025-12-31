// frontend/lib/screens/attendance_screen.dart

import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:google_mlkit_face_detection/google_mlkit_face_detection.dart';

enum AttendancePhase { phase0, phase1, success, fail, liveness }

class AttendanceScreen extends StatefulWidget {
  final List<CameraDescription> cameras;
  const AttendanceScreen({super.key, required this.cameras});
  @override
  State<AttendanceScreen> createState() => _AttendanceScreenState();
}

class _AttendanceScreenState extends State<AttendanceScreen> {
  CameraController? _controller;
  WebSocketChannel? _channel;
  String _statusMessage = "Initializing...";
  AttendancePhase _currentPhase = AttendancePhase.phase0;
  bool _isRecognized = false;
  bool _faceDetected = false;
  String? _recognizedUserName;

  final FaceDetector _faceDetector = FaceDetector(
    options: FaceDetectorOptions(
        enableLandmarks: true, performanceMode: FaceDetectorMode.fast),
  );

  DateTime? _faceFirstDetectedAt;
  bool _isSendingFrame = false;

  @override
  void initState() {
    super.initState();
    _startPhase0();
  }

  void _startPhase0() {
    setState(() {
      _currentPhase = AttendancePhase.phase0;
      _statusMessage = "Step 1 of 2 – Face Recognition";
    });
    Timer(const Duration(seconds: 2), () {
      if (mounted) _startPhase1();
    });
  }

  void _startPhase1() async {
    setState(() {
      _currentPhase = AttendancePhase.phase1;
      _statusMessage = "Place your face inside the frame";
    });
    await _initializeCamera();
    _connectWebSocket();
  }

  Future<void> _initializeCamera() async {
    final front = widget.cameras
        .firstWhere((c) => c.lensDirection == CameraLensDirection.front);
    _controller =
        CameraController(front, ResolutionPreset.medium, enableAudio: false);
    await _controller!.initialize();
    if (mounted) {
      setState(() {});
      _startDetectionLoop();
    }
  }

  void _connectWebSocket() {
    _channel = WebSocketChannel.connect(
        Uri.parse('ws://192.168.165.202:8000/api/v1/ws/attendance'));
    _channel!.stream
        .listen((data) => _processBackendResponse(jsonDecode(data)));
  }

  void _startDetectionLoop() {
    Timer.periodic(const Duration(milliseconds: 200), (timer) async {
      if (!mounted ||
          _currentPhase != AttendancePhase.phase1 ||
          _isSendingFrame) return;
      try {
        final XFile photo = await _controller!.takePicture();
        final List<Face> faces = await _faceDetector
            .processImage(InputImage.fromFilePath(photo.path));

        if (faces.isEmpty) {
          _resetDetection();
          await File(photo.path).delete();
          return;
        }

        final face = faces.first;
        final rect = face.boundingBox;

        // PHASE 1: Quality Gate (Size & Centering)
        if (rect.width < 120 || rect.height < 120) {
          setState(() {
            _faceDetected = true;
            _statusMessage = "Come closer to the camera";
          });
          await File(photo.path).delete();
          return;
        }

        // PHASE 1.5: Stability Check (300ms)
        if (_faceFirstDetectedAt == null) {
          _faceFirstDetectedAt = DateTime.now();
          setState(() {
            _faceDetected = true;
            _statusMessage = "Hold still...";
          });
        } else if (DateTime.now()
                .difference(_faceFirstDetectedAt!)
                .inMilliseconds >=
            300) {
          _sendFrameToBackend(photo); // PHASE 2
        }
      } catch (e) {
        debugPrint("Detection Error: $e");
      }
    });
  }

  void _resetDetection() {
    if (mounted)
      setState(() {
        _faceDetected = false;
        _faceFirstDetectedAt = null;
        _statusMessage = "Place face in frame";
      });
  }

  Future<void> _sendFrameToBackend(XFile photo) async {
    if (_isSendingFrame || _channel == null) return;
    setState(() {
      _isSendingFrame = true;
      _statusMessage = "Recognizing...";
    });
    final Uint8List bytes = await File(photo.path).readAsBytes();
    _channel!.sink.add(bytes);
    await File(photo.path).delete();
  }

  void _processBackendResponse(Map<String, dynamic> res) {
    if (!mounted) return;
    if (res['status'] == 'recognized') {
      setState(() {
        _currentPhase = AttendancePhase.success;
        _isRecognized = true;
        _recognizedUserName = res['user']['name'];
        _statusMessage = "✔ Face recognized";
      });
      Timer(const Duration(seconds: 1), () {
        if (mounted)
          setState(() {
            _currentPhase = AttendancePhase.liveness;
          });
      });
    } else {
      setState(() {
        _currentPhase = AttendancePhase.fail;
        _statusMessage = "Face not registered";
      });
      Timer(const Duration(seconds: 2), () {
        if (mounted) {
          setState(() {
            _currentPhase = AttendancePhase.phase1;
            _isSendingFrame = false;
            _faceFirstDetectedAt = null;
          });
        }
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
        body: AnimatedSwitcher(
            duration: const Duration(milliseconds: 500),
            child: _buildCurrentUI()));
  }

  Widget _buildCurrentUI() {
    if (_currentPhase == AttendancePhase.phase0) return _buildPhase0UI();
    if (_currentPhase == AttendancePhase.liveness) return _buildLivenessUI();
    return _buildRecognitionUI();
  }

  Widget _buildPhase0UI() => Container(
      color: Colors.blueAccent,
      child: Center(
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
        const Text("Step 1 of 2",
            style: TextStyle(color: Colors.white70, fontSize: 18)),
        const SizedBox(height: 10),
        Text(_statusMessage,
            style: const TextStyle(
                color: Colors.white, fontSize: 28, fontWeight: FontWeight.bold))
      ])));

  Widget _buildRecognitionUI() {
    if (_controller == null || !_controller!.value.isInitialized)
      return const Center(child: CircularProgressIndicator());
    Color frameColor = _currentPhase == AttendancePhase.success
        ? Colors.green
        : (_currentPhase == AttendancePhase.fail
            ? Colors.red
            : (_faceDetected ? Colors.orange : Colors.blue));
    return Container(
        color: Colors.black,
        child: Stack(children: [
          Center(child: CameraPreview(_controller!)),
          Center(
              child: Container(
                  width: 280,
                  height: 350,
                  decoration: BoxDecoration(
                      border: Border.all(color: frameColor, width: 4),
                      borderRadius: BorderRadius.circular(20)))),
          Positioned(
              bottom: 50,
              left: 0,
              right: 0,
              child: Center(
                  child: Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 24, vertical: 12),
                      decoration: BoxDecoration(
                          color: Colors.black54,
                          borderRadius: BorderRadius.circular(30)),
                      child: Text(_statusMessage,
                          style: TextStyle(
                              color: frameColor,
                              fontSize: 18,
                              fontWeight: FontWeight.bold))))),
          if (_isRecognized)
            Positioned(
                top: 100,
                left: 0,
                right: 0,
                child: Center(
                    child: Text("Welcome, $_recognizedUserName",
                        style: const TextStyle(
                            color: Colors.green,
                            fontSize: 24,
                            fontWeight: FontWeight.bold)))),
        ]));
  }

  Widget _buildLivenessUI() => Container(
      color: Colors.purple,
      child: const Center(
          child: Text("Liveness Detection Stage",
              style: TextStyle(
                  color: Colors.white,
                  fontSize: 24,
                  fontWeight: FontWeight.bold))));

  @override
  void dispose() {
    _faceDetector.close();
    _controller?.dispose();
    _channel?.sink.close();
    super.dispose();
  }
}
