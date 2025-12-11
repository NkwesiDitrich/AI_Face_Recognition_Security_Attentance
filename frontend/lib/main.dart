// frontend/lib/main.dart

import 'package:flutter/material.dart';
import 'package:camera/camera.dart';
import 'package:provider/provider.dart';

// SERVICES
import 'package:ai_face_attendance_frontend/services/user_service.dart';

// SCREENS
import 'package:ai_face_attendance_frontend/screens/enrollment_screen.dart';
import 'package:ai_face_attendance_frontend/screens/attendance_screen.dart';

// Global camera list
List<CameraDescription> cameras = [];

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  try {
    cameras = await availableCameras();
  } catch (e) {
    print("Camera Error: $e");
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
      title: 'AI Face Attendance System',
      theme: ThemeData(primarySwatch: Colors.blue),
      home: HomeScreen(),
      debugShowCheckedModeBanner: false,
    );
  }
}

class HomeScreen extends StatelessWidget {
  HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("AI Face Attendance Home")),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            // Go to Enrollment Screen
            ElevatedButton(
              onPressed: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (_) => EnrollmentScreen(cameras: cameras),
                  ),
                );
              },
              child: const Text("Go to Face Enrollment"),
            ),

            const SizedBox(height: 20),

            // Go to Real-Time Attendance Screen
            ElevatedButton(
              onPressed: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (_) => AttendanceScreen(cameras: cameras),
                  ),
                );
              },
              child: const Text("Start Real-Time Attendance"),
            ),
          ],
        ),
      ),
    );
  }
}
