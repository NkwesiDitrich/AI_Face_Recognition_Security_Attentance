import 'dart:io';
import 'dart:convert';
import 'package:http/http.dart' as http;

class UserService {
  /// ==========================================================================
  /// 🌐 NETWORK CONFIGURATION FOR REAL DEVICES
  /// ==========================================================================
  ///
  /// 1. EMULATOR: Use 'http://10.0.2.2:8000/api/v1'
  /// 2. REAL DEVICE: Use your computer's Local IP (e.g., 'http://192.168.1.5:8000/api/v1')
  ///
  /// IMPORTANT: Your phone and computer MUST be on the same Wi-Fi network.
  /// ==========================================================================

  // CHANGE THIS to your computer's IP address when testing on a real phone!
  static const String _serverIp = '192.168.11.202'; // Default for emulator
  static const String baseUrl = 'http://$_serverIp:8000/api/v1';

  /// ------------------------------
  /// ENROLL USER
  /// ------------------------------
  Future<Map<String, dynamic>> enrollUser({
    required String name,
    required String employeeId,
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
      request.fields['employee_id'] = employeeId;
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
        return {
          'success': false,
          'message': 'Duplicate: This face is already registered.',
          'data': jsonDecode(responseBody),
        };
      } else if (response.statusCode == 400) {
        return {
          'success': false,
          'message':
              'Face not detected. Please try again with a clearer photo.',
          'data': jsonDecode(responseBody),
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
