import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'models/auth_state.dart';
import 'services/auth_notifier.dart';
import 'views/voice_home_view.dart';
import 'views/login_view.dart';

void main() {
  runApp(
    const ProviderScope(
      child: MyApp(),
    ),
  );
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Executive Agent',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        brightness: Brightness.dark,
        scaffoldBackgroundColor: const Color(0xFF0F0F12),
        colorScheme: const ColorScheme.dark(
          primary: Color(0xFF7B2CBF),
          secondary: Color(0xFF00B4D8),
          surface: Color(0xFF1E1E24),
          error: Color(0xFFE63946),
        ),
        useMaterial3: true,
      ),
      home: const _AuthGate(),
    );
  }
}

/// Watches [authProvider] and routes to the correct screen reactively.
///
///   checking       → SplashScreen (brief spinner)
///   unauthenticated → LoginView
///   authenticated  → VoiceHomeView
class _AuthGate extends ConsumerWidget {
  const _AuthGate();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authProvider);

    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 350),
      child: switch (authState.status) {
        AuthStatus.checking => const _SplashScreen(),
        AuthStatus.unauthenticated => const LoginView(),
        AuthStatus.authenticated => const VoiceHomeView(),
      },
    );
  }
}

class _SplashScreen extends StatelessWidget {
  const _SplashScreen();

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      backgroundColor: Color(0xFF0F0F12),
      body: Center(
        child: CircularProgressIndicator(
          valueColor: AlwaysStoppedAnimation<Color>(Color(0xFF7B2CBF)),
        ),
      ),
    );
  }
}
