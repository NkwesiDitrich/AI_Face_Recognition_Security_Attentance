// frontend/lib/main.dart
import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:provider/provider.dart';
import 'package:ai_face_attendance_frontend/services/user_service.dart';
import 'package:ai_face_attendance_frontend/screens/enrollment_screen.dart';

// Global variable to store the list of available cameras
List<CameraDescription> cameras = [];

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  try {
    cameras = await availableCameras();
  } on CameraException catch (e) {
    print('Error in fetching the cameras: $e');
  }

  runApp(
    MultiProvider(
      providers: [
        Provider(create: (_) => UserService()),
      ],
      child: const MyApp(),
    ),
  );
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AI Face Attendance',
      theme: ThemeData(primarySwatch: Colors.blue),
      home: EnrollmentScreen(cameras: cameras),
    );
  }
}
