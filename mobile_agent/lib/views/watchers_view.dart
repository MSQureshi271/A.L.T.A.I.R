import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../services/api_service.dart';
import '../widgets/watcher_card.dart';

class WatchersView extends StatefulWidget {
  const WatchersView({super.key});

  @override
  State<WatchersView> createState() => _WatchersViewState();
}

class _WatchersViewState extends State<WatchersView> {
  final _apiService = ApiService();
  bool _isLoading = true;
  List<Map<String, dynamic>> _watchers = [];

  @override
  void initState() {
    super.initState();
    _loadWatchers();
  }

  Future<void> _loadWatchers() async {
    setState(() => _isLoading = true);
    try {
      final data = await _apiService.getWatchers();
      setState(() {
        _watchers = data;
        _isLoading = false;
      });
    } catch (e) {
      if (mounted) {
        setState(() => _isLoading = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to load watchers: $e', style: GoogleFonts.outfit()),
            backgroundColor: const Color(0xFFE63946),
          ),
        );
      }
    }
  }

  Future<void> _toggleWatcher(String id, bool currentEnabled) async {
    try {
      final newState = await _apiService.toggleWatcher(id);
      setState(() {
        final index = _watchers.indexWhere((w) => w['id'] == id);
        if (index != -1) {
          _watchers[index]['enabled'] = newState;
        }
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              newState ? 'Watcher enabled.' : 'Watcher disabled.',
              style: GoogleFonts.outfit(),
            ),
            duration: const Duration(seconds: 2),
            backgroundColor: const Color(0xFF7B2CBF),
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to toggle state: $e', style: GoogleFonts.outfit()),
            backgroundColor: const Color(0xFFE63946),
          ),
        );
      }
    }
  }

  Future<void> _deleteWatcher(String id, String description) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1E1E24),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: Text(
          'Delete Watcher?',
          style: GoogleFonts.outfit(fontWeight: FontWeight.bold, color: Colors.white),
        ),
        content: Text(
          'Are you sure you want to stop watching and delete "$description"? This action cannot be undone.',
          style: GoogleFonts.outfit(color: Colors.white70),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: Text(
              'Cancel',
              style: GoogleFonts.outfit(color: Colors.white38, fontWeight: FontWeight.bold),
            ),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: Text(
              'Delete',
              style: GoogleFonts.outfit(color: const Color(0xFFE63946), fontWeight: FontWeight.bold),
            ),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      try {
        await _apiService.deleteWatcher(id);
        setState(() {
          _watchers.removeWhere((w) => w['id'] == id);
        });
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Watcher deleted.', style: GoogleFonts.outfit()),
              backgroundColor: const Color(0xFFE63946),
            ),
          );
        }
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Failed to delete watcher: $e', style: GoogleFonts.outfit()),
              backgroundColor: const Color(0xFFE63946),
            ),
          );
        }
      }
    }
  }

  Future<void> _viewHistory(String id, String description) async {
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF13131A),
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (context) => _WatcherHistorySheet(
        watcherId: id,
        watcherDescription: description,
        apiService: _apiService,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF13131A),
      appBar: AppBar(
        backgroundColor: const Color(0xFF13131A),
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, color: Colors.white70),
          onPressed: () => Navigator.pop(context),
        ),
        title: Text(
          'Watchers Platform',
          style: GoogleFonts.outfit(
            color: Colors.white,
            fontWeight: FontWeight.bold,
            fontSize: 20,
          ),
        ),
      ),
      body: RefreshIndicator(
        onRefresh: _loadWatchers,
        color: const Color(0xFF7B2CBF),
        backgroundColor: const Color(0xFF1E1E28),
        child: _isLoading
            ? const Center(
                child: CircularProgressIndicator(
                  color: Color(0xFF7B2CBF),
                ),
              )
            : _watchers.isEmpty
                ? _buildEmptyState()
                : _buildWatchersList(),
      ),
    );
  }

  Widget _buildEmptyState() {
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      children: [
        SizedBox(height: MediaQuery.of(context).size.height * 0.22),
        Center(
          child: Column(
            children: [
              Container(
                padding: const EdgeInsets.all(24),
                decoration: BoxDecoration(
                  color: const Color(0xFF1E1E28),
                  shape: BoxShape.circle,
                  border: Border.all(color: Colors.white.withOpacity(0.04)),
                ),
                child: const Icon(
                  Icons.visibility_off_outlined,
                  size: 48,
                  color: Colors.white24,
                ),
              ),
              const SizedBox(height: 20),
              Text(
                'No Active Watchers',
                style: GoogleFonts.outfit(
                  color: Colors.white,
                  fontWeight: FontWeight.bold,
                  fontSize: 18,
                ),
              ),
              const SizedBox(height: 10),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 40),
                child: Text(
                  'Set up automated triggers by speaking naturally. Try saying:\n'
                  '"Watch my inbox for emails from Ahmed and notify me."',
                  textAlign: TextAlign.center,
                  style: GoogleFonts.outfit(
                    color: Colors.white38,
                    fontSize: 14,
                    height: 1.5,
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildWatchersList() {
    return ListView.builder(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
      itemCount: _watchers.length,
      itemBuilder: (context, index) {
        final w = _watchers[index];
        return WatcherCard(
          watcher: w,
          onToggle: (val) => _toggleWatcher(w['id'], w['enabled'] ?? true),
          onDelete: () => _deleteWatcher(w['id'], w['description'] ?? ''),
          onViewHistory: () => _viewHistory(w['id'], w['description'] ?? ''),
        );
      },
    );
  }
}

// ── Watcher History Details Sheet widget ────────────────────────────────────

class _WatcherHistorySheet extends StatefulWidget {
  final String watcherId;
  final String watcherDescription;
  final ApiService apiService;

  const _WatcherHistorySheet({
    required this.watcherId,
    required this.watcherDescription,
    required this.apiService,
  });

  @override
  State<_WatcherHistorySheet> createState() => _WatcherHistorySheetState();
}

class _WatcherHistorySheetState extends State<_WatcherHistorySheet> {
  bool _loading = true;
  List<Map<String, dynamic>> _logs = [];

  @override
  void initState() {
    super.initState();
    _fetchLogs();
  }

  Future<void> _fetchLogs() async {
    setState(() => _loading = true);
    try {
      final list = await widget.apiService.getWatcherHistory(widget.watcherId);
      setState(() {
        _logs = list;
        _loading = false;
      });
    } catch (e) {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        top: 24,
        left: 20,
        right: 20,
        bottom: MediaQuery.of(context).viewInsets.bottom + 24,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'EXECUTION HISTORY',
                      style: GoogleFonts.outfit(
                        color: const Color(0xFF7B2CBF),
                        fontSize: 10,
                        fontWeight: FontWeight.w900,
                        letterSpacing: 1.2,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      widget.watcherDescription,
                      style: GoogleFonts.outfit(
                        color: Colors.white,
                        fontSize: 16,
                        fontWeight: FontWeight.bold,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
              IconButton(
                icon: const Icon(Icons.close_rounded, color: Colors.white38),
                onPressed: () => Navigator.pop(context),
              )
            ],
          ),
          const SizedBox(height: 10),
          Divider(color: Colors.white.withOpacity(0.06)),
          const SizedBox(height: 10),
          ConstrainedBox(
            constraints: BoxConstraints(
              maxHeight: MediaQuery.of(context).size.height * 0.5,
            ),
            child: _loading
                ? const SizedBox(
                    height: 160,
                    child: Center(
                      child: CircularProgressIndicator(color: Color(0xFF7B2CBF)),
                    ),
                  )
                : _logs.isEmpty
                    ? _buildEmptyLogs()
                    : ListView.builder(
                        shrinkWrap: true,
                        itemCount: _logs.length,
                        itemBuilder: (context, index) {
                          final log = _logs[index];
                          return _buildLogItem(log);
                        },
                      ),
          ),
        ],
      ),
    );
  }

  Widget _buildEmptyLogs() {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 48.0),
      child: Center(
        child: Column(
          children: [
            const Icon(Icons.history_toggle_off_rounded, size: 36, color: Colors.white24),
            const SizedBox(height: 12),
            Text(
              'No Execution Logs Yet',
              style: GoogleFonts.outfit(color: Colors.white38, fontSize: 13),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildLogItem(Map<String, dynamic> log) {
    final status = (log['status'] ?? 'completed').toString().toLowerCase();
    final result = log['result'] ?? log['error'] ?? 'Success';
    final startedAtStr = log['started_at'] ?? '';
    final duration = log['duration_ms'] ?? 0;

    // parse custom attributes if present
    final dslLatency = log['dsl_latency_ms'] ?? 0;
    final connLatency = log['connector_latency_ms'] ?? 0;

    Color badgeColor = const Color(0xFF38B000);
    if (status == 'failed') {
      badgeColor = const Color(0xFFE63946);
    } else if (status == 'running') {
      badgeColor = const Color(0xFF00B4D8);
    }

    String formattedTime = startedAtStr;
    try {
      final dt = DateTime.parse(startedAtStr).toLocal();
      formattedTime = '${dt.month}/${dt.day} ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}:${dt.second.toString().padLeft(2, '0')}';
    } catch (_) {}

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF1E1E28),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.white.withOpacity(0.04)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: badgeColor.withOpacity(0.12),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  status.toUpperCase(),
                  style: GoogleFonts.outfit(
                    color: badgeColor,
                    fontSize: 9,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
              Text(
                formattedTime,
                style: GoogleFonts.outfit(
                  color: Colors.white38,
                  fontSize: 11,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            result,
            style: GoogleFonts.outfit(
              color: Colors.white70,
              fontSize: 13,
              height: 1.3,
            ),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              _buildMetricBadge('RUN: ${duration}ms'),
              const SizedBox(width: 8),
              if (connLatency > 0) ...[
                _buildMetricBadge('API: ${connLatency}ms'),
                const SizedBox(width: 8),
              ],
              if (dslLatency > 0) _buildMetricBadge('DSL: ${dslLatency}ms'),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildMetricBadge(String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: const Color(0xFF13131A),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text(
        label,
        style: GoogleFonts.outfit(
          color: Colors.white38,
          fontSize: 9,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}
