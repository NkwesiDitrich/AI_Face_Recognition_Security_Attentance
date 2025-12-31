// frontend/lib/utils/image_converter.dart

import 'dart:typed_data';
import 'package:camera/camera.dart';
import 'package:image/image.dart' as img;

Uint8List? convertYUV420toImage(CameraImage cameraImage) {
  final int width = cameraImage.width;
  final int height = cameraImage.height;
  if (cameraImage.format.group != ImageFormatGroup.yuv420) return null;

  final planeY = cameraImage.planes[0];
  final planeU = cameraImage.planes[1];
  final planeV = cameraImage.planes[2];
  final image = img.Image(width: width, height: height);

  for (int x = 0; x < width; x++) {
    for (int y = 0; y < height; y++) {
      final int yIndex = y * planeY.bytesPerRow + x * planeY.bytesPerPixel!;
      final int Y = planeY.bytes[yIndex];
      final int uvX = x ~/ 2;
      final int uvY = y ~/ 2;
      final int uIndex = uvY * planeU.bytesPerRow + uvX * planeU.bytesPerPixel!;
      final int U = planeU.bytes[uIndex] - 128;
      final int vIndex = uvY * planeV.bytesPerRow + uvX * planeV.bytesPerPixel!;
      final int V = planeV.bytes[vIndex] - 128;

      int R = (Y + 1.402 * V).round().clamp(0, 255);
      int G = (Y - 0.344136 * U - 0.714136 * V).round().clamp(0, 255);
      int B = (Y + 1.772 * U).round().clamp(0, 255);
      image.setPixelRgb(x, y, R, G, B);
    }
  }
  // FIXED: Reduced quality to 75 for faster encoding
  return Uint8List.fromList(img.encodeJpg(image, quality: 75));
}
