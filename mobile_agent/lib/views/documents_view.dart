// lib/views/documents_view.dart — Documents Library Screen.
//
// Features:
//   • Premium glassmorphic header with live document stats
//   • Animated FAB upload button with file picker integration
//   • Per-document status polling for 'processing' documents
//   • Pull-to-refresh
//   • Swipe-to-delete with confirmation
//   • Empty state with guided onboarding copy
//   • Upload progress overlay with gradient animation
//   • Supported file types: PDF, DOCX, TXT, CSV, MD

import 'dart:async';
import 'dart:io';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../models/document.dart';
import '../services/api_service.dart';
import '../widgets/document_card.dart';

class DocumentsView extends StatefulWidget {
  const DocumentsView({super.key});

  @override
  State<DocumentsView> createState() => _DocumentsViewState();
}

class _DocumentsViewState extends State<DocumentsView>
    with TickerProviderStateMixin {
  final _api = ApiService();

  List<DocumentRecord> _documents = [];
  bool _isLoading = true;
  bool _isUploading = false;
  String _uploadStatusText = '';
  double? _uploadProgress; // null = indeterminate

  // Polling timer for 'processing' documents
  Timer? _pollTimer;

  late AnimationController _fabController;
  late Animation<double> _fabScale;
  late AnimationController _uploadController;
  late Animation<double> _uploadGradient;

  @override
  void initState() {
    super.initState();

    _fabController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 200),
    );
    _fabScale = Tween<double>(begin: 1.0, end: 0.92).animate(
      CurvedAnimation(parent: _fabController, curve: Curves.easeOut),
    );

    _uploadController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat();
    _uploadGradient = Tween<double>(begin: 0.0, end: 1.0).animate(_uploadController);

    _loadDocuments();
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _fabController.dispose();
    _uploadController.dispose();
    super.dispose();
  }

  // ── Data loading ──────────────────────────────────────────────────────────

  Future<void> _loadDocuments() async {
    if (!mounted) return;
    setState(() => _isLoading = true);
    try {
      final data = await _api.listDocuments();
      if (!mounted) return;
      setState(() {
        _documents = data.map(DocumentRecord.fromJson).toList();
        _isLoading = false;
      });
      _startPollingIfNeeded();
    } catch (e) {
      if (!mounted) return;
      setState(() => _isLoading = false);
      _showSnack('Failed to load documents: $e', isError: true);
    }
  }

  void _startPollingIfNeeded() {
    _pollTimer?.cancel();
    final hasProcessing = _documents.any((d) => d.isProcessing);
    if (!hasProcessing) return;

    _pollTimer = Timer.periodic(const Duration(seconds: 4), (_) async {
      final processingDocs = _documents.where((d) => d.isProcessing).toList();
      if (processingDocs.isEmpty) {
        _pollTimer?.cancel();
        return;
      }
      for (final doc in processingDocs) {
        try {
          final updated = await _api.getDocument(doc.id);
          final updatedRecord = DocumentRecord.fromJson(updated);
          if (!mounted) return;
          setState(() {
            final idx = _documents.indexWhere((d) => d.id == doc.id);
            if (idx != -1) _documents[idx] = updatedRecord;
          });
          if (updatedRecord.isReady) {
            _showSnack('✅ "${updatedRecord.displayName}" is ready!');
          } else if (updatedRecord.isError) {
            _showSnack('❌ "${updatedRecord.displayName}" failed to process.', isError: true);
          }
        } catch (_) {
          // Silently ignore polling errors
        }
      }
    });
  }

  // ── Upload ────────────────────────────────────────────────────────────────

  Future<void> _pickAndUpload() async {
    final result = await FilePicker.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['pdf', 'docx', 'doc', 'txt', 'md', 'csv'],
      withData: false,
    );

    if (result == null || result.files.isEmpty) return;
    final picked = result.files.first;
    if (picked.path == null) {
      _showSnack('Could not access file path.', isError: true);
      return;
    }

    final file = File(picked.path!);
    final fileSize = await file.length();
    const maxSize = 50 * 1024 * 1024; // 50 MB
    if (fileSize > maxSize) {
      _showSnack('File is too large. Maximum allowed size is 50 MB.', isError: true);
      return;
    }

    // Determine MIME type from extension
    final ext = picked.extension?.toLowerCase() ?? '';
    final mimeType = _mimeFromExtension(ext);

    setState(() {
      _isUploading = true;
      _uploadProgress = null;
      _uploadStatusText = 'Uploading "${picked.name}"…';
    });

    try {
      setState(() => _uploadStatusText = 'Sending to A.L.T.A.I.R. backend…');
      final resp = await _api.uploadDocument(
        filePath: picked.path!,
        fileName: picked.name,
        mimeType: mimeType,
      );

      final newDoc = DocumentRecord(
        id: resp['document_id'] as String? ?? '',
        userId: '',
        filename: picked.name,
        displayName: resp['display_name'] as String? ?? picked.name,
        fileType: ext,
        mimeType: mimeType,
        storagePath: '',
        fileSizeBytes: fileSize,
        status: 'processing',
      );

      setState(() {
        _isUploading = false;
        _uploadStatusText = '';
        _documents.insert(0, newDoc);
      });

      _showSnack('📤 "${newDoc.displayName}" uploaded. Indexing in background…');
      _startPollingIfNeeded();
    } catch (e) {
      setState(() {
        _isUploading = false;
        _uploadStatusText = '';
      });
      _showSnack('Upload failed: $e', isError: true);
    }
  }

  // ── Delete ────────────────────────────────────────────────────────────────

  Future<void> _deleteDocument(DocumentRecord doc) async {
    try {
      await _api.deleteDocument(doc.id);
      if (!mounted) return;
      setState(() => _documents.removeWhere((d) => d.id == doc.id));
      _showSnack('🗑️  "${doc.displayName}" deleted.');
    } catch (e) {
      _showSnack('Delete failed: $e', isError: true);
      // Re-add the document to the list (optimistic rollback)
      setState(() => _documents.insert(0, doc));
    }
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  void _showSnack(String msg, {bool isError = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(msg, style: GoogleFonts.outfit(fontSize: 13)),
        backgroundColor: isError ? const Color(0xFFE63946) : const Color(0xFF1E1E24),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        duration: Duration(seconds: isError ? 4 : 3),
      ),
    );
  }

  String _mimeFromExtension(String ext) {
    switch (ext) {
      case 'pdf':
        return 'application/pdf';
      case 'docx':
        return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
      case 'doc':
        return 'application/msword';
      case 'csv':
        return 'text/csv';
      case 'md':
        return 'text/markdown';
      case 'txt':
      default:
        return 'text/plain';
    }
  }

  // ── Stats ─────────────────────────────────────────────────────────────────

  int get _readyCount => _documents.where((d) => d.isReady).length;
  int get _processingCount => _documents.where((d) => d.isProcessing).length;

  // ── Build ─────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0F0F12),
      body: Stack(
        children: [
          CustomScrollView(
            physics: const BouncingScrollPhysics(),
            slivers: [
              _buildHeader(),
              if (_isLoading)
                const SliverFillRemaining(child: _LoadingState())
              else if (_documents.isEmpty)
                SliverFillRemaining(child: _EmptyState(onUpload: _pickAndUpload))
              else ...[
                _buildStatsBar(),
                _buildDocumentList(),
              ],
            ],
          ),

          // Upload progress overlay
          if (_isUploading) _buildUploadOverlay(),
        ],
      ),
      floatingActionButton: _documents.isNotEmpty ? _buildFab() : null,
    );
  }

  // ── Header ────────────────────────────────────────────────────────────────

  SliverAppBar _buildHeader() {
    return SliverAppBar(
      backgroundColor: const Color(0xFF0F0F12),
      elevation: 0,
      pinned: true,
      expandedHeight: 130,
      leading: IconButton(
        icon: const Icon(Icons.arrow_back_rounded, color: Colors.white70),
        onPressed: () => Navigator.pop(context),
      ),
      actions: [
        IconButton(
          icon: const Icon(Icons.refresh_rounded, color: Colors.white38, size: 20),
          tooltip: 'Refresh',
          onPressed: _loadDocuments,
        ),
        const SizedBox(width: 8),
      ],
      flexibleSpace: FlexibleSpaceBar(
        collapseMode: CollapseMode.pin,
        background: Container(
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [Color(0xFF130D1E), Color(0xFF0F0F12)],
            ),
          ),
          child: SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 48, 20, 0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          gradient: const LinearGradient(
                            colors: [Color(0xFF7B2CBF), Color(0xFF9D4EDD)],
                          ),
                          borderRadius: BorderRadius.circular(12),
                          boxShadow: [
                            BoxShadow(
                              color: const Color(0xFF7B2CBF).withOpacity(0.4),
                              blurRadius: 12,
                              offset: const Offset(0, 4),
                            ),
                          ],
                        ),
                        child: const Icon(Icons.folder_special_rounded,
                            color: Colors.white, size: 20),
                      ),
                      const SizedBox(width: 12),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Document Library',
                            style: GoogleFonts.outfit(
                              color: const Color(0xFFF8F9FA),
                              fontSize: 22,
                              fontWeight: FontWeight.w800,
                            ),
                          ),
                          Text(
                            'Query any doc in any conversation',
                            style: GoogleFonts.outfit(
                              color: const Color(0xFF6C757D),
                              fontSize: 12,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  // ── Stats bar ─────────────────────────────────────────────────────────────

  SliverToBoxAdapter _buildStatsBar() {
    return SliverToBoxAdapter(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
        child: Row(
          children: [
            _StatChip(
              label: '${_documents.length} total',
              icon: Icons.folder_open_rounded,
              color: const Color(0xFF7B2CBF),
            ),
            const SizedBox(width: 8),
            _StatChip(
              label: '$_readyCount indexed',
              icon: Icons.check_circle_rounded,
              color: const Color(0xFF38B000),
            ),
            if (_processingCount > 0) ...[
              const SizedBox(width: 8),
              _StatChip(
                label: '$_processingCount indexing',
                icon: Icons.sync_rounded,
                color: const Color(0xFFE0A100),
                isPulsing: true,
              ),
            ],
          ],
        ),
      ),
    );
  }

  // ── Document list ─────────────────────────────────────────────────────────

  SliverList _buildDocumentList() {
    return SliverList(
      delegate: SliverChildBuilderDelegate(
        (context, index) {
          if (index == _documents.length) {
            // Bottom padding item
            return const SizedBox(height: 100);
          }
          final doc = _documents[index];
          return DocumentCard(
            key: ValueKey(doc.id),
            doc: doc,
            onDelete: () => _deleteDocument(doc),
          );
        },
        childCount: _documents.length + 1,
      ),
    );
  }

  // ── FAB ───────────────────────────────────────────────────────────────────

  Widget _buildFab() {
    return GestureDetector(
      onTapDown: (_) => _fabController.forward(),
      onTapUp: (_) {
        _fabController.reverse();
        _pickAndUpload();
      },
      onTapCancel: () => _fabController.reverse(),
      child: ScaleTransition(
        scale: _fabScale,
        child: Container(
          height: 58,
          padding: const EdgeInsets.symmetric(horizontal: 24),
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              colors: [Color(0xFF7B2CBF), Color(0xFF9D4EDD)],
            ),
            borderRadius: BorderRadius.circular(29),
            boxShadow: [
              BoxShadow(
                color: const Color(0xFF7B2CBF).withOpacity(0.5),
                blurRadius: 20,
                offset: const Offset(0, 6),
              ),
            ],
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.upload_file_rounded, color: Colors.white, size: 20),
              const SizedBox(width: 10),
              Text(
                'Upload Document',
                style: GoogleFonts.outfit(
                  color: Colors.white,
                  fontSize: 15,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  // ── Upload overlay ────────────────────────────────────────────────────────

  Widget _buildUploadOverlay() {
    return Positioned.fill(
      child: Container(
        color: Colors.black.withOpacity(0.65),
        child: Center(
          child: Container(
            width: 280,
            padding: const EdgeInsets.all(28),
            decoration: BoxDecoration(
              color: const Color(0xFF1E1E24),
              borderRadius: BorderRadius.circular(24),
              border: Border.all(color: const Color(0xFF7B2CBF).withOpacity(0.3)),
              boxShadow: [
                BoxShadow(
                  color: const Color(0xFF7B2CBF).withOpacity(0.2),
                  blurRadius: 40,
                  spreadRadius: 5,
                ),
              ],
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                AnimatedBuilder(
                  animation: _uploadGradient,
                  builder: (_, child) => Container(
                    width: 64,
                    height: 64,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      gradient: SweepGradient(
                        startAngle: 0,
                        endAngle: 6.28,
                        colors: [
                          const Color(0xFF7B2CBF),
                          const Color(0xFF00B4D8),
                          const Color(0xFF7B2CBF),
                        ],
                        stops: [
                          _uploadGradient.value,
                          (_uploadGradient.value + 0.4).clamp(0, 1),
                          1.0,
                        ],
                      ),
                    ),
                    child: const Padding(
                      padding: EdgeInsets.all(4),
                      child: CircleAvatar(
                        backgroundColor: Color(0xFF1E1E24),
                        child: Icon(Icons.cloud_upload_rounded,
                            color: Color(0xFF7B2CBF), size: 28),
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 20),
                Text(
                  'Uploading',
                  style: GoogleFonts.outfit(
                    color: const Color(0xFFF8F9FA),
                    fontSize: 18,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  _uploadStatusText,
                  style: GoogleFonts.outfit(
                    color: const Color(0xFF9E9E9E),
                    fontSize: 13,
                  ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 20),
                ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(
                    value: _uploadProgress,
                    backgroundColor: const Color(0xFF2A2A35),
                    valueColor: const AlwaysStoppedAnimation<Color>(Color(0xFF7B2CBF)),
                    minHeight: 4,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

// ── Empty state ───────────────────────────────────────────────────────────────

class _EmptyState extends StatelessWidget {
  final VoidCallback onUpload;

  const _EmptyState({required this.onUpload});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 40),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: 96,
              height: 96,
              decoration: BoxDecoration(
                color: const Color(0xFF7B2CBF).withOpacity(0.08),
                shape: BoxShape.circle,
                border: Border.all(
                    color: const Color(0xFF7B2CBF).withOpacity(0.2), width: 2),
              ),
              child: const Icon(Icons.folder_open_rounded,
                  color: Color(0xFF7B2CBF), size: 44),
            ),
            const SizedBox(height: 24),
            Text(
              'No Documents Yet',
              style: GoogleFonts.outfit(
                color: const Color(0xFFF8F9FA),
                fontSize: 22,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 10),
            Text(
              'Upload contracts, reports, pitch decks, or any document. '
              'A.L.T.A.I.R. will index them so you can query them in any conversation.',
              style: GoogleFonts.outfit(
                color: const Color(0xFF6C757D),
                fontSize: 14,
                height: 1.55,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 32),
            _SupportedFormatsRow(),
            const SizedBox(height: 32),
            GestureDetector(
              onTap: onUpload,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 16),
                decoration: BoxDecoration(
                  gradient: const LinearGradient(
                    colors: [Color(0xFF7B2CBF), Color(0xFF9D4EDD)],
                  ),
                  borderRadius: BorderRadius.circular(16),
                  boxShadow: [
                    BoxShadow(
                      color: const Color(0xFF7B2CBF).withOpacity(0.4),
                      blurRadius: 20,
                      offset: const Offset(0, 6),
                    ),
                  ],
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.upload_file_rounded,
                        color: Colors.white, size: 20),
                    const SizedBox(width: 10),
                    Text(
                      'Upload Your First Document',
                      style: GoogleFonts.outfit(
                        color: Colors.white,
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Supported formats row ─────────────────────────────────────────────────────

class _SupportedFormatsRow extends StatelessWidget {
  const _SupportedFormatsRow();

  @override
  Widget build(BuildContext context) {
    final formats = [
      ('PDF', const Color(0xFFE63946)),
      ('DOCX', const Color(0xFF2B9BF4)),
      ('TXT', const Color(0xFF9E9E9E)),
      ('CSV', const Color(0xFF38B000)),
      ('MD', const Color(0xFF9D4EDD)),
    ];

    return Column(
      children: [
        Text(
          'SUPPORTED FORMATS',
          style: GoogleFonts.outfit(
            color: const Color(0xFF6C757D),
            fontSize: 11,
            fontWeight: FontWeight.w700,
            letterSpacing: 1.4,
          ),
        ),
        const SizedBox(height: 10),
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: formats.map((f) {
            return Padding(
              padding: const EdgeInsets.symmetric(horizontal: 4),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                decoration: BoxDecoration(
                  color: f.$2.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: f.$2.withOpacity(0.3)),
                ),
                child: Text(
                  f.$1,
                  style: GoogleFonts.outfit(
                    color: f.$2,
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            );
          }).toList(),
        ),
      ],
    );
  }
}

// ── Stat chip ─────────────────────────────────────────────────────────────────

class _StatChip extends StatefulWidget {
  final String label;
  final IconData icon;
  final Color color;
  final bool isPulsing;

  const _StatChip({
    required this.label,
    required this.icon,
    required this.color,
    this.isPulsing = false,
  });

  @override
  State<_StatChip> createState() => _StatChipState();
}

class _StatChipState extends State<_StatChip>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _anim;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    );
    _anim = Tween<double>(begin: 0.5, end: 1.0).animate(
      CurvedAnimation(parent: _ctrl, curve: Curves.easeInOut),
    );
    if (widget.isPulsing) _ctrl.repeat(reverse: true);
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _anim,
      builder: (_, child) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: widget.color.withOpacity(widget.isPulsing ? _anim.value * 0.1 : 0.08),
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: widget.color.withOpacity(0.25)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(widget.icon, color: widget.color, size: 13),
            const SizedBox(width: 5),
            Text(
              widget.label,
              style: GoogleFonts.outfit(
                color: widget.color,
                fontSize: 12,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Loading state ─────────────────────────────────────────────────────────────

class _LoadingState extends StatelessWidget {
  const _LoadingState();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: CircularProgressIndicator(
        valueColor: AlwaysStoppedAnimation<Color>(Color(0xFF7B2CBF)),
        strokeWidth: 2.5,
      ),
    );
  }
}
