// lib/widgets/approval_card_attachment.dart
//
// Batch HITL approval card for downloading Gmail email attachments.
// Shown when the agent stages a "download_email_attachment" action.
//
// Features:
//  - Displays the source email subject/sender at the top.
//  - Lists all attachments with filename, type icon, and size.
//  - Each attachment has an individual checkbox so the user can deselect any.
//  - "Save to Documents" sends only selected attachments.
//  - Shows a loading state while ingestion runs on the backend.

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/api_service.dart';

class ApprovalCardAttachment extends StatefulWidget {
  /// The raw approval_required data map from the backend.
  /// Expected shape:
  /// {
  ///   "type": "approval_required",
  ///   "action": "download_attachment",
  ///   "data": {
  ///     "email_id": "...",
  ///     "subject": "...",
  ///     "sender": "...",
  ///     "attachments": [
  ///       { "attachment_id": "...", "filename": "...", "mime_type": "...",
  ///         "size_bytes": 12345, "email_id": "..." }
  ///     ]
  ///   }
  /// }
  final Map<String, dynamic> approvalData;

  /// Called when the user taps Cancel.
  final VoidCallback onCancel;

  /// Called with a success message after download completes.
  final void Function(String message) onSuccess;

  const ApprovalCardAttachment({
    super.key,
    required this.approvalData,
    required this.onCancel,
    required this.onSuccess,
  });

  @override
  State<ApprovalCardAttachment> createState() => _ApprovalCardAttachmentState();
}

