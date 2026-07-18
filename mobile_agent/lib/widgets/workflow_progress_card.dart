import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Renders a dynamic, premium multi-step progress stepper card in the conversation feed.
/// Tracks step statuses (pending, running, completed, failed) in real-time.
class WorkflowProgressCard extends StatefulWidget {
  final Map<String, dynamic> plan;

  const WorkflowProgressCard({super.key, required this.plan});

  @override
  State<WorkflowProgressCard> createState() => _WorkflowProgressCardState();
}

class _WorkflowProgressCardState extends State<WorkflowProgressCard>
    with SingleTickerProviderStateMixin {
  late AnimationController _pulseController;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final intentSummary = widget.plan['intent_summary'] as String? ?? '';
    final steps = (widget.plan['steps'] as List<dynamic>? ?? [])
        .map((s) => Map<String, dynamic>.from(s as Map))
        .toList();

    if (steps.isEmpty && intentSummary.isEmpty) return const SizedBox.shrink();

    // Count statistics
    final completedCount = steps.where((s) => s['status'] == 'completed').length;
    final totalCount = steps.length;
    final isDone = completedCount == totalCount;

    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(left: 12, right: 48, bottom: 12),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: const Color(0xFF14142B),
          borderRadius: const BorderRadius.only(
            topLeft: Radius.circular(4),
            topRight: Radius.circular(20),
            bottomLeft: Radius.circular(20),
            bottomRight: Radius.circular(20),
          ),
          border: Border.all(
            color: isDone
                ? const Color(0xFF38B000).withOpacity(0.35)
                : const Color(0xFF7B2CBF).withOpacity(0.4),
            width: 1.5,
          ),
          boxShadow: [
            BoxShadow(
              color: isDone
                  ? const Color(0xFF38B000).withOpacity(0.05)
                  : const Color(0xFF7B2CBF).withOpacity(0.1),
              blurRadius: 20,
              spreadRadius: 2,
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // ── Stepper Header ────────────────────────────────────────────────
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(6),
                      decoration: BoxDecoration(
                        color: const Color(0xFF7B2CBF).withOpacity(0.15),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: const Icon(
                        Icons.insights_rounded,
                        color: Color(0xFF9D4EDD),
                        size: 16,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      'WORKFLOW STATUS',
                      style: GoogleFonts.outfit(
                        color: const Color(0xFF9D4EDD),
                        fontSize: 12,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 1.5,
                      ),
                    ),
                  ],
                ),
                // Progress stats badge
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: isDone
                        ? const Color(0xFF38B000).withOpacity(0.15)
                        : const Color(0xFF7B2CBF).withOpacity(0.15),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    '$completedCount / $totalCount Completed',
                    style: GoogleFonts.outfit(
                      color: isDone ? const Color(0xFF38B000) : const Color(0xFFE0AAFF),
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ],
            ),

            if (intentSummary.isNotEmpty) ...[
              const SizedBox(height: 10),
              Text(
                intentSummary,
                style: GoogleFonts.outfit(
                  color: Colors.white,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],

            const SizedBox(height: 14),
            const Divider(color: Colors.white10, height: 1),
            const SizedBox(height: 14),

            // ── Vertical list of steps ───────────────────────────────────────
            ...steps.asMap().entries.map((entry) {
              final idx = entry.key;
              final step = entry.value;
              final isLast = idx == steps.length - 1;
              return _WorkflowStepRow(
                step: step,
                index: idx,
                isLast: isLast,
                pulseAnimation: _pulseController,
              );
            }),
          ],
        ),
      ),
    );
  }
}

// ── Step Row Widget ─────────────────────────────────────────────────────────

class _WorkflowStepRow extends StatelessWidget {
  final Map<String, dynamic> step;
  final int index;
  final bool isLast;
  final Animation<double> pulseAnimation;

  const _WorkflowStepRow({
    required this.step,
    required this.index,
    required this.isLast,
    required this.pulseAnimation,
  });

  static const _toolIcons = <String, IconData>{
    'gmail': Icons.email_rounded,
    'calendar': Icons.calendar_month_rounded,
    'search': Icons.search_rounded,
    'memory': Icons.psychology_rounded,
    'none': Icons.help_outline_rounded,
  };

  static const _toolColors = <String, Color>{
    'gmail': Color(0xFF00B4D8),
    'calendar': Color(0xFF38B000),
    'search': Color(0xFFFFB703),
    'memory': Color(0xFFFF70A6),
    'none': Color(0xFF6C757D),
  };

