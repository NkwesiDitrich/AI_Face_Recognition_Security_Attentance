import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:ai_face_attendance_frontend/config/api_config.dart';
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
  recording, // Waiting for backend to confirm before Access Granted
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
  static const int _livenessDurationSeconds = 10;
  Timer? _livenessTimer;
  int _livenessSecondsRemaining = _livenessDurationSeconds;
  bool _livenessPassed = false;
  bool _livenessFaceDetected = false;
  int _livenessSuccessStreak =
      0; // Track consecutive frames with correct expression
  bool _isWaitingForBackend =
      false; // Only show Access Granted after backend confirms
  String? _currentSessionId; // Track session ID from recognition
  DateTime? _livenessStartTime; // Track when liveness started
  String? _currentChallengeAction; // Track current challenge action type

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
    // CRITICAL: Reset ALL state for complete restart from recognition phase
    setState(() {
      _currentPhase = AttendancePhase.phase1;
      _statusMessage = "Place your face inside the frame";
      _isRecognized = false;
      _isSendingFrame = false;
      _isProcessing = false;
      _faceDetected = false;
      _faceFirstDetectedAt = null;
      _attempts = 0;
      _livenessPassed = false;
      _livenessFaceDetected = false;
      _livenessSuccessStreak = 0;
      _recognizedUserId = null;
      _recognizedUserName = null;
      _currentSessionId = null;
      _currentChallenge = null;
      _currentChallengeAction = null;
      _livenessStartTime = null;
      _isWaitingForBackend = false;
    });
    _livenessTimer?.cancel();
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
        Uri.parse('$wsBaseUrl/api/v1/ws/attendance'));
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
      // ✅ Store session_id from backend response
      _currentSessionId = res['session_id'] as String?;
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
      // Session ID might still be in response even on failure
      _currentSessionId = res['session_id'] as String?;
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
            _currentSessionId = null; // Reset session on retry
          });
      });
    }
  }

  void _startTransitionPhase() {
    setState(() {
      _currentPhase = AttendancePhase.transition;
      _statusMessage = "Step 2 of 2\nLiveness Detection";
      // ✅ Reset processing flags so liveness detection loop can run
      _isSendingFrame = false;
      _isProcessing = false;
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
    _livenessSecondsRemaining = _livenessDurationSeconds;
    _livenessPassed = false;
    _livenessFaceDetected = false;
    _livenessSuccessStreak = 0;
    _livenessStartTime = DateTime.now(); // ✅ Track liveness start time
    // Reset processing flags just like in step 1 so detection can run
    _isProcessing = false;
    _isSendingFrame = false;

    // ✅ FIX 1: Randomly select challenge BEFORE setting state to ensure emoji is random
    final challenges = [
      LivenessChallenge(
          type: ChallengeType.smile,
          instruction: "Smile naturally 😊",
          emoji: "😊"),
      LivenessChallenge(
          type: ChallengeType.blink,
          instruction: "Close both eyes, then open",
          emoji: "😑"),
      LivenessChallenge(
          type: ChallengeType.mouthOpen,
          instruction: 'Open mouth like "oh" 😮',
          emoji: "😮"),
      LivenessChallenge(
          type: ChallengeType.neutral,
          instruction: "Relaxed face, lips closed 😐",
          emoji: "😐"),
    ];
    _currentChallenge = challenges[Random().nextInt(challenges.length)];
    // ✅ Store challenge action name for logging
    _currentChallengeAction = _getChallengeActionName(_currentChallenge!.type);

    setState(() {
      _currentPhase = AttendancePhase.liveness;
      _statusMessage = _currentChallenge!.instruction;
    });

    // ✅ Log liveness started (async, don't wait)
    _logLivenessStarted();

    _livenessTimer?.cancel();
    _livenessTimer = Timer.periodic(const Duration(seconds: 1), (timer) {
      if (!mounted) {
        timer.cancel();
        return;
      }

      // ✅ FIX 2: Timer only counts down if face is CONTINUOUSLY detected
      // If face is lost, timer pauses and counter doesn't move
      if (!_livenessFaceDetected) {
        // Face not detected - timer pauses, don't count down
        return;
      }

      setState(() {
        if (_livenessSecondsRemaining > 0) {
          _livenessSecondsRemaining--;
        } else {
          _livenessTimer?.cancel();
          // Time ran out without completing expression - fail
          if (!_livenessPassed) {
            _handleLivenessFailure();
          }
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
        // ✅ FIX 2 & 3: Face lost - reset everything, timer will pause
        if (mounted) {
          setState(() {
            _livenessFaceDetected = false;
            _livenessSuccessStreak = 0; // Reset streak when face is lost
            _statusMessage = "Place face in frame";
          });
        }
        await File(photo.path).delete();
        _isProcessing = false;
        return;
      }

      final face = faces.first;
      final rect = face.boundingBox;

      // 2. Quality Gate (Same as Step 1)
      if (rect.width < 120 || rect.height < 120) {
        // Face too small - don't reset detection, but don't check expression either
        if (mounted)
          setState(() {
            _livenessFaceDetected = true; // Keep as detected so timer can run
            _statusMessage = "Come closer";
          });
        await File(photo.path).delete();
        _isProcessing = false;
        return;
      }

      // 3. Face is detected and quality is good - timer can count down
      if (mounted) {
        setState(() {
          _livenessFaceDetected = true;
          _statusMessage = _currentChallenge!.instruction;
        });
      }

      // Extract face metrics once for all expressions
      final smileProb = face.smilingProbability ?? 0.0;
      final leftEye = face.leftEyeOpenProbability ?? 1.0;
      final rightEye = face.rightEyeOpenProbability ?? 1.0;
      double mouthRatio = 0.0;
      double mouthWidthRatio = 0.0;
      final nose = face.landmarks[FaceLandmarkType.noseBase];
      final bottomMouth = face.landmarks[FaceLandmarkType.bottomMouth];
      final leftMouth = face.landmarks[FaceLandmarkType.leftMouth];
      final rightMouth = face.landmarks[FaceLandmarkType.rightMouth];
      if (nose != null && bottomMouth != null) {
        final mouthY = bottomMouth.position.y.toDouble();
        final noseY = nose.position.y.toDouble();
        final faceHeight = face.boundingBox.height.toDouble();
        if (faceHeight > 0) mouthRatio = (mouthY - noseY).abs() / faceHeight;
      }
      if (leftMouth != null && rightMouth != null) {
        final faceW = face.boundingBox.width.toDouble();
        if (faceW > 0)
          mouthWidthRatio =
              (rightMouth.position.x - leftMouth.position.x).abs() / faceW;
      }

      bool expressionMatched = false;
      String debugInfo = "";

      // Shared thresholds
      const double eyeClosed = 0.38;
      const double eyeOpen = 0.58;
      final bothEyesClosed = leftEye < eyeClosed && rightEye < eyeClosed;
      final bothEyesOpen = leftEye > eyeOpen && rightEye > eyeOpen;
      final isWinking = (leftEye < eyeClosed && rightEye > eyeOpen) ||
          (rightEye < eyeClosed && leftEye > eyeOpen);
      final lipsClosed = mouthRatio < 0.22;
      final mouthOpenOh = mouthRatio > 0.23;

      // 4. Liveness Logic per user specs
      switch (_currentChallenge!.type) {
        case ChallengeType.smile:
          // Natural smile: mouth curved up, eyes relaxed/open. Not exaggerated.
          final naturalSmile = smileProb > 0.18;
          final mouthCurved = mouthWidthRatio > 0.24;
          final eyesRelaxed = bothEyesOpen;
          expressionMatched =
              (naturalSmile || mouthCurved) && eyesRelaxed && !mouthOpenOh;
          debugInfo =
              "Smile: prob=$smileProb, mouthW=$mouthWidthRatio, mouthR=$mouthRatio";
          break;
        case ChallengeType.blink:
          // Both eyes closed (proper blink). One eye closed = wink = FAIL.
          expressionMatched = bothEyesClosed && !isWinking;
          debugInfo = "Blink: L=$leftEye, R=$rightEye (both must be closed)";
          break;
        case ChallengeType.mouthOpen:
          // Mouth open as "oh" or surprised. Jaw relaxed.
          if (nose != null && bottomMouth != null) {
            expressionMatched = mouthOpenOh && smileProb < 0.40;
            debugInfo = "Mouth: ratio=$mouthRatio (oh/surprised)";
          } else {
            expressionMatched = false;
            debugInfo = "Mouth: landmarks missing";
          }
          break;
        case ChallengeType.neutral:
          // Relaxed face, lips closed, eyes open, no smile or frown.
          final notSmiling = smileProb < 0.32;
          expressionMatched =
              notSmiling && lipsClosed && bothEyesOpen && !mouthOpenOh;
          debugInfo =
              "Neutral: smile=$smileProb, mouthR=$mouthRatio, eyes open";
          break;
      }

      // 5. ANTI-MATCH: Wrong expression = FAIL
      switch (_currentChallenge!.type) {
        case ChallengeType.smile:
          if (mouthOpenOh || bothEyesClosed || isWinking)
            expressionMatched = false;
          break;
        case ChallengeType.blink:
          if (isWinking)
            expressionMatched = false; // One eye closed = wink, not blink
          break;
        case ChallengeType.mouthOpen:
          if (smileProb > 0.45 || bothEyesClosed || isWinking)
            expressionMatched = false;
          break;
        case ChallengeType.neutral:
          if (smileProb > 0.35 || mouthOpenOh || !bothEyesOpen)
            expressionMatched = false;
          break;
      }

      debugPrint(
          "Liveness ${_currentChallenge!.type}: $debugInfo → ${expressionMatched ? 'MATCH' : 'NO'}");

      await File(photo.path).delete();
      _isProcessing = false;

      // ✅ Require expression to be held for MORE consecutive frames for higher security
      // CRITICAL: This ensures the user actually performs the action, not just a momentary match
      // CRITICAL: Check timer hasn't expired before marking as passed
      final framesNeeded =
          _currentChallenge!.type == ChallengeType.blink ? 3 : 5;
      if (expressionMatched && _livenessSecondsRemaining > 0) {
        _livenessSuccessStreak++;
        debugPrint(
            "✅ Expression matched! Streak: $_livenessSuccessStreak/$framesNeeded");
        if (_livenessSuccessStreak >= framesNeeded) {
          // Expression held consistently for 5 frames - success!
          // CRITICAL: Double-check timer hasn't expired and liveness hasn't already failed
          if (mounted && !_livenessPassed && _livenessSecondsRemaining > 0) {
            debugPrint(
                "🎉 Liveness PASSED! Expression held for 3 consecutive frames.");
            _livenessPassed = true;
            _livenessTimer?.cancel();
            _handleLivenessSuccess();
          } else {
            debugPrint(
                "⚠️ Cannot mark as passed - timer expired or already passed/failed");
          }
        }
      } else {
        // Expression not matched OR timer expired - reset streak immediately
        // CRITICAL: Any frame without match resets the counter - ensures actual performance
        if (_livenessSuccessStreak > 0) {
          debugPrint(
              "❌ Expression NOT matched (or timer expired). Resetting streak from $_livenessSuccessStreak to 0");
          _livenessSuccessStreak = 0;
        }
      }
    } catch (e) {
      debugPrint("Liveness Error: $e");
      _isProcessing = false;
    }
  }

  void _handleLivenessSuccess() {
    // CRITICAL: Double-check liveness actually passed before proceeding
    if (!_livenessPassed || _livenessSecondsRemaining <= 0) {
      debugPrint("❌ Cannot proceed to success - liveness not actually passed");
      _showFinalFailure("Liveness check failed. Please try again.");
      return;
    }

    setState(() {
      _statusMessage = "✔ Step 2 completed\n✔ Liveness detection completed";
    });
    Timer(const Duration(seconds: 1), () {
      // CRITICAL: Check again before recording attendance
      if (_livenessPassed && _recognizedUserId != null) {
        _recordAttendance();
      } else {
        debugPrint(
            "❌ Cannot record - liveness not passed or user not recognized");
        _showFinalFailure("Liveness check failed. Please try again.");
      }
    });
  }

  String _getChallengeActionName(ChallengeType type) {
    switch (type) {
      case ChallengeType.smile:
        return "smile";
      case ChallengeType.blink:
        return "blink";
      case ChallengeType.mouthOpen:
        return "mouth_open";
      case ChallengeType.neutral:
        return "neutral";
    }
  }

  Future<void> _logLivenessStarted() async {
    if (_currentSessionId == null || _recognizedUserId == null) return;
    try {
      await http.post(
        Uri.parse('$apiBaseUrl/api/v1/liveness/started'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'session_id': _currentSessionId,
          'user_id': _recognizedUserId,
          'device_id': 'mobile_app',
          'actions_requested': [_currentChallengeAction ?? 'unknown'],
        }),
      );
    } catch (e) {
      debugPrint("⚠️ Failed to log liveness started: $e");
    }
  }

  Future<void> _logLivenessAttempt(int attemptNum, String? failedAction) async {
    if (_currentSessionId == null) return;
    try {
      await http.post(
        Uri.parse('$apiBaseUrl/api/v1/liveness/attempt'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'session_id': _currentSessionId,
          'attempt_number': attemptNum,
          'failed_action': failedAction,
          'reason': 'timeout',
        }),
      );
    } catch (e) {
      debugPrint("⚠️ Failed to log liveness attempt: $e");
    }
  }

  void _handleLivenessFailure() {
    // CRITICAL: Immediately mark liveness as failed to prevent any success callbacks
    _livenessPassed = false;
    _livenessTimer?.cancel();

    // ✅ Log liveness attempt failure
    if (_currentSessionId != null) {
      _logLivenessAttempt(_attempts, _currentChallengeAction);
    }

    if (_attempts < _maxAttempts) {
      setState(() {
        _statusMessage = "Liveness failed. Try again.";
      });
      Timer(const Duration(seconds: 2), () {
        if (mounted) _startLivenessPhase();
      });
    } else {
      // ✅ Log final liveness failure by calling record with liveness=failed
      // This will trigger backend logging without creating attendance record
      _recordAttendanceFailure();
    }
  }

  Future<void> _recordAttendanceFailure() async {
    // Record liveness failure - backend will log it but not create attendance record
    try {
      await http.post(
        Uri.parse('$apiBaseUrl/api/v1/record'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'user_id': _recognizedUserId,
          'liveness': 'failed',
          'event_type': 'check_in',
          'session_id': _currentSessionId ??
              DateTime.now().millisecondsSinceEpoch.toString(),
          'device_id': 'mobile_app',
          'attempts_used': _attempts,
          'final_failed_action': _currentChallengeAction,
          'actions_requested': [_currentChallengeAction ?? 'unknown'],
          'liveness_start_time': _livenessStartTime != null
              ? _livenessStartTime!.millisecondsSinceEpoch / 1000.0
              : null,
        }),
      );
    } catch (e) {
      debugPrint("⚠️ Failed to log liveness failure: $e");
    }
    _showFinalFailure("Liveness check failed. Please try again.");
  }

  Future<void> _recordAttendance() async {
    // CRITICAL: Multiple checks to ensure liveness actually passed
    if (!_livenessPassed) {
      debugPrint("❌ Cannot record attendance - liveness not passed (check 1)");
      _showFinalFailure("Liveness check failed. Please try again.");
      return;
    }

    if (_livenessSecondsRemaining <= 0) {
      debugPrint("❌ Cannot record attendance - timer expired (check 2)");
      _showFinalFailure("Liveness check failed. Time expired.");
      return;
    }

    if (_recognizedUserId == null || _recognizedUserName == null) {
      debugPrint("❌ Cannot record attendance - user not recognized (check 3)");
      _showFinalFailure("User not recognized. Please try again.");
      return;
    }

    setState(() {
      _currentPhase = AttendancePhase.recording;
      _statusMessage = "Recording attendance...\nWaiting for server...";
      _isWaitingForBackend = true;
    });

    try {
      final response = await http.post(
        // Use same backend host as WebSocket to avoid network mismatch errors
        Uri.parse('$apiBaseUrl/api/v1/record'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'user_id': _recognizedUserId,
          'liveness': 'passed',
          'event_type': 'check_in',
          'session_id': _currentSessionId ??
              DateTime.now().millisecondsSinceEpoch.toString(),
          'device_id': 'mobile_app',
          'attempts_used': _attempts,
          'actions_requested': [_currentChallengeAction ?? 'unknown'],
          'liveness_start_time': _livenessStartTime != null
              ? _livenessStartTime!.millisecondsSinceEpoch / 1000.0
              : null,
        }),
      );

      // CRITICAL: Only show "Access Granted" if response is 200 AND status is success AND liveness is explicitly "passed"
      // Also verify frontend state is still valid
      if (response.statusCode == 200) {
        try {
          final responseData = jsonDecode(response.body);
          debugPrint(
              "📥 Backend response: status=${responseData['status']}, liveness=${responseData['liveness']}");

          // CRITICAL: Multiple checks before showing access granted
          final backendStatus = responseData['status'];
          final backendLiveness = responseData['liveness'];

          // NEVER show access granted unless ALL conditions are met:
          // 1. Backend status is 'success'
          // 2. Backend liveness is explicitly 'passed' (not null, not 'failed', not anything else)
          // 3. Frontend liveness is still marked as passed
          if (backendStatus == 'success' &&
              backendLiveness == 'passed' &&
              _livenessPassed) {
            debugPrint(
                "✅ Backend confirmed attendance recorded successfully with liveness passed");
            setState(() {
              _isWaitingForBackend = false;
              _currentPhase = AttendancePhase.finalResult;
              _statusMessage = "Access Granted";
            });
          } else {
            // Backend rejected or frontend state invalid - show failure
            debugPrint("❌ Backend rejected or frontend state invalid");
            debugPrint(
                "   Backend status: $backendStatus, liveness: $backendLiveness");
            debugPrint("   Frontend liveness passed: $_livenessPassed");
            _isWaitingForBackend = false;
            _showFinalFailure(
                "Liveness check failed. Attendance not recorded.");
          }
        } catch (e) {
          // If response parsing fails, DO NOT assume success - treat as failure
          debugPrint("❌ Could not parse response - treating as failure: $e");
          _isWaitingForBackend = false;
          _showFinalFailure("Failed to record attendance. Please try again.");
        }
      } else if (response.statusCode == 400) {
        // HTTP 400 = Bad Request = Liveness failed (backend explicitly rejected)
        debugPrint("❌ HTTP 400: Backend rejected - liveness failed");
        try {
          final errorData = jsonDecode(response.body);
          debugPrint(
              "   Error detail: ${errorData['detail'] ?? errorData['message']}");
          debugPrint(
              "   Status: ${errorData['status']}, Liveness: ${errorData['liveness']}");
        } catch (e) {
          debugPrint("   Could not parse error response");
        }
        _isWaitingForBackend = false;
        _showFinalFailure("Liveness check failed. Attendance NOT recorded.");
      } else {
        debugPrint("❌ HTTP error: ${response.statusCode}");
        _isWaitingForBackend = false;
        _showFinalFailure("Failed to record attendance");
      }
    } catch (e) {
      debugPrint("❌ Network error: $e");
      _isWaitingForBackend = false;
      _showFinalFailure("Network Error: $e");
    }
  }

  void _showFinalFailure(String msg) {
    _livenessPassed = false;
    _isWaitingForBackend = false;
    _livenessFaceDetected = false;
    _livenessSuccessStreak = 0;
    _livenessTimer?.cancel();
    _isRecognized = false;
    _recognizedUserId = null;
    _recognizedUserName = null;
    _currentSessionId = null;
    _currentChallenge = null;
    _currentChallengeAction = null;
    _livenessStartTime = null;
    _attempts = 0;

    setState(() {
      _currentPhase = AttendancePhase.fail;
      _statusMessage = msg;
    });

    // Always redirect back to phase 1 (recognition phase) after failure - complete restart
    Timer(const Duration(seconds: 2), () {
      if (mounted) {
        debugPrint(
            "🔄 Redirecting to phase 1 (recognition phase) after liveness failure - complete restart");
        _startPhase1();
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
      case AttendancePhase.transition:
        return _buildTransitionUI();
      case AttendancePhase.liveness:
        return _buildLivenessUI();
      case AttendancePhase.recording:
        return _buildRecordingUI();
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
          // Slight overlay for focus but keep camera bright
          Container(color: Colors.black.withOpacity(0.12)),
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

  Widget _buildRecordingUI() => Container(
      color: Colors.blueGrey.shade900,
      child: Center(
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
        if (_isWaitingForBackend)
          const CircularProgressIndicator(color: Colors.white)
        else
          const SizedBox.shrink(),
        const SizedBox(height: 24),
        Text(_statusMessage,
            textAlign: TextAlign.center,
            style: const TextStyle(color: Colors.white, fontSize: 18)),
        const SizedBox(height: 8),
        const Text("Do not leave this screen",
            style: TextStyle(color: Colors.white54, fontSize: 14)),
      ])));

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