class _ApprovalCardAttachmentState extends State<ApprovalCardAttachment> {
  final _api = ApiService();
  late List<Map<String, dynamic>> _attachments;
  late List<bool> _selected;
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    final data = widget.approvalData['data'] as Map<String, dynamic>? ?? {};
    final rawList = (data['attachments'] as List<dynamic>?) ?? [];
    _attachments = rawList.map((e) => Map<String, dynamic>.from(e as Map)).toList();
    _selected = List.filled(_attachments.length, true);
  }

  String _fileIcon(String mimeType, String filename) {
    final ext = filename.split('.').last.toLowerCase();
    if (mimeType.contains('pdf') || ext == 'pdf') return '📄';
    if (mimeType.contains('word') || ext == 'docx' || ext == 'doc') return '📝';
    if (mimeType.contains('csv') || ext == 'csv') return '📊';
    if (mimeType.contains('text') || ext == 'txt' || ext == 'md') return '📃';
    if (mimeType.contains('image')) return '🖼️';
    return '📎';
  }

  String _formatSize(dynamic sizeBytes) {
    final bytes = (sizeBytes as num?)?.toInt() ?? 0;
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  }

  Future<void> _onSave() async {
    final toSave = <Map<String, dynamic>>[];
    for (int i = 0; i < _attachments.length; i++) {
      toSave.add({..._attachments[i], 'selected': _selected[i]});
    }

    setState(() {
      _loading = true;
      _error = null;
    });

    final data = widget.approvalData['data'] as Map<String, dynamic>? ?? {};
    final emailId = data['email_id'] as String? ?? '';

    try {
      final result = await _api.executeDownloadAttachment(
        emailId: emailId,
        attachments: toSave,
      );
      final message = result['message'] as String? ?? '✅ Attachments saved to Documents.';
      widget.onSuccess(message);
    } catch (e) {
      setState(() {
        _error = e.toString().replaceFirst('Exception: ', '');
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final data = widget.approvalData['data'] as Map<String, dynamic>? ?? {};
    final subject = data['subject'] as String? ?? 'Email';
    final sender = data['sender'] as String? ?? '';
    final selectedCount = _selected.where((s) => s).length;

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            const Color(0xFF1a2332),
            const Color(0xFF0f1923),
          ],
        ),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: const Color(0xFF3D8EFF).withOpacity(0.4),
          width: 1.2,
        ),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF3D8EFF).withOpacity(0.08),
            blurRadius: 24,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ── Header ──────────────────────────────────────────────────────────
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  const Color(0xFF3D8EFF).withOpacity(0.15),
                  const Color(0xFF3D8EFF).withOpacity(0.05),
                ],
              ),
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(20),
                topRight: Radius.circular(20),
              ),
            ),
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: const Color(0xFF3D8EFF).withOpacity(0.2),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Text('📎', style: TextStyle(fontSize: 20)),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Save Attachments to Documents',
                        style: GoogleFonts.inter(
                          color: Colors.white,
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      if (subject.isNotEmpty)
                        Text(
                          subject,
                          style: GoogleFonts.inter(
                            color: Colors.white54,
                            fontSize: 12,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      if (sender.isNotEmpty)
                        Text(
                          'From: $sender',
                          style: GoogleFonts.inter(
                            color: Colors.white38,
                            fontSize: 11,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),

          // ── Attachment list ──────────────────────────────────────────────────
          if (_attachments.isEmpty)
            Padding(
              padding: const EdgeInsets.all(16),
              child: Text(
                'No attachments found in this email.',
                style: GoogleFonts.inter(color: Colors.white54, fontSize: 13),
              ),
            )
          else
            ListView.separated(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              itemCount: _attachments.length,
              separatorBuilder: (_, _) => Divider(
                color: Colors.white.withOpacity(0.06),
                height: 1,
              ),
              itemBuilder: (context, index) {
                final att = _attachments[index];
                final filename = att['filename'] as String? ?? 'attachment';
                final mimeType = att['mime_type'] as String? ?? '';
                final sizeBytes = att['size_bytes'];
                return CheckboxListTile(
                  value: _selected[index],
                  onChanged: _loading
                      ? null
                      : (val) => setState(() => _selected[index] = val ?? false),
                  activeColor: const Color(0xFF3D8EFF),
                  checkColor: Colors.white,
                  contentPadding: EdgeInsets.zero,
                  title: Row(
                    children: [
                      Text(
                        _fileIcon(mimeType, filename),
                        style: const TextStyle(fontSize: 18),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          filename,
                          style: GoogleFonts.inter(
                            color: Colors.white,
                            fontSize: 13,
                            fontWeight: FontWeight.w500,
                          ),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                  subtitle: Text(
                    _formatSize(sizeBytes),
                    style: GoogleFonts.inter(
                      color: Colors.white38,
                      fontSize: 11,
                    ),
                  ),
                );
              },
            ),

          // ── Error ─────────────────────────────────────────────────────────
          if (_error != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
              child: Container(
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: Colors.red.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.red.withOpacity(0.3)),
                ),
                child: Text(
                  _error!,
                  style: GoogleFonts.inter(color: Colors.redAccent, fontSize: 12),
                ),
              ),
            ),

          // ── Actions ───────────────────────────────────────────────────────
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
            child: Row(
              children: [
                // Cancel
                Expanded(
                  child: TextButton(
                    onPressed: _loading ? null : widget.onCancel,
                    style: TextButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 12),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                        side: BorderSide(
                          color: Colors.white.withOpacity(0.15),
                        ),
                      ),
                    ),
                    child: Text(
                      'Cancel',
                      style: GoogleFonts.inter(
                        color: Colors.white54,
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 10),
                // Save
                Expanded(
                  flex: 2,
                  child: ElevatedButton(
                    onPressed:
                        (_loading || selectedCount == 0) ? null : _onSave,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF3D8EFF),
                      disabledBackgroundColor:
                          const Color(0xFF3D8EFF).withOpacity(0.3),
                      padding: const EdgeInsets.symmetric(vertical: 12),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                      elevation: 0,
                    ),
                    child: _loading
                        ? const SizedBox(
                            height: 18,
                            width: 18,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              valueColor:
                                  AlwaysStoppedAnimation<Color>(Colors.white),
                            ),
                          )
                        : Text(
                            selectedCount == _attachments.length
                                ? 'Save All to Documents'
                                : 'Save $selectedCount to Documents',
                            style: GoogleFonts.inter(
                              color: Colors.white,
                              fontSize: 14,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
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
