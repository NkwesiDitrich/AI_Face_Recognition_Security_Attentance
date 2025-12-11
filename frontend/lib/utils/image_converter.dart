// frontend/lib/utils/image_converter.dart

import 'dart:typed_data';
import 'package:camera/camera.dart';
import 'package:image/image.dart' as img;

/// Converts a CameraImage (YUV420 format) to a JPEG byte array.
/// This is a complex operation required to send a standard image format
/// over the network to the Python backend.
Uint8List? convertYUV420toImage(CameraImage cameraImage) {
  final int width = cameraImage.width;
  final int height = cameraImage.height;

  // YUV420_888 format is common for Android/iOS cameras
  if (cameraImage.format.group != ImageFormatGroup.yuv420) {
    // Handle other formats if necessary, but YUV420 is standard for streaming
    return null;
  }

  // Get Y, U, and V planes
  final planeY = cameraImage.planes[0];
  final planeU = cameraImage.planes[1];
  final planeV = cameraImage.planes[2];

  // Create a new image object
  final image = img.Image(width: width, height: height);

  // Convert YUV to RGB
  for (int x = 0; x < width; x++) {
    for (int y = 0; y < height; y++) {
      // Y plane (Luminance)
      final int yIndex = y * planeY.bytesPerRow + x * planeY.bytesPerPixel!;
      final int Y = planeY.bytes[yIndex];

      // U and V planes (Chrominance) are subsampled (usually 4:2:0)
      // The U and V planes are half the width and half the height of the Y plane.
      // We need to account for the row stride and pixel stride.
      final int uvX = x ~/ 2;
      final int uvY = y ~/ 2;

      // U plane
      final int uIndex = uvY * planeU.bytesPerRow + uvX * planeU.bytesPerPixel!;
      final int U = planeU.bytes[uIndex] - 128;

      // V plane
      final int vIndex = uvY * planeV.bytesPerRow + uvX * planeV.bytesPerPixel!;
      final int V = planeV.bytes[vIndex] - 128;

      // YUV to RGB conversion matrix (simplified)
      int R = (Y + 1.402 * V).round().clamp(0, 255);
      int G = (Y - 0.344136 * U - 0.714136 * V).round().clamp(0, 255);
      int B = (Y + 1.772 * U).round().clamp(0, 255);

      // Set the pixel color in the image
      image.setPixelRgb(x, y, R, G, B);
    }
  }

  // Encode the image to JPEG format
  return Uint8List.fromList(img.encodeJpg(image, quality: 80));
}