  @override
  Widget build(BuildContext context) {
    final tool = step['tool'] as String? ?? 'none';
    final action = step['action'] as String? ?? '';
    final description = step['description'] as String? ?? action;
    final status = step['status'] as String? ?? 'pending';
    final requiresConfirmation = step['requires_confirmation'] as bool? ?? true;

    final toolColor = _toolColors[tool] ?? const Color(0xFF6C757D);
    final toolIcon = _toolIcons[tool] ?? Icons.device_unknown_rounded;

    // Determine status design elements
    Color statusColor;
    Widget statusIndicator;

    switch (status) {
      case 'completed':
        statusColor = const Color(0xFF38B000);
        statusIndicator = const Icon(
          Icons.check_circle_rounded,
          color: Color(0xFF38B000),
          size: 18,
        );
        break;

      case 'failed':
        statusColor = const Color(0xFFD90429);
        statusIndicator = const Icon(
          Icons.cancel_rounded,
          color: Color(0xFFD90429),
          size: 18,
        );
        break;

      case 'running':
        statusColor = requiresConfirmation
            ? const Color(0xFFFFB703)
            : const Color(0xFF9D4EDD);
        
        statusIndicator = AnimatedBuilder(
          animation: pulseAnimation,
          builder: (context, child) {
            return Transform.scale(
              scale: 1.0 + (pulseAnimation.value * 0.12),
              child: Container(
                width: 18,
                height: 18,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: statusColor.withOpacity(0.2),
                  border: Border.all(
                    color: statusColor,
                    width: 2,
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: statusColor.withOpacity(0.3 * pulseAnimation.value),
                      blurRadius: 8,
                      spreadRadius: 1,
                    )
                  ],
                ),
                child: Center(
                  child: requiresConfirmation
                      ? Icon(Icons.lock_clock_rounded, size: 10, color: statusColor)
                      : SizedBox(
                          width: 8,
                          height: 8,
                          child: CircularProgressIndicator(
                            strokeWidth: 1.5,
                            color: statusColor,
                          ),
                        ),
                ),
              ),
            );
          },
        );
        break;

      case 'pending':
      default:
        statusColor = Colors.white24;
        statusIndicator = Container(
          width: 16,
          height: 16,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(color: Colors.white24, width: 2),
            color: Colors.transparent,
          ),
          child: Center(
            child: Text(
              '${index + 1}',
              style: GoogleFonts.outfit(
                color: Colors.white30,
                fontSize: 8,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        );
        break;
    }

    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ── Timeline bullet and vertical line ──────────────────────────────
          Column(
            children: [
              statusIndicator,
              if (!isLast)
                Expanded(
                  child: Container(
                    width: 2,
                    margin: const EdgeInsets.symmetric(vertical: 4),
                    color: status == 'completed'
                        ? const Color(0xFF38B000).withOpacity(0.4)
                        : Colors.white10,
                  ),
                ),
            ],
          ),
          const SizedBox(width: 12),

          // ── Step information ────────────────────────────────────────────────
          Expanded(
            child: Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(toolIcon, color: toolColor.withOpacity(0.85), size: 13),
                      const SizedBox(width: 5),
                      Text(
                        description,
                        style: GoogleFonts.outfit(
                          color: status == 'pending'
                              ? Colors.white38
                              : (status == 'completed' ? Colors.white70 : Colors.white),
                          fontSize: 12,
                          fontWeight: status == 'running'
                              ? FontWeight.bold
                              : FontWeight.w500,
                          decoration: status == 'completed'
                              ? TextDecoration.lineThrough
                              : null,
                        ),
                      ),
                      const SizedBox(width: 6),
                      if (status == 'running' && requiresConfirmation)
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                          decoration: BoxDecoration(
                            color: const Color(0xFFFFB703).withOpacity(0.15),
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text(
                            'AWAITING APPROVAL',
                            style: GoogleFonts.outfit(
                              color: const Color(0xFFFFB703),
                              fontSize: 8,
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                        ),
                    ],
                  ),
                  if (status == 'completed' && step['output'] != null) ...[
                    const SizedBox(height: 3),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(0.02),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text(
                        step['output'].toString(),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: GoogleFonts.outfit(
                          color: Colors.white54,
                          fontSize: 10,
                          fontStyle: FontStyle.italic,
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
