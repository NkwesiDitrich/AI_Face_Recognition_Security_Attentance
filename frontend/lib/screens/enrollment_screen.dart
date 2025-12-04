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
        ResolutionPreset.high, // ✅ CHANGED FROM medium TO high
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

      print("📸 Picture taken: ${file.path}");

      final userService = Provider.of<UserService>(context, listen: false);

      final result = await userService.enrollUser(
        name: _nameController.text.trim(),
        employeeId: _employeeIdController.text.trim(),
        accessLevel: 'employee',
        imageFile: file,
      );

      if (result["success"] == true) {
        print("✅ Enrollment successful!");
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text("✅ Enrollment Successful!"),
            backgroundColor: Colors.green,
          ),
        );

        // Reset fields
        _nameController.clear();
        _employeeIdController.clear();
      } else {
        print("❌ Enrollment failed: ${result["message"]}");
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text("❌ Enrollment Failed: ${result["message"]}"),
            backgroundColor: Colors.red,
          ),
        );
      }
    } catch (e) {
      print("❌ Enrollment Error: $e");
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text("❌ Error: $e"),
          backgroundColor: Colors.red,
        ),
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
      appBar: AppBar(
        title: const Text("Admin Enrollment"),
        backgroundColor: Colors.blue,
      ),
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
                    // 🔥 IMPROVED CAMERA PREVIEW WITH GUIDE
                    Container(
                      height: 300,
                      decoration: BoxDecoration(
                        border: Border.all(color: Colors.blue, width: 2),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Stack(
                        children: [
                          CameraPreview(_controller),
                          // Face detection guide overlay
                          Center(
                            child: Container(
                              width: 200,
                              height: 250,
                              decoration: BoxDecoration(
                                border:
                                    Border.all(color: Colors.green, width: 3),
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: const Column(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  Icon(
                                    Icons.face,
                                    color: Colors.green,
                                    size: 50,
                                  ),
                                  SizedBox(height: 10),
                                  Text(
                                    "Position your face here",
                                    style: TextStyle(
                                      color: Colors.white,
                                      fontSize: 14,
                                      fontWeight: FontWeight.bold,
                                      shadows: [
                                        Shadow(
                                          blurRadius: 3,
                                          color: Colors.black,
                                        ),
                                      ],
                                    ),
                                    textAlign: TextAlign.center,
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 20),

                    // Name field
                    TextFormField(
                      controller: _nameController,
                      decoration: InputDecoration(
                        labelText: "Full Name",
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(8),
                        ),
                        prefixIcon: const Icon(Icons.person),
                      ),
                      validator: (value) =>
                          value!.isEmpty ? "Name is required" : null,
                    ),
                    const SizedBox(height: 15),

                    // Employee ID field
                    TextFormField(
                      controller: _employeeIdController,
                      decoration: InputDecoration(
                        labelText: "Employee ID",
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(8),
                        ),
                        prefixIcon: const Icon(Icons.badge),
                      ),
                      validator: (value) =>
                          value!.isEmpty ? "Employee ID is required" : null,
                    ),
                    const SizedBox(height: 30),

                    // Enroll button
                    SizedBox(
                      width: double.infinity,
                      height: 50,
                      child: ElevatedButton(
                        onPressed:
                            _isEnrolling ? null : () => _takePictureAndEnroll(),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.blue,
                          disabledBackgroundColor: Colors.grey,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(8),
                          ),
                        ),
                        child: _isEnrolling
                            ? const SizedBox(
                                height: 20,
                                width: 20,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  valueColor: AlwaysStoppedAnimation<Color>(
                                    Colors.white,
                                  ),
                                ),
                              )
                            : const Row(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  Icon(Icons.camera_alt),
                                  SizedBox(width: 10),
                                  Text(
                                    "Take Picture & Enroll",
                                    style: TextStyle(
                                      fontSize: 16,
                                      fontWeight: FontWeight.bold,
                                    ),
                                  ),
                                ],
                              ),
                      ),
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
