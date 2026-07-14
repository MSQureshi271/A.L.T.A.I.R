import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'views/voice_home_view.dart';

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
          primary: Color(0xFF7B2CBF),       // Neon Violet
          secondary: Color(0xFF00B4D8),     // Electric Cyan
          surface: Color(0xFF1E1E24),       // Sleek Slate
          error: Color(0xFFE63946),         // Vibrant Red
        ),
        useMaterial3: true,
      ),
      home: const VoiceHomeView(),
    );
  }
}
