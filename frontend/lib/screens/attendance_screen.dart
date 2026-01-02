// frontend/lib/screens/attendance_screen.dart

import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'dart:math';
import 'package:google_mlkit_face_detection/google_mlkit_face_detection.dart';
import 'package:http/http.dart' as http;

enum AttendancePhase { phase0, phase1, success, fail, liveness, finalSuccess }

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
  String? _recognizedUserId;

  final FaceDetector _faceDetector = FaceDetector(
    options: FaceDetectorOptions(
        enableLandmarks: true,
        enableClassification: true,
        performanceMode: FaceDetectorMode.fast),
  );

  DateTime? _faceFirstDetectedAt;
  bool _isSendingFrame = false;

  // Liveness State
  List<Map<String, String>> _livenessSequence = [];
  int _currentLivenessStep = 0;
  String _currentEmoji = "😊";
  String _livenessInstruction = "Please smile";
  int _livenessTimer = 5;
  Timer? _livenessCountdownTimer;
  bool _livenessPassed = false;
  DateTime? _expressionStartTime;

  // UPDATE THIS to your computer's IP address
  static const String _serverIp = '192.168.165.202';
  static const String _wsUrl = 'ws://$_serverIp:8000/api/v1/ws/attendance';
  static const String _recordUrl = 'http://$_serverIp:8000/api/v1/record';

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
        CameraController(front, ResolutionPreset.high, enableAudio: false);
    await _controller!.initialize();
    if (mounted) {
      setState(() {});
      _startDetectionLoop();
    }
  }

  void _connectWebSocket() {
    _channel = WebSocketChannel.connect(Uri.parse(_wsUrl));
    _channel!.stream
        .listen((data) => _processBackendResponse(jsonDecode(data)));
  }

  void _startDetectionLoop() {
    Timer.periodic(const Duration(milliseconds: 200), (timer) async {
      if (!mounted || _isSendingFrame) return;
      if (_currentPhase == AttendancePhase.phase1) {
        await _handleRecognitionDetection();
      } else if (_currentPhase == AttendancePhase.liveness) {
        await _handleLivenessDetection();
      }
    });
  }

  Future<void> _handleRecognitionDetection() async {
    try {
      final XFile photo = await _controller!.takePicture();
      final List<Face> faces =
          await _faceDetector.processImage(InputImage.fromFilePath(photo.path));
      if (faces.isEmpty) {
        _resetDetection();
        await File(photo.path).delete();
        return;
      }
      final face = faces.first;
      if (face.boundingBox.width < 120) {
        setState(() {
          _faceDetected = true;
          _statusMessage = "Come closer to the camera";
        });
        await File(photo.path).delete();
        return;
      }
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
        _sendFrameToBackend(photo);
      }
    } catch (e) {
      debugPrint("Detection Error: $e");
    }
  }

  Future<void> _handleLivenessDetection() async {
    if (_livenessPassed) return;
    try {
      final XFile photo = await _controller!.takePicture();
      final List<Face> faces =
          await _faceDetector.processImage(InputImage.fromFilePath(photo.path));
      await File(photo.path).delete();
      if (faces.isEmpty) {
        setState(() {
          _statusMessage = "Face lost, return to frame";
          _expressionStartTime = null;
        });
        return;
      }

      final face = faces.first;
      bool matched = false;

      switch (_currentEmoji) {
        case "😊": // Smile
          if ((face.smilingProbability ?? 0) > 0.60) matched = true;
          break;
        case "😐": // Neutral
          if ((face.smilingProbability ?? 0) < 0.2) matched = true;
          break;
        case "😠": // Angry
          if ((face.smilingProbability ?? 0) < 0.1) matched = true;
          break;
        case "😮": // Surprise (Mouth Open)
          final bottomMouth =
              face.landmarks[FaceLandmarkType.bottomMouth]?.position;
          final noseBase = face.landmarks[FaceLandmarkType.noseBase]?.position;
          if (bottomMouth != null && noseBase != null) {
            final mouthHeight = (bottomMouth.y - noseBase.y).abs();
            if (mouthHeight > 15) matched = true; // Threshold for open mouth
          }
          break;
      }

      if (matched) {
        if (_expressionStartTime == null) {
          _expressionStartTime = DateTime.now();
        } else if (DateTime.now()
                .difference(_expressionStartTime!)
                .inMilliseconds >=
            500) {
          _onStepSuccess();
        }
      } else {
        _expressionStartTime = null;
      }
    } catch (e) {
      debugPrint("Liveness Error: $e");
    }
  }

  void _onStepSuccess() {
    _expressionStartTime = null;
    if (_currentLivenessStep < _livenessSequence.length - 1) {
      setState(() {
        _currentLivenessStep++;
        _currentEmoji = _livenessSequence[_currentLivenessStep]["emoji"]!;
        _livenessInstruction =
            _livenessSequence[_currentLivenessStep]["instruction"]!;
        _livenessTimer = 5;
      });
    } else {
      _onLivenessSuccess();
    }
  }

  void _onLivenessSuccess() {
    _livenessPassed = true;
    _livenessCountdownTimer?.cancel();
    setState(() {
      _statusMessage = "✔ Liveness detection completed";
    });
    _recordAttendance();
  }

  Future<void> _recordAttendance() async {
    try {
      final response = await http.post(
        Uri.parse(_recordUrl),
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({
          "user_id": _recognizedUserId,
          "liveness": "passed",
          "event_type": "check_in"
        }),
      );
      if (response.statusCode == 200) {
        setState(() {
          _currentPhase = AttendancePhase.finalSuccess;
          _statusMessage = "Access Granted";
        });
      }
    } catch (e) {
      debugPrint("Record Error: $e");
    }
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
        _recognizedUserId = res['user']['id'];
        _statusMessage = "✔ Face recognized";
      });
      Timer(const Duration(milliseconds: 1000), () {
        if (mounted) _startLivenessPhase();
      });
    } else {
      setState(() {
        _currentPhase = AttendancePhase.fail;
        _statusMessage = "Face not registered";
      });
      Timer(const Duration(seconds: 2), () {
        if (mounted)
          setState(() {
            _currentPhase = AttendancePhase.phase1;
            _isSendingFrame = false;
            _faceFirstDetectedAt = null;
          });
      });
    }
  }

  void _startLivenessPhase() {
    final allOptions = [
      {"emoji": "😊", "instruction": "Please smile"},
      {"emoji": "😐", "instruction": "Keep a neutral expression"},
      {"emoji": "😠", "instruction": "Please look angry"},
      {"emoji": "😮", "instruction": "Open your mouth (Surprise)"},
    ];
    allOptions.shuffle();
    _livenessSequence = allOptions.take(2).toList();

    setState(() {
      _currentPhase = AttendancePhase.liveness;
      _currentLivenessStep = 0;
      _currentEmoji = _livenessSequence[0]["emoji"]!;
      _livenessInstruction = _livenessSequence[0]["instruction"]!;
      _livenessTimer = 5;
      _livenessPassed = false;
      _expressionStartTime = null;
    });

    _livenessCountdownTimer?.cancel();
    _livenessCountdownTimer =
        Timer.periodic(const Duration(seconds: 1), (timer) {
      if (_livenessTimer > 0) {
        setState(() {
          _livenessTimer--;
        });
      } else {
        timer.cancel();
        if (!_livenessPassed) _onLivenessFailed();
      }
    });
  }

  void _onLivenessFailed() {
    setState(() {
      _currentPhase = AttendancePhase.fail;
      _statusMessage = "Liveness check failed. Retrying...";
    });

    // FIXED: Instead of resetting to Phase 1, restart liveness if user is still there
    Timer(const Duration(seconds: 2), () {
      if (mounted) {
        if (_isRecognized) {
          _startLivenessPhase(); // Restart liveness challenge
        } else {
          _startPhase1(); // Go back to recognition if user left
        }
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
        body: AnimatedSwitcher(
            duration: const Duration(milliseconds: 500),
            child: _buildCurrentUI()));
  }

  Widget _buildCurrentUI() {
    switch (_currentPhase) {
      case AttendancePhase.phase0:
        return _buildPhase0UI();
      case AttendancePhase.liveness:
        return _buildLivenessUI();
      case AttendancePhase.finalSuccess:
        return _buildFinalSuccessUI();
      default:
        return _buildRecognitionUI();
    }
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

  Widget _buildLivenessUI() {
    return Container(
        color: Colors.black,
        child: Stack(children: [
          Center(child: CameraPreview(_controller!)),
          Center(
              child: Container(
                  width: 280,
                  height: 350,
                  decoration: BoxDecoration(
                      border: Border.all(color: Colors.green, width: 4),
                      borderRadius: BorderRadius.circular(20)))),
          Positioned(
              top: 60,
              right: 20,
              child: Text(_currentEmoji, style: const TextStyle(fontSize: 60))),
          Positioned(
              top: 60,
              left: 20,
              child: Text("Step ${_currentLivenessStep + 1} of 2",
                  style: const TextStyle(color: Colors.white, fontSize: 18))),
          Positioned(
              bottom: 100,
              left: 0,
              right: 0,
              child: Center(
                  child: Text(_livenessInstruction,
                      style: const TextStyle(
                          color: Colors.white,
                          fontSize: 24,
                          fontWeight: FontWeight.bold)))),
          Positioned(
              bottom: 50,
              left: 0,
              right: 0,
              child: Center(
                  child: Text("⏱ $_livenessTimer...",
                      style: const TextStyle(
                          color: Colors.orange,
                          fontSize: 30,
                          fontWeight: FontWeight.bold)))),
        ]));
  }

  Widget _buildFinalSuccessUI() {
    return Container(
        color: Colors.green,
        child: Center(
            child:
                Column(mainAxisAlignment: MainAxisAlignment.center, children: [
          const Icon(Icons.check_circle, color: Colors.white, size: 100),
          const SizedBox(height: 20),
          const Text("Access Granted",
              style: TextStyle(
                  color: Colors.white,
                  fontSize: 32,
                  fontWeight: FontWeight.bold)),
          const SizedBox(height: 10),
          Text("Welcome, $_recognizedUserName",
              style: const TextStyle(color: Colors.white70, fontSize: 24)),
          const SizedBox(height: 20),
          const Text("Attendance Recorded",
              style: TextStyle(color: Colors.white, fontSize: 18))
        ])));
  }

  @override
  void dispose() {
    _faceDetector.close();
    _controller?.dispose();
    _channel?.sink.close();
    _livenessCountdownTimer?.cancel();
    super.dispose();
  }
}
