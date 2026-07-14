import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';

/// Base URL for auth endpoints — mirrors the pattern used in api_service.dart.
const String _kWebAuthBaseUrl = 'http://127.0.0.1:8000';
const String _kAndroidAuthBaseUrl = 'http://10.0.2.2:8000';

String get _authBaseUrl {
  if (kIsWeb) return _kWebAuthBaseUrl;
  return _kAndroidAuthBaseUrl;
}

/// Authentication service for managing Google Workspace OAuth connection.
///
/// The auth flow is entirely backend-driven:
///   1. Flutter opens /auth/google/login in the system browser via url_launcher.
///   2. Backend redirects → Google consent screen → stores tokens on callback.
///   3. Flutter calls /auth/google/status to confirm the connection is live.
class AuthService {
  // ── Google OAuth ──────────────────────────────────────────────────────────

  /// Open the Google OAuth consent screen in the system browser.
  ///
  /// The backend handles the full redirect + token exchange flow.
  /// After the browser shows the success page, the user switches back
  /// to the app and taps "Check Status" to confirm connection.
  Future<bool> launchGoogleLogin() async {
    final uri = Uri.parse('$_authBaseUrl/auth/google/login');
    try {
      final launched = await launchUrl(
        uri,
        mode: LaunchMode.externalApplication,
      );
      return launched;
    } catch (e) {
      debugPrint('AuthService: failed to launch Google login — $e');
      return false;
    }
  }

  /// Fetch the current Google connection status from the backend.
  ///
  /// Returns a [GoogleAuthStatus] describing whether tokens are stored
  /// and which scopes were granted.
  Future<GoogleAuthStatus> getGoogleStatus() async {
    try {
      final uri = Uri.parse('$_authBaseUrl/auth/google/status');
      final response = await http
          .get(uri)
          .timeout(const Duration(seconds: 8));

      if (response.statusCode == 200) {
        final body = jsonDecode(response.body) as Map<String, dynamic>;
        return GoogleAuthStatus(
          connected: body['connected'] as bool? ?? false,
          scopes: List<String>.from(body['scopes'] as List? ?? []),
        );
      }
      return const GoogleAuthStatus(connected: false);
    } catch (e) {
      debugPrint('AuthService: failed to fetch Google status — $e');
      return const GoogleAuthStatus(connected: false, error: true);
    }
  }

  /// Disconnect Google by clearing stored tokens from the backend.
  Future<bool> disconnectGoogle() async {
    try {
      final uri = Uri.parse('$_authBaseUrl/auth/google/disconnect');
      final response = await http
          .get(uri)
          .timeout(const Duration(seconds: 8));
      return response.statusCode == 200;
    } catch (e) {
      debugPrint('AuthService: failed to disconnect Google — $e');
      return false;
    }
  }
}

/// Immutable snapshot of the Google OAuth connection state.
class GoogleAuthStatus {
  final bool connected;
  final List<String> scopes;
  final bool error; // True when the status check itself failed (backend down, etc.)

  const GoogleAuthStatus({
    required this.connected,
    this.scopes = const [],
    this.error = false,
  });
}
