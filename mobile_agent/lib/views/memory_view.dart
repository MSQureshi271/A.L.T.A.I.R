import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/api_service.dart';

/// Full-screen dashboard screen representing A.L.T.A.I.R.'s long-term memory.
/// Segmented into tab pages: Contacts, Preferences, Routines, and General Knowledge.
class MemoryView extends StatefulWidget {
  const MemoryView({super.key});

  @override
  State<MemoryView> createState() => _MemoryViewState();
}

class _MemoryViewState extends State<MemoryView> {
  final _apiService = ApiService();
  bool _isLoading = true;

  List<dynamic> _contacts = [];
  List<dynamic> _preferences = [];
  List<dynamic> _routines = [];
  List<dynamic> _knowledge = [];

  @override
  void initState() {
    super.initState();
    _loadMemoryData();
  }

  Future<void> _loadMemoryData() async {
    setState(() => _isLoading = true);
    try {
      final data = await _apiService.getMemory();
      setState(() {
        _contacts = data['contacts'] ?? [];
        _preferences = data['preferences'] ?? [];
        _routines = data['routines'] ?? [];
        _knowledge = data['knowledge'] ?? [];
        _isLoading = false;
      });
    } catch (e) {
      if (mounted) {
        setState(() => _isLoading = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to sync memory: $e', style: GoogleFonts.outfit()),
            backgroundColor: Theme.of(context).colorScheme.error,
          ),
        );
      }
    }
  }

  Future<void> _deleteEntry(String category, String key, String displayName) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1E1E24),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: Text('Forget Memory?', style: GoogleFonts.outfit(fontWeight: FontWeight.bold, color: Colors.white)),
        content: Text(
          'Are you sure you want A.L.T.A.I.R. to forget: "$displayName"?',
          style: GoogleFonts.outfit(color: const Color(0xFFADB5BD)),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: Text('Cancel', style: GoogleFonts.outfit(color: Colors.white70)),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: Text('Forget', style: GoogleFonts.outfit(color: const Color(0xFFE63946), fontWeight: FontWeight.bold)),
          ),
        ],
      ),
    );

    if (confirmed != true || !mounted) return;

    try {
      await _apiService.deleteMemory(category, key);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Forgot: "$displayName"', style: GoogleFonts.outfit()),
            backgroundColor: const Color(0xFF7B2CBF),
            duration: const Duration(seconds: 2),
          ),
        );
        _loadMemoryData();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Failed to delete memory: $e', style: GoogleFonts.outfit()),
            backgroundColor: Theme.of(context).colorScheme.error,
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 4,
      child: Scaffold(
        backgroundColor: const Color(0xFF0F0F12),
        appBar: AppBar(
          backgroundColor: const Color(0xFF0F0F12),
          elevation: 0,
          leading: IconButton(
            icon: const Icon(Icons.arrow_back, color: Colors.white),
            onPressed: () => Navigator.of(context).pop(),
          ),
          title: Text(
            'Assistant Memory',
            style: GoogleFonts.outfit(
              fontWeight: FontWeight.bold,
              fontSize: 22,
              color: Colors.white,
            ),
          ),
          bottom: TabBar(
            isScrollable: true,
            tabAlignment: TabAlignment.start,
            labelColor: const Color(0xFF00B4D8),
            unselectedLabelColor: Colors.white38,
            indicatorColor: const Color(0xFF00B4D8),
            indicatorSize: TabBarIndicatorSize.tab,
            labelStyle: GoogleFonts.outfit(fontWeight: FontWeight.bold, fontSize: 15),
            tabs: const [
              Tab(text: 'Contacts'),
              Tab(text: 'Preferences'),
              Tab(text: 'Routines'),
              Tab(text: 'Knowledge'),
            ],
          ),
        ),
        body: _isLoading
            ? const Center(
                child: CircularProgressIndicator(
                  valueColor: AlwaysStoppedAnimation<Color>(Color(0xFF00B4D8)),
                ),
              )
            : TabBarView(
                children: [
                  _buildContactsTab(),
                  _buildPreferencesTab(),
                  _buildRoutinesTab(),
                  _buildKnowledgeTab(),
                ],
              ),
      ),
    );
  }

  // ── Tab 1: Contacts ────────────────────────────────────────────────────────

  Widget _buildContactsTab() {
    if (_contacts.isEmpty) {
      return _buildEmptyState('No contacts remembered yet.', Icons.contact_phone_outlined);
    }
    return RefreshIndicator(
      onRefresh: _loadMemoryData,
      color: const Color(0xFF00B4D8),
      child: ListView.builder(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        itemCount: _contacts.length,
        itemBuilder: (context, index) {
          final c = _contacts[index];
          final name = c['name'] as String? ?? 'Unnamed';
          final email = c['email'] as String? ?? '';
          final phone = c['phone'] as String? ?? '';
          final company = c['company'] as String? ?? '';
          final notes = c['notes'] as String? ?? '';

          return Card(
            color: const Color(0xFF1E1E24),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            margin: const EdgeInsets.only(bottom: 12),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          name,
                          style: GoogleFonts.outfit(
                            fontWeight: FontWeight.bold,
                            fontSize: 18,
                            color: Colors.white,
                          ),
                        ),
                        const SizedBox(height: 6),
                        if (email.isNotEmpty)
                          _buildDetailRow(Icons.email_outlined, email),
                        if (phone.isNotEmpty)
                          _buildDetailRow(Icons.phone_outlined, phone),
                        if (company.isNotEmpty)
                          _buildDetailRow(Icons.business_outlined, company),
                        if (notes.isNotEmpty) ...[
                          const SizedBox(height: 8),
                          Container(
                            padding: const EdgeInsets.all(8),
                            decoration: BoxDecoration(
                              color: Colors.black12,
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: Text(
                              notes,
                              style: GoogleFonts.outfit(
                                fontSize: 13,
                                fontStyle: FontStyle.italic,
                                color: const Color(0xFFADB5BD),
                              ),
                            ),
                          )
                        ],
                      ],
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.delete_outline, color: Color(0xFFE63946)),
                    onPressed: () => _deleteEntry('contacts', name, name),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildDetailRow(IconData icon, String text) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(
        children: [
          Icon(icon, size: 14, color: const Color(0xFF00B4D8)),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              text,
              style: GoogleFonts.outfit(fontSize: 14, color: Colors.white70),
            ),
          ),
        ],
      ),
    );
  }

  // ── Tab 2: Preferences ─────────────────────────────────────────────────────

  Widget _buildPreferencesTab() {
    if (_preferences.isEmpty) {
      return _buildEmptyState('No preferences remembered yet.', Icons.settings_outlined);
    }
    return RefreshIndicator(
      onRefresh: _loadMemoryData,
      color: const Color(0xFF00B4D8),
      child: ListView.builder(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        itemCount: _preferences.length,
        itemBuilder: (context, index) {
          final p = _preferences[index];
          final category = p['category'] as String? ?? '';
          final key = p['key'] as String? ?? '';
          final val = p['value']?.toString() ?? 'null';

          final displayKey = '$category/$key';

          return ListTile(
            tileColor: const Color(0xFF1E1E24),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            title: Row(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: const Color(0xFF7B2CBF).withOpacity(0.2),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(
                    category.toUpperCase(),
                    style: GoogleFonts.outfit(
                      fontSize: 10,
                      fontWeight: FontWeight.bold,
                      color: const Color(0xFFD7B9FF),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  key,
                  style: GoogleFonts.outfit(fontWeight: FontWeight.bold, color: Colors.white),
                ),
              ],
            ),
            subtitle: Padding(
              padding: const EdgeInsets.only(top: 6),
              child: Text(
                val,
                style: GoogleFonts.outfit(color: const Color(0xFFADB5BD)),
              ),
            ),
            trailing: IconButton(
              icon: const Icon(Icons.delete_outline, color: Color(0xFFE63946)),
              onPressed: () => _deleteEntry('preferences', displayKey, displayKey),
            ),
          );
        },
      ),
    );
  }

  // ── Tab 3: Routines ────────────────────────────────────────────────────────

  Widget _buildRoutinesTab() {
    if (_routines.isEmpty) {
      return _buildEmptyState('No routine workflows remembered.', Icons.replay_outlined);
    }
    return RefreshIndicator(
      onRefresh: _loadMemoryData,
      color: const Color(0xFF00B4D8),
      child: ListView.builder(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        itemCount: _routines.length,
        itemBuilder: (context, index) {
          final r = _routines[index];
          final name = r['name'] as String? ?? 'unnamed';
          final dynamic rawSteps = r['steps'];
          final List<String> steps = rawSteps is List
              ? List<String>.from(rawSteps)
              : (rawSteps is String
                  ? rawSteps.split(',').map((e) => e.trim()).toList()
                  : []);

          return Card(
            color: const Color(0xFF1E1E24),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            margin: const EdgeInsets.only(bottom: 12),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          name,
                          style: GoogleFonts.outfit(
                            fontWeight: FontWeight.bold,
                            fontSize: 17,
                            color: Colors.white,
                          ),
                        ),
                        const SizedBox(height: 10),
                        Wrap(
                          spacing: 6,
                          runSpacing: 6,
                          children: steps.map((step) {
                            return Chip(
                              label: Text(
                                step,
                                style: GoogleFonts.outfit(
                                  fontSize: 12,
                                  fontWeight: FontWeight.bold,
                                  color: Colors.white70,
                                ),
                              ),
                              backgroundColor: Colors.black26,
                              visualDensity: VisualDensity.compact,
                              padding: EdgeInsets.zero,
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(8),
                              ),
                            );
                          }).toList(),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.delete_outline, color: Color(0xFFE63946)),
                    onPressed: () => _deleteEntry('routines', name, name),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  // ── Tab 4: Knowledge ───────────────────────────────────────────────────────

  Widget _buildKnowledgeTab() {
    if (_knowledge.isEmpty) {
      return _buildEmptyState('No semantic facts stored.', Icons.lightbulb_outline);
    }
    return RefreshIndicator(
      onRefresh: _loadMemoryData,
      color: const Color(0xFF00B4D8),
      child: ListView.builder(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        itemCount: _knowledge.length,
        itemBuilder: (context, index) {
          final k = _knowledge[index];
          final text = k['text'] as String? ?? '';
          final importance = k['importance'] as int? ?? 1;

          return Card(
            color: const Color(0xFF1E1E24),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            margin: const EdgeInsets.only(bottom: 12),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          text,
                          style: GoogleFonts.outfit(
                            fontSize: 15,
                            height: 1.4,
                            color: Colors.white,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Row(
                          children: List.generate(5, (starIdx) {
                            return Icon(
                              Icons.star,
                              size: 14,
                              color: starIdx < importance
                                  ? const Color(0xFFFFB703)
                                  : Colors.white10,
                            );
                          }),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.delete_outline, color: Color(0xFFE63946)),
                    onPressed: () => _deleteEntry('knowledge', text, text),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildEmptyState(String text, IconData icon) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, size: 48, color: Colors.white10),
          const SizedBox(height: 12),
          Text(
            text,
            style: GoogleFonts.outfit(color: Colors.white30, fontSize: 16),
          ),
        ],
      ),
    );
  }
}
