import 'dart:io';
import 'dart:convert';
import 'package:http/http.dart' as http;

import 'package:ai_face_attendance_frontend/config/api_config.dart';

class UserService {
  /// API base. Set via: flutter run --dart-define=API_BASE_URL=https://your-api.com
  static String get baseUrl => '${apiBaseUrl}/api/v1';

  /// ------------------------------
  /// ENROLL USER
  /// ------------------------------
  Future<Map<String, dynamic>> enrollUser({
    required String name,
    String employeeId = "", // Optional - will be auto-generated if empty
    required String accessLevel,
    required File imageFile,
  }) async {
    try {
      print("📸 Preparing enrollment request for $name...");

      var request = http.MultipartRequest(
        'POST',
        Uri.parse('$baseUrl/enroll'),
      );

      request.headers['Accept'] = 'application/json';

      request.fields['name'] = name;
      request.fields['employee_id'] =
          employeeId; // Empty string = auto-generate
      request.fields['access_level'] = accessLevel;

      request.files.add(
        await http.MultipartFile.fromPath('file', imageFile.path),
      );

      print("📤 Sending enrollment request to $baseUrl/enroll...");

      var streamedResponse = await request.send().timeout(
        const Duration(seconds: 60),
        onTimeout: () {
          throw Exception(
              "Request timed out. Check if your server is running and accessible at $baseUrl");
        },
      );

      var response = await http.Response.fromStream(streamedResponse);
      var responseBody = response.body;

      print("📥 Backend response: ${response.statusCode}");

      if (response.statusCode == 201) {
        return {
          'success': true,
          'message': 'User enrolled successfully',
          'data': jsonDecode(responseBody),
        };
      } else if (response.statusCode == 409) {
        // Handle duplicate name or duplicate face
        final errorData = jsonDecode(responseBody);
        final errorType = errorData['detail']?['error'] ?? '';
        String message = 'Duplicate detected.';

        if (errorType == 'duplicate_name') {
          message = errorData['detail']?['message'] ??
              'Name already exists. Please use a different name.';
        } else if (errorType == 'duplicate_face') {
          message = 'Face already registered.';
        }

        return {
          'success': false,
          'message': message,
          'data': errorData,
        };
      } else if (response.statusCode == 400) {
        final errorData = jsonDecode(responseBody);
        final errorDetail = errorData['detail'];
        String message =
            'Face not detected. Please try again with a clearer photo.';

        if (errorDetail is Map && errorDetail['message'] != null) {
          message = errorDetail['message'];
        }

        return {
          'success': false,
          'message': message,
          'data': errorData,
        };
      } else {
        return {
          'success': false,
          'message': 'Enrollment failed: ${response.statusCode}',
          'data': responseBody,
        };
      }
    } catch (e) {
      print("❌ Enrollment error: $e");
      return {
        'success': false,
        'message':
            'Network Error: $e. Ensure your phone and PC are on the same Wi-Fi.',
        'data': null,
      };
    }
  }

  /// ------------------------------
  /// SEARCH USER
  /// ------------------------------
  Future<Map<String, dynamic>> searchUser({
    required File imageFile,
  }) async {
    try {
      print("📸 Preparing search request...");

      var request = http.MultipartRequest(
        'POST',
        Uri.parse('$baseUrl/search'),
      );

      request.headers['Accept'] = 'application/json';

      request.files.add(
        await http.MultipartFile.fromPath('file', imageFile.path),
      );

      print("📤 Sending search request to $baseUrl/search...");

      var streamedResponse = await request.send().timeout(
        const Duration(seconds: 60),
        onTimeout: () {
          throw Exception(
              "Request timed out. Check if your server is running and accessible at $baseUrl");
        },
      );

      var response = await http.Response.fromStream(streamedResponse);
      var responseBody = response.body;

      print("📥 Backend response: ${response.statusCode}");

      if (response.statusCode == 200) {
        return {
          'success': true,
          'message': 'User found',
          'data': jsonDecode(responseBody),
        };
      } else if (response.statusCode == 404) {
        return {
          'success': false,
          'message': 'No matching user found',
          'data': null,
        };
      } else {
        return {
          'success': false,
          'message': 'Search failed: ${response.statusCode}',
          'data': responseBody,
        };
      }
    } catch (e) {
      print("❌ Search error: $e");
      return {
        'success': false,
        'message':
            'Network Error: $e. Ensure your phone and PC are on the same Wi-Fi.',
        'data': null,
      };
    }
  }
}
