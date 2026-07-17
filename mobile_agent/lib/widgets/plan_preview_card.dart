import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// Displays the structured task plan produced by the Planner Agent.
///
/// Shows the intent summary as a header, then each step as a labelled badge
/// with tool icon, description, and a confirmation indicator.
///
/// Rendered in the chat area immediately after the user's command bubble,
/// before execution results arrive.
class PlanPreviewCard extends StatelessWidget {
  /// The raw plan map from the backend `{"type": "plan", "plan": {...}}` event.
  final Map<String, dynamic> plan;

  const PlanPreviewCard({super.key, required this.plan});

  @override
  Widget build(BuildContext context) {
    final intentSummary = plan['intent_summary'] as String? ?? '';
    final steps = (plan['steps'] as List<dynamic>? ?? [])
        .map((s) => Map<String, dynamic>.from(s as Map))
        .toList();

    if (steps.isEmpty && intentSummary.isEmpty) return const SizedBox.shrink();

    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(left: 12, right: 48, bottom: 8),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: const Color(0xFF1A1A2E),
          borderRadius: const BorderRadius.only(
            topLeft: Radius.circular(4),
            topRight: Radius.circular(16),
            bottomLeft: Radius.circular(16),
            bottomRight: Radius.circular(16),
          ),
          border: Border.all(
            color: const Color(0xFF7B2CBF).withOpacity(0.35),
          ),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFF7B2CBF).withOpacity(0.08),
              blurRadius: 16,
              spreadRadius: 2,
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // ── Header ───────────────────────────────────────────────────────
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(5),
                  decoration: BoxDecoration(
                    color: const Color(0xFF7B2CBF).withOpacity(0.15),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: const Icon(
                    Icons.account_tree_rounded,
                    color: Color(0xFF7B2CBF),
                    size: 14,
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  'PLAN',
                  style: GoogleFonts.outfit(
                    color: const Color(0xFF7B2CBF),
                    fontSize: 11,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 1.5,
                  ),
                ),
              ],
            ),

            if (intentSummary.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                intentSummary,
                style: GoogleFonts.outfit(
                  color: const Color(0xFFADB5BD),
                  fontSize: 12,
                  fontStyle: FontStyle.italic,
                ),
              ),
            ],

            if (steps.isNotEmpty) ...[
              const SizedBox(height: 10),
              ...steps.asMap().entries.map((entry) {
                final i = entry.key;
                final step = entry.value;
                return _StepBadge(step: step, index: i);
              }),
            ],
          ],
        ),
      ),
    );
  }
}

// ── Step badge ───────────────────────────────────────────────────────────────

class _StepBadge extends StatelessWidget {
  final Map<String, dynamic> step;
  final int index;

  const _StepBadge({required this.step, required this.index});

  static const _toolIcons = <String, IconData>{
    'gmail': Icons.email_rounded,
    'calendar': Icons.calendar_month_rounded,
    'search': Icons.search_rounded,
    'none': Icons.help_outline_rounded,
  };

  static const _toolColors = <String, Color>{
    'gmail': Color(0xFF00B4D8),
    'calendar': Color(0xFF38B000),
    'search': Color(0xFFFFB703),
    'none': Color(0xFF6C757D),
  };

  static const _actionLabels = <String, String>{
    'read_emails': 'Read emails',
    'draft_email': 'Draft email',
    'get_events': 'Get events',
    'create_event': 'Create event',
    'search_web': 'Search web',
    'clarify': 'Clarify',
  };

  @override
  Widget build(BuildContext context) {
    final tool = step['tool'] as String? ?? 'none';
    final action = step['action'] as String? ?? '';
    final description = step['description'] as String? ?? action;
    final requiresConfirmation = step['requires_confirmation'] as bool? ?? true;

    final color = _toolColors[tool] ?? const Color(0xFF6C757D);
    final icon = _toolIcons[tool] ?? Icons.device_unknown_rounded;

    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Step number
          Container(
            width: 18,
            height: 18,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: color.withOpacity(0.15),
              border: Border.all(color: color.withOpacity(0.5)),
            ),
            child: Center(
              child: Text(
                '${index + 1}',
                style: GoogleFonts.outfit(
                  color: color,
                  fontSize: 10,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ),
          const SizedBox(width: 8),

          // Step info
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(icon, color: color, size: 13),
                    const SizedBox(width: 4),
                    Text(
                      _actionLabels[action] ?? action,
                      style: GoogleFonts.outfit(
                        color: color,
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(width: 6),
                    // Confirmation indicator
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                      decoration: BoxDecoration(
                        color: requiresConfirmation
                            ? const Color(0xFFFFB703).withOpacity(0.12)
                            : const Color(0xFF38B000).withOpacity(0.12),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(
                        requiresConfirmation ? '⚠ Review' : '⚡ Auto',
                        style: GoogleFonts.outfit(
                          color: requiresConfirmation
                              ? const Color(0xFFFFB703)
                              : const Color(0xFF38B000),
                          fontSize: 9,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 2),
                Text(
                  description,
                  style: GoogleFonts.outfit(
                    color: Colors.white54,
                    fontSize: 11,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
