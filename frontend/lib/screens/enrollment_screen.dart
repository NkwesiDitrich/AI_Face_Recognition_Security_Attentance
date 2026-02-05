import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:provider/provider.dart';
import 'dart:io';
import 'package:ai_face_attendance_frontend/services/user_service.dart';

/// ============================================================================
/// ENROLLMENT SCREEN - Face Registration with Image Preview
/// ============================================================================
///
/// This screen allows users to enroll in the face recognition system.
///
/// Features:
/// 1. Camera preview for live face capture
/// 2. User input for name and employee ID
/// 3. ✨ NEW: Image preview dialog before enrollment
/// 4. ✨ NEW: Ability to retake photo if not satisfied
/// 5. Backend integration with duplicate detection
///
/// Flow:
/// 1. User enters name and employee ID
/// 2. Camera preview shown
/// 3. User clicks "Take Picture & Enroll"
/// 4. Image captured and preview dialog shown
/// 5. User confirms "Face looks good" or "Retake"
/// 6. If confirmed → Send to backend
/// 7. If retake → Return to camera preview
/// 8. Backend processes enrollment with duplicate detection
/// 9. Success/Error message shown
///
/// ============================================================================

class EnrollmentScreen extends StatefulWidget {
  /// List of available cameras on the device
  final List<CameraDescription> cameras;

  const EnrollmentScreen({super.key, required this.cameras});

  @override
  State<EnrollmentScreen> createState() => _EnrollmentScreenState();
}

class _EnrollmentScreenState extends State<EnrollmentScreen> {
  /// Camera controller for managing camera operations
  late CameraController _controller;

  /// Future that initializes the camera controller
  late Future<void> _initializeControllerFuture;

  /// Form key for validating user input
  final _formKey = GlobalKey<FormState>();

  /// Text controllers for user input
  final TextEditingController _nameController = TextEditingController();

  /// State flags
  bool _isEnrolling = false;
  String? _enrolledUserId;  // Store enrolled user ID to display

  @override
  void initState() {
    super.initState();

    // Initialize camera controller with front-facing camera
    if (widget.cameras.isNotEmpty) {
      // Find front camera, fallback to first camera if not available
      final frontCamera = widget.cameras.firstWhere(
        (camera) => camera.lensDirection == CameraLensDirection.front,
        orElse: () => widget.cameras.first,
      );

      // Create camera controller with high resolution
      _controller = CameraController(
        frontCamera,
        ResolutionPreset.high,
        enableAudio: false,
      );

      // Initialize the controller asynchronously
      _initializeControllerFuture = _controller.initialize();
    } else {
      _initializeControllerFuture = Future.error("No cameras available");
    }
  }

  @override
  void dispose() {
    // Clean up resources
    _controller.dispose();
    _nameController.dispose();
    super.dispose();
  }
  
