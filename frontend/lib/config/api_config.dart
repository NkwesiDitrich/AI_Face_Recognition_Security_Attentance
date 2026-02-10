/// API base URL for backend. Set at build time:
///   flutter run --dart-define=API_BASE_URL=https://your-api.onrender.com
///   flutter build apk --dart-define=API_BASE_URL=https://your-api.onrender.com
///
/// Default: local dev (emulator: 10.0.2.2, device: 192.168.100.58)
const String apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://192.168.100.58:8000',
);

/// WebSocket uses same host, ws:// or wss:// based on http/https
String get wsBaseUrl {
  if (apiBaseUrl.startsWith('https://')) {
    return apiBaseUrl.replaceFirst('https://', 'wss://');
  }
  return apiBaseUrl.replaceFirst('http://', 'ws://');
}
