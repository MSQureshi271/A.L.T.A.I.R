import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/auth_notifier.dart';

/// Full-screen landing page shown to unauthenticated users.
///
/// Flow:
///   1. Tap "Sign in with Google" → opens browser OAuth consent screen.
///   2. User completes sign-in in browser.
///   3. Tap "I've signed in → Continue" → app re-checks backend status.
///   4. On success → main.dart navigator switches to VoiceHomeView.
class LoginView extends ConsumerStatefulWidget {
  const LoginView({super.key});

  @override
  ConsumerState<LoginView> createState() => _LoginViewState();
}

class _LoginViewState extends ConsumerState<LoginView>
    with SingleTickerProviderStateMixin {
  bool _waitingForCallback = false;
  late final AnimationController _pulseCtrl;
  late final Animation<double> _pulseAnim;

  @override
  void initState() {
    super.initState();
    _pulseCtrl = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat(reverse: true);
    _pulseAnim = Tween<double>(begin: 0.85, end: 1.0).animate(
      CurvedAnimation(parent: _pulseCtrl, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _pulseCtrl.dispose();
    super.dispose();
  }

  Future<void> _handleSignIn() async {
    await ref.read(authProvider.notifier).loginWithGoogle();
    if (mounted) setState(() => _waitingForCallback = true);
  }

  Future<void> _handleContinue() async {
    await ref.read(authProvider.notifier).checkStatus();
    // Navigation is handled reactively by main.dart watching authProvider
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authProvider);
    final isLoading = authState.isLoading;

    return Scaffold(
      backgroundColor: const Color(0xFF0F0F12),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 32),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                // ── Logo ───────────────────────────────────────────────────
                ScaleTransition(
                  scale: _pulseAnim,
                  child: Container(
                    width: 100,
                    height: 100,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      gradient: const LinearGradient(
                        colors: [Color(0xFF7B2CBF), Color(0xFF3A0CA3)],
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: const Color(0xFF7B2CBF).withOpacity(0.5),
                          blurRadius: 40,
                          spreadRadius: 8,
                        ),
                      ],
                    ),
                    child: const Icon(
                      Icons.account_balance_wallet_rounded,
                      color: Colors.white,
                      size: 48,
                    ),
                  ),
                ),
                const SizedBox(height: 32),

                // ── Title ──────────────────────────────────────────────────
                Text(
                  'EXECUTIVE AGENT',
                  style: GoogleFonts.outfit(
                    color: const Color(0xFFF8F9FA),
                    fontSize: 26,
                    fontWeight: FontWeight.w900,
                    letterSpacing: 3,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  'Your AI-powered business assistant',
                  style: GoogleFonts.outfit(
                    color: const Color(0xFFADB5BD),
                    fontSize: 14,
                  ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 56),

                // ── Error banner ───────────────────────────────────────────
                if (authState.errorMessage != null) ...[
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: const Color(0xFFE63946).withOpacity(0.15),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(
                        color: const Color(0xFFE63946).withOpacity(0.4),
                      ),
                    ),
                    child: Row(
                      children: [
                        const Icon(Icons.error_outline,
                            color: Color(0xFFE63946), size: 18),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            authState.errorMessage!,
                            style: GoogleFonts.outfit(
                              color: const Color(0xFFE63946),
                              fontSize: 13,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 20),
                ],

                // ── Primary CTA ────────────────────────────────────────────
                if (!_waitingForCallback) ...[
                  _GoogleSignInButton(
                    onTap: isLoading ? null : _handleSignIn,
                    isLoading: isLoading,
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'Connect your Google Workspace to get started.',
                    style: GoogleFonts.outfit(
                      color: const Color(0xFF6C757D),
                      fontSize: 12,
                    ),
                    textAlign: TextAlign.center,
                  ),
                ] else ...[
                  // ── Waiting for OAuth callback ──────────────────────────
                  Container(
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      color: const Color(0xFF1E1E24),
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(
                        color: Colors.white.withOpacity(0.08),
                      ),
                    ),
                    child: Column(
                      children: [
                        const Icon(
                          Icons.open_in_browser_rounded,
                          color: Color(0xFF7B2CBF),
                          size: 32,
                        ),
                        const SizedBox(height: 12),
                        Text(
                          'Complete sign-in in your browser',
                          style: GoogleFonts.outfit(
                            color: const Color(0xFFF8F9FA),
                            fontSize: 15,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          'After Google redirects you back, tap the button below.',
                          style: GoogleFonts.outfit(
                            color: const Color(0xFFADB5BD),
                            fontSize: 13,
                          ),
                          textAlign: TextAlign.center,
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 20),
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton(
                      onPressed: isLoading ? null : _handleContinue,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF38B000),
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 16),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(14),
                        ),
                      ),
                      child: isLoading
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                valueColor: AlwaysStoppedAnimation<Color>(
                                    Colors.white),
                              ),
                            )
                          : Text(
                              "I've signed in — Continue",
                              style: GoogleFonts.outfit(
                                fontSize: 15,
                                fontWeight: FontWeight.w700,
                              ),
                            ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextButton(
                    onPressed: () =>
                        setState(() => _waitingForCallback = false),
                    child: Text(
                      'Go back',
                      style: GoogleFonts.outfit(
                        color: const Color(0xFF6C757D),
                        fontSize: 13,
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ── Google Sign-In button ────────────────────────────────────────────────────

class _GoogleSignInButton extends StatelessWidget {
  final VoidCallback? onTap;
  final bool isLoading;

  const _GoogleSignInButton({this.onTap, required this.isLoading});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedOpacity(
        opacity: onTap == null ? 0.5 : 1.0,
        duration: const Duration(milliseconds: 200),
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 20),
          decoration: BoxDecoration(
            color: const Color(0xFF1E1E24),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: Colors.white.withOpacity(0.12)),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(0.3),
                blurRadius: 12,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              if (isLoading) ...[
                const SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(
                    strokeWidth: 2,
                    valueColor: AlwaysStoppedAnimation<Color>(Color(0xFF7B2CBF)),
                  ),
                ),
              ] else ...[
                // Google "G" logo colours using a Text widget
                RichText(
                  text: const TextSpan(
                    children: [
                      TextSpan(text: 'G', style: TextStyle(color: Color(0xFF4285F4), fontSize: 22, fontWeight: FontWeight.bold)),
                      TextSpan(text: 'o', style: TextStyle(color: Color(0xFFEA4335), fontSize: 22, fontWeight: FontWeight.bold)),
                      TextSpan(text: 'o', style: TextStyle(color: Color(0xFFFBBC05), fontSize: 22, fontWeight: FontWeight.bold)),
                      TextSpan(text: 'g', style: TextStyle(color: Color(0xFF4285F4), fontSize: 22, fontWeight: FontWeight.bold)),
                      TextSpan(text: 'l', style: TextStyle(color: Color(0xFF34A853), fontSize: 22, fontWeight: FontWeight.bold)),
                      TextSpan(text: 'e', style: TextStyle(color: Color(0xFFEA4335), fontSize: 22, fontWeight: FontWeight.bold)),
                    ],
                  ),
                ),
              ],
              const SizedBox(width: 16),
              Text(
                'Sign in with Google',
                style: GoogleFonts.outfit(
                  color: const Color(0xFFF8F9FA),
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
