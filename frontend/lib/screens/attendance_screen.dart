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
  int _livenessSuccessStreak =
      0; // Track consecutive frames with correct expression
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
        Uri.parse('ws://192.168.100.58:8000/api/v1/ws/attendance'));
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
    _livenessSecondsRemaining = 5;
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

      bool expressionMatched = false;
      String debugInfo = "";

      // 4. Liveness Logic - Check if expression matches challenge
      // Tuned thresholds: now STRICTER so user must clearly perform the emoji action
      switch (_currentChallenge!.type) {
        case ChallengeType.smile:
          final smileProb = face.smilingProbability ?? 0.0;
          // Fallback using mouth geometry (ML Kit smilingProbability is often conservative)
          double mouthRatio = 0.0;
          double mouthWidthRatio = 0.0;
          final nose = face.landmarks[FaceLandmarkType.noseBase];
          final bottomMouth = face.landmarks[FaceLandmarkType.bottomMouth];
          final leftMouth = face.landmarks[FaceLandmarkType.leftMouth];
          final rightMouth = face.landmarks[FaceLandmarkType.rightMouth];
          if (nose != null && bottomMouth != null) {
            final mouthY = bottomMouth.position.y.toDouble();
            final noseY = nose.position.y.toDouble();
            final diff = (mouthY - noseY).abs();
            final faceHeight = face.boundingBox.height.toDouble();
            if (faceHeight > 0) mouthRatio = diff / faceHeight;
          }
          if (leftMouth != null && rightMouth != null) {
            final w = (rightMouth.position.x - leftMouth.position.x).toDouble();
            final faceW = face.boundingBox.width.toDouble();
            if (faceW > 0) mouthWidthRatio = w.abs() / faceW;
          }
          // STRICTER thresholds: user must give a clear smile
          // - Strong smile probability
          // - Or moderate probability + clear mouth drop
          // - Or clearly stretched mouth width
          final probStrongSmile = smileProb > 0.35;
          final probModerateSmile = smileProb > 0.22 && mouthRatio > 0.20;
          final mouthStretchSmile =
              mouthWidthRatio > 0.32; // smile widens mouth
          expressionMatched =
              probStrongSmile || probModerateSmile || mouthStretchSmile;
          debugInfo =
              "Smile: prob=$smileProb, mouthRatio=$mouthRatio, mouthW=$mouthWidthRatio";
          debugPrint(
              "😊 ${debugInfo} → ${expressionMatched ? 'MATCH' : 'NO MATCH'}");
          break;
        case ChallengeType.blink:
          final leftEye = face.leftEyeOpenProbability ?? 1.0;
          final rightEye = face.rightEyeOpenProbability ?? 1.0;
          // STRICT blink detection:
          // - Require BOTH eyes to be clearly closed (no more "half-blinks" or small eye movements)
          final bothClosed = leftEye < 0.35 && rightEye < 0.35;
          expressionMatched = bothClosed;
          debugInfo = "Blink: L=$leftEye, R=$rightEye (both<0.35)";
          debugPrint(
              "😉 ${debugInfo} → ${expressionMatched ? 'MATCH' : 'NO MATCH'}");
          break;
        case ChallengeType.neutral:
          final smileProb = face.smilingProbability ?? 0.5;
          final leftEye = face.leftEyeOpenProbability ?? 0.0;
          final rightEye = face.rightEyeOpenProbability ?? 0.0;
          final avgEyeOpen = (leftEye + rightEye) / 2.0;
          // STRICTER neutral:
          // - Almost no smile
          // - Eyes reasonably open
          final notSmiling = smileProb < 0.35;
          final eyesOpen = avgEyeOpen > 0.60;
          expressionMatched = notSmiling && eyesOpen;
          debugInfo =
              "Neutral: smile=$smileProb (<0.35), eyes=$avgEyeOpen (>0.60)";
          debugPrint(
              "😐 ${debugInfo} → ${expressionMatched ? 'MATCH' : 'NO MATCH'}");
          break;
        case ChallengeType.mouthOpen:
          final nose = face.landmarks[FaceLandmarkType.noseBase];
          final mouth = face.landmarks[FaceLandmarkType.bottomMouth];
          if (nose != null && mouth != null) {
            final mouthY = mouth.position.y.toDouble();
            final noseY = nose.position.y.toDouble();
            final diff = (mouthY - noseY).abs();
            final faceHeight = face.boundingBox.height.toDouble();
            final ratio = diff / faceHeight;
            // STRICTER mouth-open threshold:
            // User must clearly open mouth, not just slightly
            expressionMatched = ratio > 0.26;
            debugInfo =
                "Mouth: diff=$diff, height=$faceHeight, ratio=$ratio (need >0.26)";
            debugPrint(
                "😮 ${debugInfo} → ${expressionMatched ? 'MATCH' : 'NO MATCH'}");
          } else {
            debugPrint(
                "😮 Mouth: Landmarks missing (nose=${nose != null}, mouth=${mouth != null})");
            expressionMatched = false; // Fail if landmarks missing
          }
          break;
      }

      await File(photo.path).delete();
      _isProcessing = false;

      // ✅ Require expression to be held for MORE consecutive frames for higher security
      // CRITICAL: This ensures the user actually performs the action, not just a momentary match
      // CRITICAL: Check timer hasn't expired before marking as passed
      if (expressionMatched && _livenessSecondsRemaining > 0) {
        _livenessSuccessStreak++;
        debugPrint(
            "✅ Expression matched! Streak: $_livenessSuccessStreak/5 (need 5 for strict security)");
        if (_livenessSuccessStreak >= 5) {
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
        Uri.parse('http://192.168.100.58:8000/api/v1/liveness/started'),
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
        Uri.parse('http://192.168.100.58:8000/api/v1/liveness/attempt'),
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
        Uri.parse('http://192.168.100.58:8000/api/v1/record'),
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
      _statusMessage = "Recording attendance...";
    });

    try {
      final response = await http.post(
        // Use same backend host as WebSocket to avoid network mismatch errors
        Uri.parse('http://192.168.100.58:8000/api/v1/record'),
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
              _currentPhase = AttendancePhase.finalResult;
              _statusMessage = "Access Granted";
            });
          } else {
            // Backend rejected or frontend state invalid - show failure
            debugPrint("❌ Backend rejected or frontend state invalid");
            debugPrint(
                "   Backend status: $backendStatus, liveness: $backendLiveness");
            debugPrint("   Frontend liveness passed: $_livenessPassed");
            _showFinalFailure(
                "Liveness check failed. Attendance not recorded.");
          }
        } catch (e) {
          // If response parsing fails, DO NOT assume success - treat as failure
          debugPrint("❌ Could not parse response - treating as failure: $e");
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
        _showFinalFailure("Liveness check failed. Attendance NOT recorded.");
      } else {
        // Other HTTP error - don't show access granted, redirect to phase 1
        debugPrint("❌ HTTP error: ${response.statusCode}");
        _showFinalFailure("Failed to record attendance");
      }
    } catch (e) {
      // Network error - don't show access granted, redirect to phase 1
      debugPrint("❌ Network error: $e");
      _showFinalFailure("Network Error: $e");
    }
  }

  void _showFinalFailure(String msg) {
    // CRITICAL: Reset ALL state to prevent showing "Access Granted" and ensure clean restart
    _livenessPassed = false;
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