  /// Show user ID display screen (auto-closes after 6 seconds)
  Future<void> _showUserIdDisplay(String userId) async {
    return showDialog(
      context: context,
      barrierDismissible: false,
      builder: (BuildContext context) {
        // Auto-close after 6 seconds
        Future.delayed(const Duration(seconds: 6), () {
          if (Navigator.of(context).canPop()) {
            Navigator.of(context).pop();
          }
        });
        
        return Dialog(
          backgroundColor: Colors.transparent,
          child: Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color: Colors.white,
              borderRadius: BorderRadius.circular(16),
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(
                  Icons.check_circle,
                  color: Colors.green,
                  size: 64,
                ),
                const SizedBox(height: 16),
                const Text(
                  "Enrollment Successful!",
                  style: TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 24),
                const Text(
                  "Your User ID is:",
                  style: TextStyle(
                    fontSize: 16,
                    color: Colors.grey,
                  ),
                ),
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
                  decoration: BoxDecoration(
                    color: Colors.blue.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: Colors.blue, width: 2),
                  ),
                  child: Text(
                    userId,
                    style: const TextStyle(
                      fontSize: 48,
                      fontWeight: FontWeight.bold,
                      color: Colors.blue,
                      letterSpacing: 4,
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                const Text(
                  "Please save this ID for future reference",
                  style: TextStyle(
                    fontSize: 14,
                    color: Colors.grey,
                  ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 8),
                const Text(
                  "(This will close automatically in 6 seconds)",
                  style: TextStyle(
                    fontSize: 12,
                    color: Colors.grey,
                    fontStyle: FontStyle.italic,
                  ),
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  /// =========================================================================
  /// ✨ NEW METHOD: Show Image Preview Dialog
  /// =========================================================================
  ///
  /// Displays the captured image in a dialog and asks user to confirm.
  ///
  /// Parameters:
  ///   - imageFile: The captured image file
  ///
  /// Returns:
  ///   - true: User confirmed the image looks good
  ///   - false: User wants to retake the photo
  ///
  /// =========================================================================
  Future<bool> _showImagePreviewDialog(File imageFile) async {
    print("📸 Showing image preview dialog...");

    return await showDialog<bool>(
          context: context,
          barrierDismissible: false, // User must make a choice
          builder: (BuildContext context) {
            return AlertDialog(
              // Dialog title
              title: const Text(
                "Confirm Face Image",
                style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),

              // Dialog content with image preview
              content: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    // Instructions
                    const Text(
                      "Is your face clearly visible?",
                      style: TextStyle(
                        fontSize: 14,
                        color: Colors.grey,
                      ),
                      textAlign: TextAlign.center,
                    ),

                    const SizedBox(height: 16),

                    // Display the captured image
                    Container(
                      decoration: BoxDecoration(
                        border: Border.all(
                          color: Colors.blue,
                          width: 2,
                        ),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(6),
                        child: Image.file(
                          imageFile,
                          height: 300,
                          width: 300,
                          fit: BoxFit.cover,
                        ),
                      ),
                    ),

                    const SizedBox(height: 16),

                    // Additional instructions
                    const Text(
                      "Make sure your face is clearly visible and well-lit",
                      style: TextStyle(
                        fontSize: 12,
                        color: Colors.grey,
                        fontStyle: FontStyle.italic,
                      ),
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              ),

              // Dialog actions (buttons)
              actions: [
                // Retake button
                TextButton(
                  onPressed: () {
                    print("❌ User clicked 'Retake' - returning to camera");
                    Navigator.pop(context, false); // Return false to retake
                  },
                  child: const Text(
                    "Retake",
                    style: TextStyle(
                      color: Colors.orange,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),

                // Confirm button
                ElevatedButton(
                  onPressed: () {
                    print(
                        "✅ User clicked 'Confirm & Enroll' - proceeding with enrollment");
                    Navigator.pop(context, true); // Return true to proceed
                  },
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.blue,
                    foregroundColor: Colors.white,
                  ),
                  child: const Text("Confirm & Enroll"),
                ),
              ],
            );
          },
        ) ??
        false; // Default to false if dialog is dismissed
  }

  /// =========================================================================
  /// MODIFIED METHOD: Take Picture and Enroll
  /// =========================================================================
  ///
  /// Main enrollment workflow:
  /// 1. Validate user input
  /// 2. Capture image from camera
  /// 3. ✨ NEW: Show image preview dialog
  /// 4. If user confirms → Send to backend
  /// 5. If user retakes → Return to camera
  /// 6. Handle backend response (success/duplicate/error)
  ///
  /// =========================================================================
  Future<void> _takePictureAndEnroll() async {
    // Validate form and check if already enrolling
    if (_isEnrolling || !_formKey.currentState!.validate()) {
      print("⚠️ Form validation failed or already enrolling");
      return;
    }

    try {
      // Set loading state
      setState(() {
        _isEnrolling = true;
      });

      print("📸 Starting enrollment process...");

      // Make sure the camera is ready
      await _initializeControllerFuture;

      // Add delay to avoid camera hang problem
      await Future.delayed(const Duration(milliseconds: 500));

      // Step 1: Capture image from camera
      print("📷 Capturing image from camera...");
      final XFile imageFile = await _controller.takePicture();
      final File file = File(imageFile.path);
      print("✅ Image captured: ${file.path}");

      // Step 2: ✨ NEW - Show image preview dialog
      print("🖼️ Showing image preview dialog...");
      final confirmed = await _showImagePreviewDialog(file);

      // Step 3: Check user's choice
      if (!confirmed) {
        // User clicked "Retake" - go back to camera
        print("↩️ User chose to retake - returning to camera preview");
        setState(() {
          _isEnrolling = false;
        });

        // Show snackbar informing user
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text("📸 Ready to take another photo"),
            duration: Duration(seconds: 2),
          ),
        );
        return;
      }

      // Step 4: User confirmed - proceed with enrollment
      print("✅ User confirmed image - proceeding with enrollment");

      // Get user service from provider
      final userService = Provider.of<UserService>(context, listen: false);

      // Step 5: Send enrollment request to backend
      print("📤 Sending enrollment request to backend...");
      final result = await userService.enrollUser(
        name: _nameController.text.trim(),
        employeeId: "",  // Empty = auto-generate
        accessLevel: 'employee',
        imageFile: file,
      );

      // Step 6: Handle backend response
      if (result["success"] == true) {
        // Success: User enrolled successfully
        print("✅ Enrollment successful!");
        
        // Extract user ID from response
        final userData = result["data"];
        final userId = userData["employee_id"] ?? "N/A";
        print("📋 Generated User ID: $userId");
        
        // Store user ID for display
        setState(() {
          _enrolledUserId = userId;
        });

        // Show user ID in big text (auto-closes after 6 seconds)
        await _showUserIdDisplay(userId);

        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text("✅ Enrollment Successful! Your ID: $userId"),
            backgroundColor: Colors.green,
            duration: const Duration(seconds: 3),
          ),
        );

        // Reset form fields for next enrollment
        _nameController.clear();
        setState(() {
          _enrolledUserId = null;
        });
      } else {
        // Error: Enrollment failed
        print("❌ Enrollment failed: ${result["message"]}");

        // Extract error message
        String errorMessage = result["message"] ?? "Enrollment failed";

        // Handle different error types
        if (errorMessage.contains("already exists") || 
            errorMessage.contains("duplicate_name")) {
          errorMessage = "⚠️ Name already exists!\n"
              "Please use a different name.";
        } else if (errorMessage.contains("already registered") ||
            errorMessage.contains("duplicate")) {
          errorMessage = "⚠️ This face is already registered!\n"
              "Please use a different face or contact admin.";
        }

        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(errorMessage),
            backgroundColor: Colors.red,
            duration: const Duration(seconds: 4),
          ),
        );
      }
    } catch (e) {
      // Handle unexpected errors
      print("❌ Enrollment Error: $e");

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text("Error: $e"),
          backgroundColor: Colors.red,
          duration: const Duration(seconds: 3),
        ),
      );
    } finally {
      // Reset loading state
      setState(() {
        _isEnrolling = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      // App bar with title
      appBar: AppBar(
        title: const Text("Face Enrollment"),
        elevation: 0,
      ),

      // Main body
      body: FutureBuilder(
        future: _initializeControllerFuture,
        builder: (context, snapshot) {
          // Camera initialized successfully
          if (snapshot.connectionState == ConnectionState.done) {
            return SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    // =====================================================
                    // CAMERA PREVIEW SECTION
                    // =====================================================
                    Container(
                      decoration: BoxDecoration(
                        border: Border.all(
                          color: Colors.blue,
                          width: 2,
                        ),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(6),
                        child: SizedBox(
                          height: 300,
                          child: CameraPreview(_controller),
                        ),
                      ),
                    ),

                    const SizedBox(height: 20),

                    // =====================================================
                    // USER INPUT SECTION
                    // =====================================================

                    // Full Name input field
                    TextFormField(
                      controller: _nameController,
                      decoration: InputDecoration(
                        labelText: "Full Name",
                        hintText: "Enter your full name",
                        prefixIcon: const Icon(Icons.person),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(8),
                        ),
                      ),
                      validator: (value) {
                        if (value == null || value.isEmpty) {
                          return "Name is required";
                        }
                        if (value.length < 2) {
                          return "Name must be at least 2 characters";
                        }
                        return null;
                      },
                    ),

                    const SizedBox(height: 30),

                    // =====================================================
                    // ACTION BUTTON SECTION
                    // =====================================================

                    ElevatedButton.icon(
                      onPressed:
                          _isEnrolling ? null : () => _takePictureAndEnroll(),
                      icon: _isEnrolling
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
                          : const Icon(Icons.camera_alt),
                      label: Text(
                        _isEnrolling
                            ? "Processing..."
                            : "Take Picture & Enroll",
                        style: const TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      style: ElevatedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 16),
                        backgroundColor: Colors.blue,
                        foregroundColor: Colors.white,
                        disabledBackgroundColor: Colors.grey,
                      ),
                    ),

                    const SizedBox(height: 16),

                    // =====================================================
                    // INSTRUCTIONS SECTION
                    // =====================================================

                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.blue.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(
                          color: Colors.blue.withOpacity(0.3),
                        ),
                      ),
                      child: const Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            "📋 Instructions:",
                            style: TextStyle(
                              fontWeight: FontWeight.bold,
                              fontSize: 14,
                            ),
                          ),
                          SizedBox(height: 8),
                          Text(
                            "1. Enter your full name\n"
                            "2. Position your face in the camera\n"
                            "3. Click 'Take Picture & Enroll'\n"
                            "4. Review the image preview\n"
                            "5. Click 'Confirm & Enroll' to proceed\n"
                            "6. Your unique 4-digit User ID will be displayed\n"
                            "7. Save your User ID for future reference",
                            style: TextStyle(
                              fontSize: 12,
                              color: Colors.grey,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            );
          }

          // Camera still initializing
          return const Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                CircularProgressIndicator(),
                SizedBox(height: 16),
                Text("Initializing camera..."),
              ],
            ),
          );
        },
      ),
    );
  }
}
