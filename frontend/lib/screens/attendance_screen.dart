import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';
import 'package:google_mlkit_face_detection/google_mlkit_face_detection.dart';
import 'package:http/http.dart' as http;

enum AttendancePhase {
  phase0,
  phase1,
  success,
  transition,
  liveness,
  finalResult,
  fail
}

enum ChallengeType { smile, blink, mouthOpen, neutral }

class LivenessChallenge {
  final ChallengeType type;
  final String instruction;
  final String emoji;

  LivenessChallenge(
      {required this.type, required this.instruction, required this.emoji});
}

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

  // EXACT SAME FaceDetector as Step 1
  final FaceDetector _faceDetector = FaceDetector(
    options: FaceDetectorOptions(
      enableClassification: true,
      enableLandmarks: true,
      performanceMode: FaceDetectorMode.fast,
    ),
  );

  ResolutionPreset get _cameraResolution => ResolutionPreset.high;
  DateTime? _faceFirstDetectedAt;
  bool _isSendingFrame = false;
  bool _isProcessing = false; // ✅ NEW: Lock to prevent camera choking

  LivenessChallenge? _currentChallenge;
  int _attempts = 0;
  final int _maxAttempts = 2;
  Timer? _livenessTimer;
  int _livenessSecondsRemaining = 5;
  bool _livenessPassed = false;
  bool _livenessFaceDetected = false;

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
      _isRecognized = false;
      _isSendingFrame = false;
      _isProcessing = false;
      _faceFirstDetectedAt = null;
      _attempts = 0;
    });
    await _initializeCamera();
    _connectWebSocket();
  }

  Future<void> _initializeCamera() async {
    if (_controller != null && _controller!.value.isInitialized) return;
    final front = widget.cameras
        .firstWhere((c) => c.lensDirection == CameraLensDirection.front);
    _controller =
        CameraController(front, _cameraResolution, enableAudio: false);
    await _controller!.initialize();
    if (mounted) {
      setState(() {});
      _startDetectionLoop();
    }
  }

  void _connectWebSocket() {
    _channel = WebSocketChannel.connect(
        Uri.parse('ws://192.168.137.1:8000/api/v1/ws/attendance'));
    _channel!.stream
        .listen((data) => _processBackendResponse(jsonDecode(data)));
  }

  void _startDetectionLoop() {
    Timer.periodic(const Duration(milliseconds: 200), (timer) async {
      if (!mounted || _isSendingFrame || _isProcessing) return;

      if (_currentPhase == AttendancePhase.phase1) {
        await _handleRecognitionDetection();
      } else if (_currentPhase == AttendancePhase.liveness) {
        await _handleLivenessDetection();
      }
    });
  }

  // STEP 1 LOGIC (Untouched)
  Future<void> _handleRecognitionDetection() async {
    try {
      if (_controller == null || !_controller!.value.isInitialized) return;
      _isProcessing = true;
      final XFile photo = await _controller!.takePicture();
      final List<Face> faces =
          await _faceDetector.processImage(InputImage.fromFilePath(photo.path));

      if (faces.isEmpty) {
        _resetDetection();
        await File(photo.path).delete();
        _isProcessing = false;
        return;
      }

      final face = faces.first;
      final rect = face.boundingBox;

      if (rect.width < 120 || rect.height < 120) {
        setState(() {
          _faceDetected = true;
          _statusMessage = "Come closer";
        });
        await File(photo.path).delete();
        _isProcessing = false;
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
      _isProcessing = false;
    } catch (e) {
      debugPrint("Detection Error: $e");
      _isProcessing = false;
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
      Timer(const Duration(seconds: 1), () {
        if (mounted) _startTransitionPhase();
      });
    } else if (res['status'] == 'not_recognized') {
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

  void _startTransitionPhase() {
    setState(() {
      _currentPhase = AttendancePhase.transition;
      _statusMessage = "Step 2 of 2\nLiveness Detection";
    });
    Timer(const Duration(seconds: 1), () {
      if (mounted) _startLivenessPhase();
    });
  }

  void _startLivenessPhase() {
    if (_attempts >= _maxAttempts) {
      _showFinalFailure("Liveness check failed. Please try again.");
      return;
    }

    _attempts++;
    _livenessSecondsRemaining = 5;
    _livenessPassed = false;
    _livenessFaceDetected = false;

    final challenges = [
      LivenessChallenge(
          type: ChallengeType.smile,
          instruction: "Please Smile 😊",
          emoji: "😊"),
      LivenessChallenge(
          type: ChallengeType.blink,
          instruction: "Blink your eyes 😉",
          emoji: "😉"),
      LivenessChallenge(
          type: ChallengeType.mouthOpen,
          instruction: "Open your mouth 😮",
          emoji: "😮"),
      LivenessChallenge(
          type: ChallengeType.neutral,
          instruction: "Stay Neutral 😐",
          emoji: "😐"),
    ];
    _currentChallenge = challenges[Random().nextInt(challenges.length)];

    setState(() {
      _currentPhase = AttendancePhase.liveness;
      _statusMessage = _currentChallenge!.instruction;
    });

    _livenessTimer?.cancel();
    _livenessTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted) return;

      // ✅ Timer only counts down if a face is detected (Paused Timer)
      if (!_livenessFaceDetected) return;

      setState(() {
        if (_livenessSecondsRemaining > 0) {
          _livenessSecondsRemaining--;
        } else {
          _livenessTimer?.cancel();
          if (!_livenessPassed) _handleLivenessFailure();
        }
      });
    });
  }

  // ✅ CHEAT: Using the EXACT same detection logic as Step 1
  Future<void> _handleLivenessDetection() async {
    if (_livenessPassed || _isProcessing) return;

    try {
      if (_controller == null || !_controller!.value.isInitialized) return;
      _isProcessing = true; // Prevent overlapping calls
      final XFile photo = await _controller!.takePicture();
      final List<Face> faces =
          await _faceDetector.processImage(InputImage.fromFilePath(photo.path));

      // 1. Face Detection Foundation (Same as Step 1)
      if (faces.isEmpty) {
        if (mounted)
          setState(() {
            _livenessFaceDetected = false;
          });
        await File(photo.path).delete();
        _isProcessing = false;
        return;
      }

      final face = faces.first;
      final rect = face.boundingBox;

      // 2. Quality Gate (Same as Step 1)
      if (rect.width < 120 || rect.height < 120) {
        if (mounted)
          setState(() {
            _livenessFaceDetected = true;
            _statusMessage = "Come closer";
          });
        await File(photo.path).delete();
        _isProcessing = false;
        return;
      }

      // 3. Face is detected and quality is good
      if (mounted)
        setState(() {
          _livenessFaceDetected = true;
          _statusMessage = _currentChallenge!.instruction;
        });

      bool success = false;

      // 4. Liveness Logic
      switch (_currentChallenge!.type) {
        case ChallengeType.smile:
          if ((face.smilingProbability ?? 0) > 0.6) success = true;
          break;
        case ChallengeType.blink:
          if ((face.leftEyeOpenProbability ?? 1.0) < 0.25 &&
              (face.rightEyeOpenProbability ?? 1.0) < 0.25) success = true;
          break;
        case ChallengeType.neutral:
          if ((face.smilingProbability ?? 1.0) < 0.2 &&
              (face.leftEyeOpenProbability ?? 0) > 0.7) success = true;
          break;
        case ChallengeType.mouthOpen:
          final nose = face.landmarks[FaceLandmarkType.noseBase];
          final mouth = face.landmarks[FaceLandmarkType.bottomMouth];
          if (nose != null && mouth != null) {
            double diff =
                (mouth.position.y.toDouble() - nose.position.y.toDouble())
                    .abs();
            double faceHeight = face.boundingBox.height.toDouble();
            if ((diff / faceHeight) > 0.25) success = true;
          }
          break;
      }

      await File(photo.path).delete();
      _isProcessing = false;

      if (success) {
        _livenessPassed = true;
        _livenessTimer?.cancel();
        _handleLivenessSuccess();
      }
    } catch (e) {
      debugPrint("Liveness Error: $e");
      _isProcessing = false;
    }
  }

  void _handleLivenessSuccess() {
    setState(() {
      _statusMessage = "✔ Step 2 completed\n✔ Liveness detection completed";
    });
    Timer(const Duration(seconds: 1), () {
      _recordAttendance();
    });
  }

  void _handleLivenessFailure() {
    if (_attempts < _maxAttempts) {
      setState(() {
        _statusMessage = "Liveness failed. Try again.";
      });
      Timer(const Duration(seconds: 2), () {
        if (mounted) _startLivenessPhase();
      });
    } else {
      _showFinalFailure("Liveness check failed. Please try again.");
    }
  }

  Future<void> _recordAttendance() async {
    setState(() {
      _statusMessage = "Recording attendance...";
    });

    try {
      final response = await http.post(
        Uri.parse('http://192.168.11.202:8000/api/v1/record'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'user_id': _recognizedUserId,
          'liveness': 'passed',
          'event_type': 'check_in',
          'session_id': DateTime.now().millisecondsSinceEpoch.toString(),
        }),
      );

      if (response.statusCode == 200) {
        setState(() {
          _currentPhase = AttendancePhase.finalResult;
          _statusMessage = "Access Granted";
        });
      } else {
        _showFinalFailure("Failed to record attendance");
      }
    } catch (e) {
      _showFinalFailure("Network Error: $e");
    }
  }

  void _showFinalFailure(String msg) {
    setState(() {
      _currentPhase = AttendancePhase.fail;
      _statusMessage = msg;
    });
    Timer(const Duration(seconds: 2), () {
      if (mounted) _startPhase1();
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
      case AttendancePhase.transition:
        return _buildTransitionUI();
      case AttendancePhase.liveness:
        return _buildLivenessUI();
      case AttendancePhase.finalResult:
        return _buildFinalResultUI();
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
            textAlign: TextAlign.center,
            style: const TextStyle(
                color: Colors.white, fontSize: 28, fontWeight: FontWeight.bold))
      ])));

  Widget _buildTransitionUI() => Container(
      color: Colors.deepPurple,
      child: Center(
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
        const Text("Step 2 of 2",
            style: TextStyle(color: Colors.white70, fontSize: 18)),
        const SizedBox(height: 10),
        Text(_statusMessage,
            textAlign: TextAlign.center,
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
                          textAlign: TextAlign.center,
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
    Color frameColor = _livenessFaceDetected ? Colors.orange : Colors.purple;
    return Container(
        color: Colors.black,
        child: Stack(children: [
          Center(child: CameraPreview(_controller!)),
          Container(color: Colors.black.withOpacity(0.3)),
          Center(
              child: Container(
                  width: 280,
                  height: 350,
                  decoration: BoxDecoration(
                      border: Border.all(color: frameColor, width: 4),
                      borderRadius: BorderRadius.circular(20)))),
          Positioned(
              top: 60,
              right: 20,
              child: Container(
                  padding: const EdgeInsets.all(16),
                  decoration: const BoxDecoration(
                      color: Colors.white, shape: BoxShape.circle),
                  child: Text(_currentChallenge?.emoji ?? "",
                      style: const TextStyle(fontSize: 40)))),
          Positioned(
              bottom: 100,
              left: 0,
              right: 0,
              child: Center(
                  child: Text("Time remaining: $_livenessSecondsRemaining s",
                      style:
                          const TextStyle(color: Colors.white, fontSize: 20)))),
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
                      child: Text(
                          _livenessFaceDetected
                              ? _statusMessage
                              : "Face not detected",
                          textAlign: TextAlign.center,
                          style: TextStyle(
                              color: frameColor,
                              fontSize: 18,
                              fontWeight: FontWeight.bold))))),
        ]));
  }

  Widget _buildFinalResultUI() => Container(
      color: Colors.green,
      child: Center(
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
        const Icon(Icons.check_circle, color: Colors.white, size: 100),
        const SizedBox(height: 20),
        const Text("Access Granted",
            style: TextStyle(
                color: Colors.white,
                fontSize: 32,
                fontWeight: FontWeight.bold)),
        const SizedBox(height: 10),
        Text("Welcome, $_recognizedUserName",
            style: const TextStyle(color: Colors.white70, fontSize: 20)),
      ])));

  @override
  void dispose() {
    _livenessTimer?.cancel();
    _faceDetector.close();
    _controller?.dispose();
    _channel?.sink.close();
    super.dispose();
  }
}
