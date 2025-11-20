import 'dart:io';
import 'dart:convert';
import 'package:http/http.dart' as http;

class UserService {
  static const String baseUrl = 'http://10.0.2.2:8000/api/v1';

  Future<Map<String, dynamic>> enrollUser({
    required String name,
    required String employeeId,
    required String accessLevel,
    required File imageFile,
  }) async {
    try {
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

      var response = await request.send();
      var responseBytes = await response.stream.toBytes();
      var responseString = utf8.decode(responseBytes);

      if (response.statusCode == 201) {
        return {
          'success': true,
          'message': 'User enrolled successfully',
          'data': jsonDecode(responseString),
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

  Future<Map<String, dynamic>> searchUser({
    required File imageFile,
  }) async {
    try {
      var request = http.MultipartRequest(
        'POST',
        Uri.parse('$baseUrl/search'),
      );

      request.headers['Accept'] = 'application/json';

      request.files.add(
        await http.MultipartFile.fromPath('file', imageFile.path),
      );

      var response = await request.send();
      var responseBytes = await response.stream.toBytes();
      var responseString = utf8.decode(responseBytes);

      if (response.statusCode == 200) {
        return {
          'success': true,
          'message': 'User found',
          'data': jsonDecode(responseString),
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
