// frontend/lib/screens/attendance_screen.dart

import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:google_mlkit_face_detection/google_mlkit_face_detection.dart';

class AttendanceScreen extends StatefulWidget {
  final List<CameraDescription> cameras;
  const AttendanceScreen({super.key, required this.cameras});
  @override
  State<AttendanceScreen> createState() => _AttendanceScreenState();
}

class _AttendanceScreenState extends State<AttendanceScreen> {
  CameraController? _controller;
  WebSocketChannel? _channel;
  String _statusMessage = "Initializing camera...";
  Timer? _captureTimer;
  bool _isRecognized = false;
  bool _faceDetected = false;
  String? _recognizedUserName;

  // ML Kit Face Detector (The Quality Gate)
  final FaceDetector _faceDetector = FaceDetector(
    options: FaceDetectorOptions(
      enableLandmarks: true,
      performanceMode: FaceDetectorMode.fast,
    ),
  );

  @override
  void initState() {
    super.initState();
    _initializeCamera();
  }

  void _initializeCamera() async {
    try {
      final front = widget.cameras
          .firstWhere((c) => c.lensDirection == CameraLensDirection.front);
      _controller =
          CameraController(front, ResolutionPreset.medium, enableAudio: false);
      await _controller!.initialize();
      if (mounted) {
        setState(() {
          _statusMessage = "Place your face inside the frame";
        });
        _connectWebSocket();
        _startSmartCapture();
      }
    } catch (e) {
      setState(() {
        _statusMessage = "Camera Error: $e";
      });
    }
  }

  void _connectWebSocket() {
    // IMPORTANT: Replace with your computer's IP address
    const String serverIp = '192.168.165.202';
    _channel = WebSocketChannel.connect(
        Uri.parse('ws://$serverIp:8000/api/v1/ws/attendance'));

    _channel!.stream.listen((data) {
      final res = jsonDecode(data);
      if (!mounted || _isRecognized) return;
      setState(() {
        if (res['status'] == 'success') {
          _isRecognized = true;
          _recognizedUserName = res['name'];
          _statusMessage = "✔ Face recognized";
          _captureTimer?.cancel();
        } else if (res['status'] == 'not_recognized') {
          _statusMessage = "Face not registered";
        }
      });
    },
        onError: (e) =>
            setState(() => _statusMessage = "Server Connection Error"));
  }

  void _startSmartCapture() {
    _captureTimer =
        Timer.periodic(const Duration(milliseconds: 1500), (timer) async {
      if (_isRecognized ||
          _channel == null ||
          !(_controller?.value.isInitialized ?? false)) return;

      try {
        // 1. Capture high-quality JPEG
        final XFile photo = await _controller!.takePicture();
        final inputImage = InputImage.fromFilePath(photo.path);

        // 2. Run Local ML Kit Detection (The Bouncer)
        final List<Face> faces = await _faceDetector.processImage(inputImage);

        if (faces.isEmpty) {
          setState(() {
            _faceDetected = false;
            _statusMessage = "No face detected";
          });
          await File(photo.path).delete();
          return;
        }

        final face = faces.first;
        final rect = face.boundingBox;

        // 3. QUALITY GATE: Check size and orientation
        if (rect.width < 120 || rect.height < 120) {
          setState(() {
            _faceDetected = true;
            _statusMessage = "Face too far. Come closer.";
          });
          await File(photo.path).delete();
          return;
        }

        if ((face.headEulerAngleY ?? 0).abs() > 15 ||
            (face.headEulerAngleX ?? 0).abs() > 15) {
          setState(() {
            _faceDetected = true;
            _statusMessage = "Please look straight";
          });
          await File(photo.path).delete();
          return;
        }

        // 4. VALID FACE: Send to backend
        setState(() {
          _faceDetected = true;
          _statusMessage = "Recognizing...";
        });
        final Uint8List bytes = await File(photo.path).readAsBytes();
        _channel!.sink.add(bytes);
        await File(photo.path).delete();
      } catch (e) {
        debugPrint("Capture error: $e");
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_controller == null || !_controller!.value.isInitialized)
      return const Scaffold(body: Center(child: CircularProgressIndicator()));

    Color frameColor = _isRecognized
        ? Colors.green
        : (_faceDetected ? Colors.orange : Colors.blue);
    if (_statusMessage.contains("not registered")) frameColor = Colors.red;

    return Scaffold(
      appBar: AppBar(title: const Text("Real-time Attendance")),
      body: Column(children: [
        const SizedBox(height: 20),
        Center(
          child: Container(
            width: 300,
            height: 350,
            decoration: BoxDecoration(
                border: Border.all(color: frameColor, width: 6),
                borderRadius: BorderRadius.circular(20)),
            child: ClipRRect(
                borderRadius: BorderRadius.circular(15),
                child: CameraPreview(_controller!)),
          ),
        ),
        const SizedBox(height: 30),
        Text(_statusMessage,
            textAlign: TextAlign.center,
            style: TextStyle(
                color: frameColor, fontSize: 22, fontWeight: FontWeight.bold)),
        if (_isRecognized)
          Text("Welcome, $_recognizedUserName",
              style: const TextStyle(
                  color: Colors.green,
                  fontSize: 26,
                  fontWeight: FontWeight.bold)),
      ]),
    );
  }

  @override
  void dispose() {
    _captureTimer?.cancel();
    _faceDetector.close();
    _controller?.dispose();
    _channel?.sink.close();
    super.dispose();
  }
}
