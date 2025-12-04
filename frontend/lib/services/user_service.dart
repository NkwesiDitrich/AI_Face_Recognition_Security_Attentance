import 'dart:io';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:image/image.dart' as img;

class UserService {
  static const String baseUrl = 'http://10.0.2.2:8000/api/v1';

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
      // 🔥 FIX: Rotate image if needed (camera orientation issue)
      print("📸 Processing image for enrollment...");

      var imageBytes = await imageFile.readAsBytes();
      var image = img.decodeImage(imageBytes);

      if (image != null) {
        // Rotate 90 degrees if needed (common on Android)
        image = img.copyRotate(image, angle: 90);

        // Save the corrected image with high quality
        var correctedImageBytes = img.encodeJpg(image, quality: 95);
        await imageFile.writeAsBytes(correctedImageBytes);

        print("✅ Image rotated and optimized for face detection");
      } else {
        print("⚠️ Could not decode image, proceeding with original");
      }

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

      print("📤 Sending enrollment request to backend...");

      // Add timeout
      var streamedResponse = await request.send().timeout(
        const Duration(seconds: 90),
        onTimeout: () {
          throw Exception("Request timed out while enrolling user.");
        },
      );

      var response = await http.Response.fromStream(streamedResponse);
      var responseBody = response.body;

      print("📥 Backend response: ${response.statusCode}");

      if (response.statusCode == 201) {
        print("✅ Enrollment successful!");
        return {
          'success': true,
          'message': 'User enrolled successfully',
          'data': jsonDecode(responseBody),
        };
      } else {
        print("❌ Enrollment failed: ${response.statusCode}");
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
        'message': 'Error: $e',
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
      // 🔥 FIX: Rotate image if needed (camera orientation issue)
      print("📸 Processing image for search...");

      var imageBytes = await imageFile.readAsBytes();
      var image = img.decodeImage(imageBytes);

      if (image != null) {
        // Rotate 90 degrees if needed (common on Android)
        image = img.copyRotate(image, angle: 90);

        // Save the corrected image with high quality
        var correctedImageBytes = img.encodeJpg(image, quality: 95);
        await imageFile.writeAsBytes(correctedImageBytes);

        print("✅ Image rotated and optimized for face detection");
      } else {
        print("⚠️ Could not decode image, proceeding with original");
      }

      var request = http.MultipartRequest(
        'POST',
        Uri.parse('$baseUrl/search'),
      );

      request.headers['Accept'] = 'application/json';

      request.files.add(
        await http.MultipartFile.fromPath('file', imageFile.path),
      );

      print("📤 Sending search request to backend...");

      // Add timeout
      var streamedResponse = await request.send().timeout(
        const Duration(seconds: 90),
        onTimeout: () {
          throw Exception("Request timed out while searching user.");
        },
      );

      var response = await http.Response.fromStream(streamedResponse);
      var responseBody = response.body;

      print("📥 Backend response: ${response.statusCode}");

      if (response.statusCode == 200) {
        print("✅ User found!");
        return {
          'success': true,
          'message': 'User found',
          'data': jsonDecode(responseBody),
        };
      } else if (response.statusCode == 404) {
        print("❌ No matching user found");
        return {
          'success': false,
          'message': 'No matching user found',
          'data': null,
        };
      } else {
        print("❌ Search failed: ${response.statusCode}");
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
        'message': 'Error: $e',
        'data': null,
      };
    }
  }
}
