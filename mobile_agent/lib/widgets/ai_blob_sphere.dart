// ai_blob_sphere.dart
//
// A morphing, glowing "AI orb" widget — the kind of animated sphere used
// in voice-assistant / AI chat UIs to signal "I'm alive and listening."
//
// Usage:
//   AiBlobSphere(
//     size: 220,
//     amplitude: 1.0,      // 0.0 = idle/calm, 1.0 = fully active (e.g. speaking)
//     colors: [Color(0xFF6C5CE7), Color(0xFF00CEC9), Color(0xFFFF6B9D)],
//   )
//
// Drop this file into your project and import it. No external packages
// required — pure Flutter (dart:ui, CustomPainter, AnimationController).

import 'dart:math' as math;
import 'dart:ui' as ui;
import 'package:flutter/material.dart';

class AiBlobSphere extends StatefulWidget {
  /// Overall widget size (width & height).
  final double size;

  /// 0.0 = calm idle motion, 1.0 = energetic (e.g. AI is "speaking").
  /// Feed this from audio amplitude / TTS playback / thinking state.
  final double amplitude;

  /// Gradient colors used for the glow + fill. 2–4 colors work best.
  final List<Color> colors;

  /// How fast the blob morphs. 1.0 = default speed.
  final double speed;

  const AiBlobSphere({
    super.key,
    this.size = 200,
    this.amplitude = 0.4,
    this.colors = const [
      Color(0xFF7F5AF0),
      Color(0xFF2CB1FF),
      Color(0xFFFF5AA6),
    ],
    this.speed = 1.0,
  });

  @override
  State<AiBlobSphere> createState() => _AiBlobSphereState();
}

class _AiBlobSphereState extends State<AiBlobSphere>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 8),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        final t = _controller.value * 2 * math.pi * widget.speed;
        return SizedBox(
          width: widget.size,
          height: widget.size,
          child: CustomPaint(
            painter: _BlobPainter(
              time: t,
              amplitude: widget.amplitude.clamp(0.0, 1.0),
              colors: widget.colors,
            ),
          ),
        );
      },
    );
  }
}

class _BlobPainter extends CustomPainter {
  final double time;
  final double amplitude;
  final List<Color> colors;

  _BlobPainter({
    required this.time,
    required this.amplitude,
    required this.colors,
  });

  /// Builds an organic, wobbling blob outline as a smooth closed path.
  Path _buildBlobPath(Offset center, double baseRadius, double time,
      double amplitude, {int points = 10}) {
    final path = Path();
    final angleStep = (2 * math.pi) / points;
    final List<Offset> vertices = [];

    for (int i = 0; i < points; i++) {
      final angle = i * angleStep;

      // Layer several sine waves at different frequencies/phases so the
      // deformation looks organic instead of a simple pulsing circle.
      final noise = math.sin(angle * 3 + time) * 0.06 +
          math.sin(angle * 5 - time * 1.3) * 0.04 +
          math.sin(angle * 2 + time * 0.7) * 0.05;

      final radius = baseRadius * (1 + noise * (0.4 + amplitude));
      vertices.add(Offset(
        center.dx + radius * math.cos(angle),
        center.dy + radius * math.sin(angle),
      ));
    }

    // Smooth the polygon into curves using Catmull-Rom-ish midpoint
    // interpolation, so edges look fluid rather than faceted.
    path.moveTo(
      (vertices[0].dx + vertices[1].dx) / 2,
      (vertices[0].dy + vertices[1].dy) / 2,
    );
    for (int i = 0; i < points; i++) {
      final current = vertices[i];
      final next = vertices[(i + 1) % points];
      final mid = Offset(
        (current.dx + next.dx) / 2,
        (current.dy + next.dy) / 2,
      );
      path.quadraticBezierTo(current.dx, current.dy, mid.dx, mid.dy);
    }
    path.close();
    return path;
  }

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final baseRadius = size.width * 0.30;

    // --- 1. Soft outer glow (large blurred, low-opacity blob) ---
    final glowPath = _buildBlobPath(center, baseRadius * 1.35, time * 0.8,
        amplitude, points: 8);
    final glowPaint = Paint()
      ..shader = ui.Gradient.radial(
        center,
        baseRadius * 1.6,
        colors.map((c) => c.withOpacity(0.35)).toList(),
      )
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 40);
    canvas.drawPath(glowPath, glowPaint);

    // --- 2. Mid glow layer (tighter, brighter) ---
    final midPath = _buildBlobPath(
        center, baseRadius * 1.05, time * 1.1, amplitude, points: 9);
    final midPaint = Paint()
      ..shader = ui.Gradient.radial(
        center,
        baseRadius * 1.2,
        colors.map((c) => c.withOpacity(0.55)).toList(),
      )
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 18);
    canvas.drawPath(midPath, midPaint);

    // --- 3. Core blob (crisp-ish, fully opaque gradient fill) ---
    final corePath =
        _buildBlobPath(center, baseRadius, time, amplitude, points: 11);
    final corePaint = Paint()
      ..shader = ui.Gradient.linear(
        center.translate(-baseRadius, -baseRadius),
        center.translate(baseRadius, baseRadius),
        colors,
      );
    canvas.drawPath(corePath, corePaint);

    // --- 4. A subtle bright "highlight" for a glassy, alive feel ---
    final highlightPaint = Paint()
      ..shader = ui.Gradient.radial(
        center.translate(-baseRadius * 0.3, -baseRadius * 0.35),
        baseRadius * 0.6,
        [Colors.white.withOpacity(0.35), Colors.white.withOpacity(0.0)],
      );
    canvas.drawCircle(
      center.translate(-baseRadius * 0.25, -baseRadius * 0.3),
      baseRadius * 0.45,
      highlightPaint,
    );
  }

  @override
  bool shouldRepaint(covariant _BlobPainter oldDelegate) => true;
}
