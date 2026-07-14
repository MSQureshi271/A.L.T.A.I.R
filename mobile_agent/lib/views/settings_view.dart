import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../services/auth_service.dart';

/// Settings screen — manage Google Workspace connection.
///
/// Accessible from the tune icon in the AppBar of VoiceHomeView.
class SettingsView extends StatefulWidget {
  const SettingsView({super.key});

  @override
  State<SettingsView> createState() => _SettingsViewState();
}

class _SettingsViewState extends State<SettingsView> {
  final _authService = AuthService();

  GoogleAuthStatus _googleStatus = const GoogleAuthStatus(connected: false);
  bool _isLoading = true;
  bool _isActing = false; // True while connect/disconnect request is in flight

  @override
  void initState() {
    super.initState();
    _refreshStatus();
  }

  Future<void> _refreshStatus() async {
    setState(() => _isLoading = true);
    final status = await _authService.getGoogleStatus();
    if (mounted) {
      setState(() {
        _googleStatus = status;
        _isLoading = false;
      });
    }
  }

  Future<void> _connectGoogle() async {
    setState(() => _isActing = true);
    final launched = await _authService.launchGoogleLogin();
    setState(() => _isActing = false);

    if (!launched && mounted) {
      _showSnackbar('Could not open browser. Is the backend running?', isError: true);
    } else if (mounted) {
      _showSnackbar(
        'Browser opened! Complete sign-in, then tap "Check Status" below.',
        isError: false,
      );
    }
  }

  Future<void> _disconnectGoogle() async {
    final confirmed = await _showDisconnectConfirm();
    if (!confirmed || !mounted) return;

    setState(() => _isActing = true);
    final success = await _authService.disconnectGoogle();
    if (mounted) {
      setState(() => _isActing = false);
      if (success) {
        await _refreshStatus();
        _showSnackbar('Google Workspace disconnected.', isError: false);
      } else {
        _showSnackbar('Failed to disconnect. Try again.', isError: true);
      }
    }
  }

