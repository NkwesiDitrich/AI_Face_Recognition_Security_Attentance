import 'dart:io';
import 'package:http/http.dart' as http;

class UserService {
  // Backend API base URL - Change this to your backend server address
  static const String baseUrl = 'http://10.0.2.2:8000/api/v1';
  // For physical device, use: 'http://YOUR_BACKEND_IP:8000/api/v1'

  /// Enroll a new user with face recognition
  Future<Map<String, dynamic>> enrollUser({
    required String name,
    required String employeeId,
    required String accessLevel,
    required File imageFile,
  }) async {
    try {
      // Create multipart request
      var request = http.MultipartRequest(
        'POST',
        Uri.parse('$baseUrl/enroll'),
      );

      // Add form fields
      request.fields['name'] = name;
      request.fields['employee_id'] = employeeId;
      request.fields['access_level'] = accessLevel;

      // Add image file
      request.files.add(
        await http.MultipartFile.fromPath('file', imageFile.path),
      );

      // Send request
      var response = await request.send();
      var responseData = await response.stream.toBytes();
      var responseString = String.fromCharCodes(responseData);

      if (response.statusCode == 201) {
        return {
          'success': true,
          'message': 'User enrolled successfully',
          'data': responseString,
        };
      } else {
        return {
          'success': false,
          'message': 'Enrollment failed: ${response.statusCode}',
          'data': responseString,
        };
      }
    } catch (e) {
      return {
        'success': false,
        'message': 'Error: $e',
        'data': null,
      };
    }
  }

  /// Search for a user by face recognition
  Future<Map<String, dynamic>> searchUser({
    required File imageFile,
  }) async {
    try {
      // Create multipart request
      var request = http.MultipartRequest(
        'POST',
        Uri.parse('$baseUrl/search'),
      );

      // Add image file
      request.files.add(
        await http.MultipartFile.fromPath('file', imageFile.path),
      );

      // Send request
      var response = await request.send();
      var responseData = await response.stream.toBytes();
      var responseString = String.fromCharCodes(responseData);

      if (response.statusCode == 200) {
        return {
          'success': true,
          'message': 'User found',
          'data': responseString,
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
          'data': responseString,
        };
      }
    } catch (e) {
      return {
        'success': false,
        'message': 'Error: $e',
        'data': null,
      };
    }
  }
}
