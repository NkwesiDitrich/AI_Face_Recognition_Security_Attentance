import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

class AttendanceScreen extends StatefulWidget {
  final List<CameraDescription> cameras;
  const AttendanceScreen({super.key, required this.cameras});

  @override
  State<AttendanceScreen> createState() => _AttendanceScreenState();
}

class _AttendanceScreenState extends State<AttendanceScreen> {
  late CameraController _controller;
  late Future<void> _initializeControllerFuture;

  late WebSocketChannel _channel;
  String _statusMessage = "Connecting to server...";
  Timer? _timer;

  /// WS endpoint from your FastAPI backend
  static const String _wsUrl = 'ws://10.0.2.2:8000/api/v1/ws/attendance';

  @override
  void initState() {
    super.initState();
    _initializeCamera();
    _connectWebSocket();
  }

  // -----------------------
  // CAMERA INITIALIZATION
  // -----------------------
  void _initializeCamera() {
    if (widget.cameras.isEmpty) {
      setState(() => _statusMessage = "No cameras available");
      return;
    }

    // FRONT CAMERA
    _controller = CameraController(
      widget.cameras.firstWhere(
        (camera) => camera.lensDirection == CameraLensDirection.front,
      ),
      ResolutionPreset.low,
      enableAudio: false,
    );

    _initializeControllerFuture = _controller.initialize().then((_) {
      if (!mounted) return;
      setState(() => _statusMessage = "Camera ready. Starting stream...");
      _startFrameStream();
    }).catchError((e) {
      setState(() => _statusMessage = "Camera initialization failed: $e");
    });
  }

  // -----------------------
  // WEBSOCKET CONNECTION
  // -----------------------
  void _connectWebSocket() {
    try {
      _channel = WebSocketChannel.connect(Uri.parse(_wsUrl));

      _channel.stream.listen(
        (data) {
          final response = jsonDecode(data);
          setState(() {
            _statusMessage = response['message'] ?? "Processing...";
          });
        },
        onDone: () => setState(() {
          _statusMessage = "Connection closed by server.";
        }),
        onError: (error) => setState(() {
          _statusMessage = "WebSocket Error: $error";
        }),
      );
    } catch (e) {
      setState(() {
        _statusMessage = "Could not connect: $e";
      });
    }
  }

  // -----------------------
  // SEND CAMERA FRAMES
  // -----------------------
  void _startFrameStream() {
    _controller.startImageStream((CameraImage image) async {
      // Send one frame every 500ms
      if (_timer == null || !_timer!.isActive) {
        _timer = Timer(const Duration(milliseconds: 500), () async {
          // TEMPORARY PLACEHOLDER
          _channel.sink.add(Uint8List.fromList([1, 2, 3, 4]));

          // (Real image conversion comes later)
          _timer = null;
        });
      }
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    _channel.sink.close();
    _timer?.cancel();
    super.dispose();
  }

  // -----------------------
  // UI
  // -----------------------
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("Real-Time Attendance")),
      body: FutureBuilder<void>(
        future: _initializeControllerFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.done) {
            return Stack(
              children: [
                SizedBox(
                  width: MediaQuery.of(context).size.width,
                  height: MediaQuery.of(context).size.height,
                  child: CameraPreview(_controller),
                ),
                Positioned(
                  bottom: 0,
                  left: 0,
                  right: 0,
                  child: Container(
                    padding: const EdgeInsets.all(16),
                    color: Colors.black54,
                    child: Text(
                      _statusMessage,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 18,
                      ),
                      textAlign: TextAlign.center,
                    ),
                  ),
                ),
              ],
            );
          } else {
            return Center(child: Text(_statusMessage));
          }
        },
      ),
    );
  }
}
