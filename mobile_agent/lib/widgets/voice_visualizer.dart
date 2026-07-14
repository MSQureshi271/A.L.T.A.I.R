import 'dart:math';
import 'package:flutter/material.dart';

class VoiceVisualizer extends StatefulWidget {
  final bool isRecording;

  const VoiceVisualizer({super.key, required this.isRecording});

  @override
  State<VoiceVisualizer> createState() => _VoiceVisualizerState();
}

class _VoiceVisualizerState extends State<VoiceVisualizer>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1000),
    );

    if (widget.isRecording) {
      _controller.repeat();
    }
  }

  @override
  void didUpdateWidget(covariant VoiceVisualizer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isRecording && !_controller.isAnimating) {
      _controller.repeat();
    } else if (!widget.isRecording && _controller.isAnimating) {
      _controller.stop();
    }
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
      builder: (context, child) {
        return CustomPaint(
          size: const Size(double.infinity, 100),
          painter: WaveformPainter(
            animationValue: _controller.value,
            isActive: widget.isRecording,
          ),
        );
      },
    );
  }
}

class WaveformPainter extends CustomPainter {
  final double animationValue;
  final bool isActive;

  WaveformPainter({required this.animationValue, required this.isActive});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3.5
      ..strokeCap = StrokeCap.round;

    final double centerY = size.height / 2;
    final int barCount = 25;
    final double spacing = size.width / (barCount + 1);

    for (int i = 0; i < barCount; i++) {
      final double x = spacing * (i + 1);
      
      // Calculate height based on index (bell curve distribution)
      final double distanceFromCenter = (i - barCount / 2).abs() / (barCount / 2);
      final double maxBarHeight = size.height * 0.8 * (1.0 - distanceFromCenter * 0.7);

      double barHeight = 8.0; // Default quiet height
      if (isActive) {
        // Create an oscillating motion using sine and the animation value
        final double phase = (i * 0.3) + (animationValue * 2 * pi);
        final double scale = 0.4 + 0.6 * sin(phase).abs();
        barHeight = maxBarHeight * scale;
      }

      // Modern Gradient Color transition (Violet to Cyan)
      final rect = Rect.fromLTRB(x - 2, centerY - barHeight / 2, x + 2, centerY + barHeight / 2);
      paint.shader = const LinearGradient(
        colors: [
          Color(0xFF7B2CBF), // Neon Violet
          Color(0xFF00B4D8), // Electric Cyan
        ],
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
      ).createShader(rect);

      canvas.drawLine(
        Offset(x, centerY - barHeight / 2),
        Offset(x, centerY + barHeight / 2),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant WaveformPainter oldDelegate) {
    return oldDelegate.animationValue != animationValue || oldDelegate.isActive != isActive;
  }
}
