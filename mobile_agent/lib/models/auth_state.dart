/// Represents the user's authentication state in the app.
enum AuthStatus {
  /// Initial state while we check whether tokens are already stored.
  checking,

  /// No valid Google connection — show LoginView.
  unauthenticated,

  /// Google is connected — show the main app.
  authenticated,
}

/// Immutable snapshot of the auth state exposed by [AuthNotifier].
class AuthState {
  final AuthStatus status;

  /// The connected Google account email (empty string if unauthenticated).
  final String email;

  /// True when a connect/disconnect operation is in progress.
  final bool isLoading;

  /// Non-null when the last operation produced an error.
  final String? errorMessage;

  const AuthState({
    this.status = AuthStatus.checking,
    this.email = '',
    this.isLoading = false,
    this.errorMessage,
  });

  AuthState copyWith({
    AuthStatus? status,
    String? email,
    bool? isLoading,
    String? errorMessage,
    bool clearError = false,
  }) {
    return AuthState(
      status: status ?? this.status,
      email: email ?? this.email,
      isLoading: isLoading ?? this.isLoading,
      errorMessage: clearError ? null : (errorMessage ?? this.errorMessage),
    );
  }
}
