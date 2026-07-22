// lib/widgets/document_card.dart — Individual document card widget.
//
// Shows file type icon, name, size, status badge, page/chunk counts,
// and a swipe-to-delete action via a Dismissible wrapper.

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../models/document.dart';

class DocumentCard extends StatelessWidget {
  final DocumentRecord doc;
  final VoidCallback onDelete;
  final VoidCallback? onTap;

  const DocumentCard({
    super.key,
    required this.doc,
    required this.onDelete,
    this.onTap,
  });

  // ── Status colours & labels ───────────────────────────────────────────────

  Color get _statusColor {
    switch (doc.status) {
      case 'ready':
        return const Color(0xFF38B000);
      case 'processing':
        return const Color(0xFFE0A100);
      case 'error':
        return const Color(0xFFE63946);
      default:
        return const Color(0xFF6C757D);
    }
  }

  String get _statusLabel {
    switch (doc.status) {
      case 'ready':
        return 'Ready';
      case 'processing':
        return 'Processing…';
      case 'error':
        return 'Error';
      default:
        return doc.status;
    }
  }

  Color get _fileTypeColor {
    switch (doc.fileType.toLowerCase()) {
      case 'pdf':
        return const Color(0xFFE63946);
      case 'docx':
      case 'doc':
        return const Color(0xFF2B9BF4);
      case 'csv':
        return const Color(0xFF38B000);
      case 'txt':
      case 'md':
        return const Color(0xFF9E9E9E);
      default:
        return const Color(0xFF7B2CBF);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Dismissible(
      key: ValueKey(doc.id),
      direction: DismissDirection.endToStart,
      background: Container(
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: 24),
        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
        decoration: BoxDecoration(
          color: const Color(0xFFE63946).withOpacity(0.15),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: const Color(0xFFE63946).withOpacity(0.4)),
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.delete_rounded, color: Color(0xFFE63946), size: 22),
            const SizedBox(height: 4),
            Text('Delete', style: GoogleFonts.outfit(color: const Color(0xFFE63946), fontSize: 11)),
          ],
        ),
      ),
      confirmDismiss: (_) async {
        return await showDialog<bool>(
          context: context,
          builder: (ctx) => _DeleteConfirmDialog(displayName: doc.displayName),
        ) ?? false;
      },
      onDismissed: (_) => onDelete(),
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
          decoration: BoxDecoration(
            color: const Color(0xFF1E1E24),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: doc.isError
                  ? const Color(0xFFE63946).withOpacity(0.35)
                  : Colors.white.withOpacity(0.06),
            ),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(0.25),
                blurRadius: 8,
                offset: const Offset(0, 2),
              ),
            ],
          ),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // ── Row 1: Icon + Name + Status badge ─────────────────────
                Row(
                  children: [
                    // File type badge
                    Container(
                      width: 44,
                      height: 44,
                      decoration: BoxDecoration(
                        color: _fileTypeColor.withOpacity(0.12),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: _fileTypeColor.withOpacity(0.3)),
                      ),
                      child: Center(
                        child: Text(
                          doc.fileType.toUpperCase(),
                          style: GoogleFonts.outfit(
                            color: _fileTypeColor,
                            fontSize: 11,
                            fontWeight: FontWeight.w800,
                            letterSpacing: 0.5,
                          ),
                        ),
                      ),
                    ),

                    const SizedBox(width: 12),

                    // Name + date
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            doc.displayName,
                            style: GoogleFonts.outfit(
                              color: const Color(0xFFF8F9FA),
                              fontSize: 15,
                              fontWeight: FontWeight.w600,
                            ),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                          const SizedBox(height: 2),
                          Text(
                            doc.formattedDate.isNotEmpty
                                ? 'Uploaded ${doc.formattedDate}'
                                : 'Just uploaded',
                            style: GoogleFonts.outfit(
                              color: const Color(0xFF6C757D),
                              fontSize: 12,
                            ),
                          ),
                        ],
                      ),
                    ),

                    const SizedBox(width: 8),

                    // Status badge
                    _StatusBadge(
                      label: _statusLabel,
                      color: _statusColor,
                      isAnimated: doc.isProcessing,
                    ),
                  ],
                ),

                const SizedBox(height: 12),

                // ── Row 2: Metadata pills ──────────────────────────────────
                Row(
                  children: [
                    _MetaPill(
                      icon: Icons.storage_rounded,
                      label: doc.formattedSize,
                      color: const Color(0xFF00B4D8),
                    ),
                    if (doc.pageCount != null) ...[
                      const SizedBox(width: 8),
                      _MetaPill(
                        icon: Icons.menu_book_rounded,
                        label: '${doc.pageCount} pages',
                        color: const Color(0xFF9E9E9E),
                      ),
                    ],
                    if (doc.chunkCount != null && doc.isReady) ...[
                      const SizedBox(width: 8),
                      _MetaPill(
                        icon: Icons.auto_awesome_mosaic_rounded,
                        label: '${doc.chunkCount} chunks',
                        color: const Color(0xFF7B2CBF),
                      ),
                    ],
                  ],
                ),

                // ── Error message ──────────────────────────────────────────
                if (doc.isError && doc.errorMessage != null) ...[
                  const SizedBox(height: 10),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    decoration: BoxDecoration(
                      color: const Color(0xFFE63946).withOpacity(0.08),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: const Color(0xFFE63946).withOpacity(0.25)),
                    ),
                    child: Row(
                      children: [
                        const Icon(Icons.warning_amber_rounded,
                            color: Color(0xFFE63946), size: 14),
                        const SizedBox(width: 6),
                        Expanded(
                          child: Text(
                            doc.errorMessage!,
                            style: GoogleFonts.outfit(
                              color: const Color(0xFFE63946),
                              fontSize: 12,
                            ),
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
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

// ── Status badge with optional pulse animation ────────────────────────────────

class _StatusBadge extends StatefulWidget {
  final String label;
  final Color color;
  final bool isAnimated;

  const _StatusBadge({
    required this.label,
    required this.color,
    this.isAnimated = false,
  });

  @override
  State<_StatusBadge> createState() => _StatusBadgeState();
}

class _StatusBadgeState extends State<_StatusBadge>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _pulse;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    );
    _pulse = Tween<double>(begin: 0.4, end: 1.0).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeInOut),
    );
    if (widget.isAnimated) {
      _controller.repeat(reverse: true);
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
      animation: _pulse,
      builder: (_, child) {
        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
          decoration: BoxDecoration(
            color: widget.color.withOpacity(widget.isAnimated ? _pulse.value * 0.15 : 0.12),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: widget.color.withOpacity(0.4)),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 6,
                height: 6,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: widget.color,
                  boxShadow: [
                    BoxShadow(
                      color: widget.color.withOpacity(0.6),
                      blurRadius: widget.isAnimated ? _pulse.value * 6 : 4,
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 6),
              Text(
                widget.label,
                style: GoogleFonts.outfit(
                  color: widget.color,
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

// ── Metadata pill ─────────────────────────────────────────────────────────────

class _MetaPill extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;

  const _MetaPill({required this.icon, required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withOpacity(0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withOpacity(0.2)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: color.withOpacity(0.8), size: 12),
          const SizedBox(width: 4),
          Text(
            label,
            style: GoogleFonts.outfit(
              color: color.withOpacity(0.9),
              fontSize: 11,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}

// ── Delete confirmation dialog ────────────────────────────────────────────────

class _DeleteConfirmDialog extends StatelessWidget {
  final String displayName;

  const _DeleteConfirmDialog({required this.displayName});

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: const Color(0xFF1E1E24),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: const Color(0xFFE63946).withOpacity(0.12),
                shape: BoxShape.circle,
              ),
              child: const Icon(Icons.delete_rounded,
                  color: Color(0xFFE63946), size: 28),
            ),
            const SizedBox(height: 16),
            Text(
              'Delete Document?',
              style: GoogleFonts.outfit(
                color: const Color(0xFFF8F9FA),
                fontSize: 18,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              '"$displayName" and all its indexed data will be permanently removed.',
              style: GoogleFonts.outfit(
                color: const Color(0xFF9E9E9E),
                fontSize: 13,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 24),
            Row(
              children: [
                Expanded(
                  child: TextButton(
                    onPressed: () => Navigator.pop(context, false),
                    style: TextButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 12),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                        side: BorderSide(color: Colors.white.withOpacity(0.1)),
                      ),
                    ),
                    child: Text('Cancel',
                        style: GoogleFonts.outfit(color: Colors.white60)),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: ElevatedButton(
                    onPressed: () => Navigator.pop(context, true),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFFE63946),
                      padding: const EdgeInsets.symmetric(vertical: 12),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12)),
                    ),
                    child: Text('Delete',
                        style: GoogleFonts.outfit(
                          color: Colors.white,
                          fontWeight: FontWeight.w700,
                        )),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
