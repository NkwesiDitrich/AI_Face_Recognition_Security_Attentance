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
      _controller = CameraController(
        widget.cameras.firstWhere(
          (camera) => camera.lensDirection == CameraLensDirection.front,
        ),
        ResolutionPreset.medium,
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

      await _initializeControllerFuture;

      final XFile imageFile = await _controller.takePicture();
      final File file = File(imageFile.path);

      final userService = Provider.of<UserService>(context, listen: false);

      final result = await userService.enrollUser(
        name: _nameController.text,
        employeeId: _employeeIdController.text,
        accessLevel: 'employee',
        imageFile: file,
      );

      if (result["success"]) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Enrollment Successful!")),
        );
        _nameController.clear();
        _employeeIdController.clear();
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("Enrollment Failed: ${result['message']}")),
        );
      }
    } catch (e) {
      print(e);
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
      appBar: AppBar(title: Text("Admin Enrollment")),
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
                    SizedBox(height: 300, child: CameraPreview(_controller)),
                    SizedBox(height: 20),
                    TextFormField(
                      controller: _nameController,
                      decoration: InputDecoration(labelText: "Full Name"),
                      validator: (value) => value!.isEmpty ? "Required" : null,
                    ),
                    TextFormField(
                      controller: _employeeIdController,
                      decoration: InputDecoration(labelText: "Employee ID"),
                      validator: (value) => value!.isEmpty ? "Required" : null,
                    ),
                    SizedBox(height: 30),
                    ElevatedButton(
                      onPressed: _isEnrolling ? null : _takePictureAndEnroll,
                      child: _isEnrolling
                          ? CircularProgressIndicator()
                          : Text("Take Picture & Enroll"),
                    ),
                  ],
                ),
              ),
            );
          }
          return Center(child: CircularProgressIndicator());
        },
      ),
    );
  }
}
