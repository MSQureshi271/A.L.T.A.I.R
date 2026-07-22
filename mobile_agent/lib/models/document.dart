// lib/models/document.dart — Data model for uploaded document records.
//
// Mirrors the DocumentRecord Pydantic model from the backend exactly.

class DocumentRecord {
  final String id;
  final String userId;
  final String filename;
  final String displayName;
  final String fileType;
  final String mimeType;
  final String storagePath;
  final int fileSizeBytes;
  final String status; // 'processing' | 'ready' | 'error'
  final int? pageCount;
  final int? chunkCount;
  final String? errorMessage;
  final List<String> tags;
  final String embeddingModel;
  final String createdAt;
  final String updatedAt;

  const DocumentRecord({
    required this.id,
    required this.userId,
    required this.filename,
    required this.displayName,
    required this.fileType,
    required this.mimeType,
    required this.storagePath,
    required this.fileSizeBytes,
    required this.status,
    this.pageCount,
    this.chunkCount,
    this.errorMessage,
    this.tags = const [],
    this.embeddingModel = '',
    this.createdAt = '',
    this.updatedAt = '',
  });

  factory DocumentRecord.fromJson(Map<String, dynamic> json) {
    return DocumentRecord(
      id: json['id'] as String? ?? '',
      userId: json['user_id'] as String? ?? '',
      filename: json['filename'] as String? ?? '',
      displayName: json['display_name'] as String? ?? json['filename'] as String? ?? '',
      fileType: json['file_type'] as String? ?? '',
      mimeType: json['mime_type'] as String? ?? '',
      storagePath: json['storage_path'] as String? ?? '',
      fileSizeBytes: json['file_size_bytes'] as int? ?? 0,
      status: json['status'] as String? ?? 'processing',
      pageCount: json['page_count'] as int?,
      chunkCount: json['chunk_count'] as int?,
      errorMessage: json['error_message'] as String?,
      tags: (json['tags'] as List<dynamic>?)?.map((e) => e.toString()).toList() ?? [],
      embeddingModel: json['embedding_model'] as String? ?? '',
      createdAt: json['created_at'] as String? ?? '',
      updatedAt: json['updated_at'] as String? ?? '',
    );
  }

  // ── Helpers ──────────────────────────────────────────────────────────────────

  bool get isProcessing => status == 'processing';
  bool get isReady => status == 'ready';
  bool get isError => status == 'error';

  String get formattedSize {
    if (fileSizeBytes < 1024) return '$fileSizeBytes B';
    if (fileSizeBytes < 1024 * 1024) return '${(fileSizeBytes / 1024).toStringAsFixed(1)} KB';
    return '${(fileSizeBytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  }

  String get formattedDate {
    if (createdAt.isEmpty) return '';
    try {
      final dt = DateTime.parse(createdAt).toLocal();
      return '${dt.day} ${_monthName(dt.month)} ${dt.year}';
    } catch (_) {
      return createdAt.length >= 10 ? createdAt.substring(0, 10) : createdAt;
    }
  }

  String _monthName(int m) => const [
        '', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
      ][m];

  String get fileTypeIcon {
    switch (fileType.toLowerCase()) {
      case 'pdf':
        return '📄';
      case 'docx':
      case 'doc':
        return '📝';
      case 'csv':
        return '📊';
      case 'txt':
      case 'md':
        return '📃';
      default:
        return '📁';
    }
  }
}
