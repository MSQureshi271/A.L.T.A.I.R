import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class WatcherCard extends StatelessWidget {
  final Map<String, dynamic> watcher;
  final Function(bool) onToggle;
  final VoidCallback onDelete;
  final VoidCallback onViewHistory;

  const WatcherCard({
    super.key,
    required this.watcher,
    required this.onToggle,
    required this.onDelete,
    required this.onViewHistory,
  });

  @override
  Widget build(BuildContext context) {
    final bool isEnabled = watcher['enabled'] ?? true;
    final String description = watcher['description'] ?? '';
    final String provider = watcher['trigger']?['provider'] ?? 'gmail';
    final List<dynamic> actions = watcher['actions'] ?? [];

    final bool isGmail = provider.toLowerCase() == 'gmail';
    final IconData providerIcon = isGmail ? Icons.mail_rounded : Icons.calendar_month_rounded;
    final Color providerColor = isGmail ? const Color(0xFFE63946) : const Color(0xFF00B4D8);

    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      decoration: BoxDecoration(
        color: const Color(0xFF1E1E28),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: isEnabled
              ? providerColor.withOpacity(0.25)
              : Colors.white.withOpacity(0.05),
          width: 1,
        ),
        boxShadow: isEnabled
            ? [
                BoxShadow(
                  color: providerColor.withOpacity(0.04),
                  blurRadius: 10,
                  offset: const Offset(0, 4),
                )
              ]
            : null,
      ),
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // ── Top Row: Icon + Switch Toggle ─────────────────────────────────
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: providerColor.withOpacity(0.12),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Icon(
                    providerIcon,
                    color: providerColor,
                    size: 20,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        provider.toUpperCase(),
                        style: GoogleFonts.outfit(
                          color: providerColor.withOpacity(0.8),
                          fontSize: 10,
                          fontWeight: FontWeight.w800,
                          letterSpacing: 1.2,
                        ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        description.isNotEmpty ? description : 'Generic Watcher',
                        style: GoogleFonts.outfit(
                          color: isEnabled ? Colors.white : Colors.white60,
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                          decoration: isEnabled ? null : TextDecoration.lineThrough,
                        ),
                      ),
                    ],
                  ),
                ),
                Switch(
                  value: isEnabled,
                  onChanged: onToggle,
                  activeColor: const Color(0xFF7B2CBF),
                  activeTrackColor: const Color(0xFF7B2CBF).withOpacity(0.3),
                  inactiveThumbColor: Colors.white30,
                  inactiveTrackColor: Colors.white10,
                ),
              ],
            ),

            const SizedBox(height: 14),
            Divider(color: Colors.white.withOpacity(0.06), height: 1),
            const SizedBox(height: 14),

            // ── Actions summary row ──────────────────────────────────────────
            Row(
              children: [
                Text(
                  'ACTIONS: ',
                  style: GoogleFonts.outfit(
                    color: Colors.white38,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(width: 6),
                Expanded(
                  child: Wrap(
                    spacing: 6,
                    runSpacing: 4,
                    children: actions.map<Widget>((action) {
                      final type = action['action_type'] ?? 'notify';
                      return Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          color: const Color(0xFF13131A),
                          borderRadius: BorderRadius.circular(6),
                          border: Border.all(color: Colors.white.withOpacity(0.06)),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(
                              _getActionIcon(type),
                              size: 11,
                              color: const Color(0xFFE0A100),
                            ),
                            const SizedBox(width: 4),
                            Text(
                              type.toString().toUpperCase(),
                              style: GoogleFonts.outfit(
                                color: Colors.white70,
                                fontSize: 9,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                        ),
                      );
                    }).toList(),
                  ),
                ),
              ],
            ),

            const SizedBox(height: 16),

            // ── Bottom Action Buttons ────────────────────────────────────────
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                // History Button
                TextButton.icon(
                  onPressed: onViewHistory,
                  icon: const Icon(Icons.history_rounded, size: 16, color: Color(0xFF7B2CBF)),
                  label: Text(
                    'Run Logs',
                    style: GoogleFonts.outfit(
                      color: const Color(0xFF7B2CBF),
                      fontSize: 13,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  style: TextButton.styleFrom(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    backgroundColor: const Color(0xFF7B2CBF).withOpacity(0.08),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8),
                    ),
                  ),
                ),

                // Delete Button
                IconButton(
                  onPressed: onDelete,
                  icon: const Icon(
                    Icons.delete_outline_rounded,
                    color: Color(0xFFE63946),
                    size: 18,
                  ),
                  style: IconButton.styleFrom(
                    padding: const EdgeInsets.all(8),
                    backgroundColor: const Color(0xFFE63946).withOpacity(0.08),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8),
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  IconData _getActionIcon(String type) {
    switch (type.toLowerCase()) {
      case 'notify':
        return Icons.notifications_active_outlined;
      case 'summarize':
        return Icons.short_text_rounded;
      case 'save_memory':
        return Icons.psychology_outlined;
      default:
        return Icons.bolt_outlined;
    }
  }
}
