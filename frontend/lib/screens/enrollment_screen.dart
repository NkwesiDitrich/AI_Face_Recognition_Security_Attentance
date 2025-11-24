import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:provider/provider.dart';
import 'dart:io';
import 'package:ai_face_attendance_frontend/services/user_service.dart';

class EnrollmentScreen extends StatefulWidget {
  final List<CameraDescription> cameras;

  const EnrollmentScreen({super.key, required this.cameras});

  @override
  State<EnrollmentScreen> createState() => _EnrollmentScreenState();
}

class _EnrollmentScreenState extends State<EnrollmentScreen> {
  late CameraController _controller;
  late Future<void> _initializeControllerFuture;

  final _formKey = GlobalKey<FormState>();
  final TextEditingController _nameController = TextEditingController();
  final TextEditingController _employeeIdController = TextEditingController();

  bool _isEnrolling = false;

  @override
  void initState() {
    super.initState();

    if (widget.cameras.isNotEmpty) {
      final frontCamera = widget.cameras.firstWhere(
        (camera) => camera.lensDirection == CameraLensDirection.front,
        orElse: () => widget.cameras.first,
      );

      _controller = CameraController(
        frontCamera,
        ResolutionPreset.medium,
        enableAudio: false,
      );

      _initializeControllerFuture = _controller.initialize();
    } else {
      _initializeControllerFuture = Future.error("No cameras available");
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    _nameController.dispose();
    _employeeIdController.dispose();
    super.dispose();
  }

  Future<void> _takePictureAndEnroll() async {
    if (_isEnrolling || !_formKey.currentState!.validate()) return;

    try {
      setState(() {
        _isEnrolling = true;
      });

      // Make sure the camera is ready
      await _initializeControllerFuture;

      // 🔥 FIX: Add delay to avoid camera hang problem
      await Future.delayed(const Duration(milliseconds: 500));

      // Take picture
      final XFile imageFile = await _controller.takePicture();
      final File file = File(imageFile.path);

      final userService = Provider.of<UserService>(context, listen: false);

      final result = await userService.enrollUser(
        name: _nameController.text.trim(),
        employeeId: _employeeIdController.text.trim(),
        accessLevel: 'employee',
        imageFile: file,
      );

      if (result["success"] == true) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text("Enrollment Successful!")),
        );

        // Reset fields
        _nameController.clear();
        _employeeIdController.clear();
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Enrollment Failed: ${result["message"]}")),
        );
      }
    } catch (e) {
      print("Enrollment Error: $e");
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text("Error: $e")),
      );
    } finally {
      setState(() {
        _isEnrolling = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("Admin Enrollment")),
      body: FutureBuilder(
        future: _initializeControllerFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.done) {
            return SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Form(
                key: _formKey,
                child: Column(
                  children: [
                    SizedBox(
                      height: 300,
                      child: CameraPreview(_controller),
                    ),
                    const SizedBox(height: 20),
                    TextFormField(
                      controller: _nameController,
                      decoration: const InputDecoration(
                        labelText: "Full Name",
                      ),
                      validator: (value) =>
                          value!.isEmpty ? "Name is required" : null,
                    ),
                    TextFormField(
                      controller: _employeeIdController,
                      decoration: const InputDecoration(
                        labelText: "Employee ID",
                      ),
                      validator: (value) =>
                          value!.isEmpty ? "Employee ID is required" : null,
                    ),
                    const SizedBox(height: 30),
                    ElevatedButton(
                      onPressed:
                          _isEnrolling ? null : () => _takePictureAndEnroll(),
                      child: _isEnrolling
                          ? const SizedBox(
                              height: 20,
                              width: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text("Take Picture & Enroll"),
                    ),
                  ],
                ),
              ),
            );
          }

          return const Center(child: CircularProgressIndicator());
        },
      ),
    );
  }
}