  Future<bool> _showDisconnectConfirm() async {
    return await showDialog<bool>(
          context: context,
          builder: (ctx) => AlertDialog(
            backgroundColor: const Color(0xFF1E1E24),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
            title: Text(
              'Disconnect Google?',
              style: GoogleFonts.outfit(color: Colors.white, fontWeight: FontWeight.bold),
            ),
            content: Text(
              'Executive Agent will no longer be able to read your Gmail or Calendar until you reconnect.',
              style: GoogleFonts.outfit(color: const Color(0xFFADB5BD), fontSize: 14),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(ctx, false),
                child: Text('Cancel', style: GoogleFonts.outfit(color: Colors.white60)),
              ),
              TextButton(
                onPressed: () => Navigator.pop(ctx, true),
                child: Text(
                  'Disconnect',
                  style: GoogleFonts.outfit(color: const Color(0xFFE63946)),
                ),
              ),
            ],
          ),
        ) ??
        false;
  }

  void _showSnackbar(String message, {required bool isError}) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message, style: GoogleFonts.outfit()),
        backgroundColor: isError ? const Color(0xFFE63946) : const Color(0xFF38B000),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0F0F12),
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_rounded, color: Colors.white70, size: 20),
          onPressed: () => Navigator.pop(context),
        ),
        title: Text(
          'SETTINGS',
          style: GoogleFonts.outfit(
            color: const Color(0xFFF8F9FA),
            fontSize: 14,
            fontWeight: FontWeight.w800,
            letterSpacing: 1.5,
          ),
        ),
      ),
      body: SafeArea(
        child: _isLoading
            ? const Center(
                child: CircularProgressIndicator(
                  color: Color(0xFF7B2CBF),
                  strokeWidth: 2,
                ),
              )
            : ListView(
                padding: const EdgeInsets.all(20),
                children: [
                  // ── Section header ─────────────────────────────────────────
                  _sectionHeader('Integrations'),
                  const SizedBox(height: 12),

                  // ── Google Workspace card ──────────────────────────────────
                  _buildGoogleCard(),

                  const SizedBox(height: 32),
                  _sectionHeader('Developer Info'),
                  const SizedBox(height: 12),
                  _buildDevInfoCard(),

                  const SizedBox(height: 32),
                  // ── Android emulator tip ───────────────────────────────────
                  _buildEmulatorTip(),
                ],
              ),
      ),
    );
  }

  // ── Widgets ─────────────────────────────────────────────────────────────────

  Widget _sectionHeader(String title) {
    return Text(
      title.toUpperCase(),
      style: GoogleFonts.outfit(
        color: const Color(0xFF6C757D),
        fontSize: 11,
        fontWeight: FontWeight.w700,
        letterSpacing: 1.4,
      ),
    );
  }

  Widget _buildGoogleCard() {
    final isConnected = _googleStatus.connected;
    final hasError = _googleStatus.error;

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1E1E24),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: isConnected
              ? const Color(0xFF38B000).withOpacity(0.4)
              : Colors.white.withOpacity(0.06),
          width: 1.5,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header row
          Padding(
            padding: const EdgeInsets.all(20),
            child: Row(
              children: [
                // Google "G" logo colours
                Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    color: Colors.white,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(Icons.g_mobiledata, color: Color(0xFF4285F4), size: 32),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Google Workspace',
                        style: GoogleFonts.outfit(
                          color: Colors.white,
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                      Text(
                        'Gmail · Google Calendar',
                        style: GoogleFonts.outfit(
                          color: const Color(0xFF6C757D),
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ),
                ),
                // Status chip
                _statusChip(isConnected: isConnected, hasError: hasError),
              ],
            ),
          ),

          // Scopes granted (if connected)
          if (isConnected && _googleStatus.scopes.isNotEmpty) ...[
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20),
              child: Wrap(
                spacing: 8,
                runSpacing: 6,
                children: _googleStatus.scopes
                    .map((s) => _scopeChip(s))
                    .toList(),
              ),
            ),
            const SizedBox(height: 16),
          ],

          const Divider(color: Colors.white10, height: 1),

          // Action buttons
          Padding(
            padding: const EdgeInsets.all(16),
            child: _isActing
                ? const Center(
                    child: SizedBox(
                      height: 24,
                      width: 24,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Color(0xFF7B2CBF),
                      ),
                    ),
                  )
                : Row(
                    children: [
                      // Check Status button (always shown)
                      Expanded(
                        child: _outlineButton(
                          label: 'Check Status',
                          icon: Icons.refresh_rounded,
                          onTap: _refreshStatus,
                        ),
                      ),
                      const SizedBox(width: 10),
                      // Connect or Disconnect
                      Expanded(
                        child: isConnected
                            ? _outlineButton(
                                label: 'Disconnect',
                                icon: Icons.link_off_rounded,
                                onTap: _disconnectGoogle,
                                color: const Color(0xFFE63946),
                              )
                            : _primaryButton(
                                label: 'Connect Google',
                                icon: Icons.add_link_rounded,
                                onTap: _connectGoogle,
                              ),
                      ),
                    ],
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildDevInfoCard() {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1E1E24),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white.withOpacity(0.05)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _devInfoRow('Auth Mode', 'Dev User (Milestone 3)'),
          const SizedBox(height: 10),
          _devInfoRow('User ID', '00000000-…-0001'),
          const SizedBox(height: 10),
          _devInfoRow('Token Storage', 'Local .token_cache.json'),
        ],
      ),
    );
  }

  Widget _devInfoRow(String label, String value) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(label, style: GoogleFonts.outfit(color: const Color(0xFF6C757D), fontSize: 13)),
        Text(
          value,
          style: GoogleFonts.outfit(
            color: const Color(0xFFADB5BD),
            fontSize: 13,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    );
  }

  Widget _buildEmulatorTip() {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF00B4D8).withOpacity(0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFF00B4D8).withOpacity(0.2)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.info_outline_rounded, color: Color(0xFF00B4D8), size: 18),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              'Android Emulator tip: Run `adb reverse tcp:8000 tcp:8000` in a terminal so the emulator browser can reach your local backend on localhost:8000.',
              style: GoogleFonts.outfit(color: const Color(0xFF90E0EF), fontSize: 12),
            ),
          ),
        ],
      ),
    );
  }

  Widget _statusChip({required bool isConnected, required bool hasError}) {
    Color bg;
    Color textColor;
    String label;

    if (hasError) {
      bg = const Color(0xFFE63946).withOpacity(0.15);
      textColor = const Color(0xFFE63946);
      label = 'Error';
    } else if (isConnected) {
      bg = const Color(0xFF38B000).withOpacity(0.15);
      textColor = const Color(0xFF38B000);
      label = 'Connected';
    } else {
      bg = Colors.white.withOpacity(0.06);
      textColor = const Color(0xFF6C757D);
      label = 'Not Connected';
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(20)),
      child: Text(
        label,
        style: GoogleFonts.outfit(color: textColor, fontSize: 11, fontWeight: FontWeight.bold),
      ),
    );
  }

  Widget _scopeChip(String scope) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: const Color(0xFF38B000).withOpacity(0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: const Color(0xFF38B000).withOpacity(0.2)),
      ),
      child: Text(
        scope,
        style: GoogleFonts.outfit(
          color: const Color(0xFF38B000),
          fontSize: 10,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }

  Widget _primaryButton({
    required String label,
    required IconData icon,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 11),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: [Color(0xFF7B2CBF), Color(0xFF5A189A)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, color: Colors.white, size: 16),
            const SizedBox(width: 6),
            Text(
              label,
              style: GoogleFonts.outfit(
                color: Colors.white,
                fontSize: 13,
                fontWeight: FontWeight.bold,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _outlineButton({
    required String label,
    required IconData icon,
    required VoidCallback onTap,
    Color color = const Color(0xFFADB5BD),
  }) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 11),
        decoration: BoxDecoration(
          color: color.withOpacity(0.08),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: color.withOpacity(0.3)),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, color: color, size: 16),
            const SizedBox(width: 6),
            Text(
              label,
              style: GoogleFonts.outfit(
                color: color,
                fontSize: 13,
                fontWeight: FontWeight.bold,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
