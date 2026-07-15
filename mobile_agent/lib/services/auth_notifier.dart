import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/auth_state.dart';
import 'auth_service.dart';

/// Riverpod notifier that manages the Google OAuth authentication state.
///
/// Call [checkStatus] on app startup.
/// Call [loginWithGoogle] to initiate the OAuth browser flow.
/// Call [logout] to disconnect and return to [LoginView].
class AuthNotifier extends Notifier<AuthState> {
  late final AuthService _authService;

  @override
  AuthState build() {
    _authService = AuthService();
    // Kick off a status check as soon as the provider is first read.
    Future.microtask(checkStatus);
    return const AuthState(status: AuthStatus.checking);
  }

  // ── Public actions ──────────────────────────────────────────────────────────

  /// Check whether Google tokens are already stored in the backend.
  /// Called on startup and after returning from the browser OAuth flow.
  Future<void> checkStatus() async {
    state = state.copyWith(isLoading: true, clearError: true);
    final status = await _authService.getGoogleStatus();

    if (status.connected) {
      state = state.copyWith(
        status: AuthStatus.authenticated,
        email: status.email,
        isLoading: false,
      );
    } else {
      state = state.copyWith(
        status: AuthStatus.unauthenticated,
        email: '',
        isLoading: false,
        errorMessage: status.error ? 'Could not reach backend.' : null,
      );
    }
  }

  /// Open the Google OAuth consent screen in the system browser.
  Future<void> loginWithGoogle() async {
    state = state.copyWith(isLoading: true, clearError: true);
    final launched = await _authService.launchGoogleLogin();
    state = state.copyWith(isLoading: false);
    if (!launched) {
      state = state.copyWith(
        errorMessage: 'Could not open browser. Is the backend running?',
      );
    }
  }

  /// Disconnect Google and return to the unauthenticated state.
  Future<void> logout() async {
    state = state.copyWith(isLoading: true, clearError: true);
    await _authService.disconnectGoogle();
    state = const AuthState(status: AuthStatus.unauthenticated);
  }
}

final authProvider = NotifierProvider<AuthNotifier, AuthState>(
  AuthNotifier.new,
);
