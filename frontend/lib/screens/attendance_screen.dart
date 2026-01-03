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
import 'package:flutter/foundation.dart';

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
  String? _livenessSessionId;

  bool _isImageStreamRunning = false;

  final FaceDetector _faceDetector = FaceDetector(
    options: FaceDetectorOptions(
        enableLandmarks: true,
        enableClassification: true,
        enableContours: true, // CRITICAL for mouth open detection
        performanceMode: FaceDetectorMode.fast),
  );

  DateTime? _faceFirstDetectedAt;
  bool _isSendingFrame = false;
  bool _isProcessingStream = false;
  Timer? _detectionTimer;

  // FIX: Frame throttling variable
  DateTime _lastLivenessProcess = DateTime.now();

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
  static const String _serverIp = '192.168.74.202';
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
      _livenessSessionId = DateTime.now().millisecondsSinceEpoch.toString();
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
    _controller = CameraController(front, ResolutionPreset.high,
        enableAudio: false, imageFormatGroup: ImageFormatGroup.yuv420);
    await _controller!.initialize();
    if (mounted) {
      setState(() {});
      _startRecognitionLoop();
    }
  }

  void _connectWebSocket() {
    _channel = WebSocketChannel.connect(Uri.parse(_wsUrl));
    _channel!.stream
        .listen((data) => _processBackendResponse(jsonDecode(data)));
  }

  void _startRecognitionLoop() {
    _detectionTimer?.cancel();
    _detectionTimer =
        Timer.periodic(const Duration(milliseconds: 500), (timer) async {
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
        debugPrint("Recognition Error: $e");
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
    _isSendingFrame = false;
    if (res['status'] == 'recognized') {
      _detectionTimer?.cancel();
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
        _faceFirstDetectedAt = null;
      });
      Timer(const Duration(seconds: 2), () {
        if (mounted)
          setState(() {
            _currentPhase = AttendancePhase.phase1;
          });
      });
    }
  }

  void _startLivenessPhase() async {
    // FIX: Reset camera pipeline to fix takePicture conflict
    await _controller?.pausePreview();
    await Future.delayed(const Duration(milliseconds: 200));
    await _controller?.resumePreview();

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

    if (!_isImageStreamRunning) {
      _controller!.startImageStream(_processLivenessFrame);
      _isImageStreamRunning = true;
    }
  }

  void _processLivenessFrame(CameraImage image) async {
    if (_livenessPassed ||
        _isProcessingStream ||
        _currentPhase != AttendancePhase.liveness) return;

    // ✅ FRAME THROTTLING (CRITICAL)
    if (DateTime.now().difference(_lastLivenessProcess).inMilliseconds < 180)
      return;
    _lastLivenessProcess = DateTime.now();

    _isProcessingStream = true;
    try {
      final inputImage = _convertCameraImage(image);
      if (inputImage != null) {
        final List<Face> faces = await _faceDetector.processImage(inputImage);

        // ✅ SINGLE FACE ENFORCEMENT
        if (faces.length != 1) {
          setState(() {
            _statusMessage = faces.isEmpty
                ? "Face lost, return to frame"
                : "Multiple faces detected";
            _expressionStartTime = null;
          });
          _isProcessingStream = false;
          return;
        }

        _evaluateExpression(faces.first);
      }
    } catch (e) {
      debugPrint("Liveness Frame Error: $e");
    }
    _isProcessingStream = false;
  }

  void _evaluateExpression(Face face) {
    bool matched = false;
    debugPrint(
        "Smile: ${face.smilingProbability}, LeftEye: ${face.leftEyeOpenProbability}, RightEye: ${face.rightEyeOpenProbability}");

    switch (_currentEmoji) {
      case "😊":
        // FIX: Relaxed smile threshold for live video
        matched = (face.smilingProbability ?? 0) > 0.35;
        break;
      case "😐":
        matched = (face.smilingProbability ?? 0) < 0.30;
        break;
      case "😠":
        matched = (face.smilingProbability ?? 0) < 0.25;
        break;
      case "😮":
        final upperLip = face.contours[FaceContourType.upperLipBottom]?.points;
        final lowerLip = face.contours[FaceContourType.lowerLipTop]?.points;
        if (upperLip != null &&
            lowerLip != null &&
            upperLip.isNotEmpty &&
            lowerLip.isNotEmpty) {
          final upY = upperLip[upperLip.length ~/ 2].y;
          final lowY = lowerLip[lowerLip.length ~/ 2].y;
          // FIX: Scale-aware threshold
          final faceHeight = face.boundingBox.height;
          matched = ((lowY - upY).abs() / faceHeight) > 0.08;
        }
        break;
    }
    if (matched) {
      _expressionStartTime ??= DateTime.now();
      if (DateTime.now().difference(_expressionStartTime!).inMilliseconds >=
          650) {
        _onStepSuccess();
      }
    } else {
      _expressionStartTime = null;
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

    if (_isImageStreamRunning) {
      _controller?.stopImageStream();
      _isImageStreamRunning = false;
    }

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
          "event_type": "check_in",
          "session_id": _livenessSessionId
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

  void _onLivenessFailed() {
    if (_isImageStreamRunning) {
      _controller?.stopImageStream();
      _isImageStreamRunning = false;
    }
    setState(() {
      _currentPhase = AttendancePhase.fail;
      _statusMessage = "Liveness check failed. Retrying...";
      _isRecognized = false;
    });

    Timer(const Duration(seconds: 2), () {
      if (mounted) _startPhase1();
    });
  }

  InputImage? _convertCameraImage(CameraImage image) {
    final WriteBuffer allBytes = WriteBuffer();
    for (final Plane plane in image.planes) {
      allBytes.putUint8List(plane.bytes);
    }
    final bytes = allBytes.done().buffer.asUint8List();

    // ✅ CORRECT rotation handling
    final camera = _controller!.description;
    final rotation = camera.sensorOrientation;
    InputImageRotation imageRotation;
    switch (rotation) {
      case 0:
        imageRotation = InputImageRotation.rotation0deg;
        break;
      case 90:
        imageRotation = InputImageRotation.rotation90deg;
        break;
      case 180:
        imageRotation = InputImageRotation.rotation180deg;
        break;
      case 270:
        imageRotation = InputImageRotation.rotation270deg;
        break;
      default:
        imageRotation = InputImageRotation.rotation90deg;
    }

    final inputImageFormat =
        InputImageFormatValue.fromRawValue(image.format.raw) ??
            InputImageFormat.yuv420;
    final metadata = InputImageMetadata(
        size: Size(image.width.toDouble(), image.height.toDouble()),
        rotation: imageRotation,
        format: inputImageFormat,
        bytesPerRow: image.planes[0].bytesPerRow);
    return InputImage.fromBytes(bytes: bytes, metadata: metadata);
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
    if (_currentPhase == AttendancePhase.finalSuccess)
      return _buildFinalSuccessUI();
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
    _detectionTimer?.cancel();
    _faceDetector.close();
    _controller?.dispose();
    _channel?.sink.close();
    _livenessCountdownTimer?.cancel();
    super.dispose();
  }
}
