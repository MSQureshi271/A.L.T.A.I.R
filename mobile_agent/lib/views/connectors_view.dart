import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../models/connector.dart';
import '../services/auth_service.dart';

/// Full-screen page for managing third-party tool connections.
///
/// Driven entirely by the [kConnectors] registry — adding a new tool only
/// requires adding a [ConnectorConfig] to that list.
class ConnectorsView extends StatefulWidget {
  const ConnectorsView({super.key});

  @override
  State<ConnectorsView> createState() => _ConnectorsViewState();
}

class _ConnectorsViewState extends State<ConnectorsView> {
  final _authService = AuthService();

  /// Maps connector id → true/false connection status.
  Map<String, bool> _statusMap = {};
  bool _initialLoading = true;

  @override
  void initState() {
    super.initState();
    _refreshStatuses();
  }

  Future<void> _refreshStatuses() async {
    setState(() => _initialLoading = true);
    final status = await _authService.getGoogleStatus();
    final connected = status.connected;

    // Both Gmail and Google Calendar share the same OAuth token.
    // We treat the connection as on/off for both simultaneously.
    if (mounted) {
      setState(() {
        _statusMap = {
          'gmail': connected,
          'google_calendar': connected,
        };
        _initialLoading = false;
      });
    }
  }

  Future<void> _handleConnect(ConnectorConfig connector) async {
    // For now all connectors use the same Google OAuth flow.
    // Future connectors can dispatch to different auth methods here.
    final launched = await _authService.launchGoogleLogin();
    if (!launched && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Could not open browser. Is the backend running?',
              style: GoogleFonts.outfit()),
          backgroundColor: const Color(0xFFE63946),
        ),
      );
    } else if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Browser opened — complete sign-in then come back.',
            style: GoogleFonts.outfit(),
          ),
          backgroundColor: const Color(0xFF38B000),
          action: SnackBarAction(
            label: 'Check Status',
            textColor: Colors.white,
            onPressed: _refreshStatuses,
          ),
        ),
      );
    }
  }

  Future<void> _handleDisconnect(ConnectorConfig connector) async {
    final confirmed = await _showDisconnectDialog(connector.name);
    if (!confirmed || !mounted) return;

    await _authService.disconnectGoogle();
    await _refreshStatuses();
  }

  Future<bool> _showDisconnectDialog(String name) async {
    return await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            backgroundColor: const Color(0xFF1E1E24),
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            title: Text('Disconnect $name?',
                style: GoogleFonts.outfit(
                    color: Colors.white, fontWeight: FontWeight.bold)),
            content: Text(
              'Executive Agent will no longer be able to access $name on your behalf.',
              style: GoogleFonts.outfit(color: const Color(0xFFADB5BD)),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child:
                    Text('Cancel', style: GoogleFonts.outfit(color: Colors.white60)),
              ),
              ElevatedButton(
                onPressed: () => Navigator.pop(context, true),
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFFE63946),
                  foregroundColor: Colors.white,
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(10)),
                ),
                child: Text('Disconnect', style: GoogleFonts.outfit()),
              ),
            ],
          ),
        ) ??
        false;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0F0F12),
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: Text(
          'Connectors',
          style: GoogleFonts.outfit(
            color: const Color(0xFFF8F9FA),
            fontSize: 20,
            fontWeight: FontWeight.w700,
          ),
        ),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_rounded, color: Colors.white70),
          onPressed: () => Navigator.pop(context),
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh_rounded, color: Colors.white54),
            tooltip: 'Refresh statuses',
            onPressed: _refreshStatuses,
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: _initialLoading
          ? const Center(
              child: CircularProgressIndicator(
                valueColor:
                    AlwaysStoppedAnimation<Color>(Color(0xFF7B2CBF)),
              ),
            )
          : ListView.separated(
              padding: const EdgeInsets.all(20),
              itemCount: kConnectors.length,
              separatorBuilder: (_, _) => const SizedBox(height: 12),
              itemBuilder: (context, i) {
                final connector = kConnectors[i];
                final isConnected = _statusMap[connector.id] ?? false;
                return _ConnectorCard(
                  connector: connector,
                  isConnected: isConnected,
                  onConnect: () => _handleConnect(connector),
                  onDisconnect: () => _handleDisconnect(connector),
                );
              },
            ),
    );
  }
}

// ── ConnectorCard ────────────────────────────────────────────────────────────

class _ConnectorCard extends StatelessWidget {
  final ConnectorConfig connector;
  final bool isConnected;
  final VoidCallback onConnect;
  final VoidCallback onDisconnect;

  const _ConnectorCard({
    required this.connector,
    required this.isConnected,
    required this.onConnect,
    required this.onDisconnect,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: const Color(0xFF1E1E24),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: isConnected
              ? connector.accentColor.withOpacity(0.3)
              : Colors.white.withOpacity(0.06),
        ),
        boxShadow: [
          if (isConnected)
            BoxShadow(
              color: connector.accentColor.withOpacity(0.08),
              blurRadius: 20,
              spreadRadius: 2,
            ),
        ],
      ),
      child: Row(
        children: [
          // Icon badge
          Container(
            width: 48,
            height: 48,
            decoration: BoxDecoration(
              color: connector.accentColor.withOpacity(0.12),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(connector.icon, color: connector.accentColor, size: 24),
          ),
          const SizedBox(width: 14),

          // Name + description
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  connector.name,
                  style: GoogleFonts.outfit(
                    color: const Color(0xFFF8F9FA),
                    fontSize: 15,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  connector.description,
                  style: GoogleFonts.outfit(
                    color: const Color(0xFFADB5BD),
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 12),

          // Status badge + action button
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              // Status pill
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: isConnected
                      ? const Color(0xFF38B000).withOpacity(0.15)
                      : Colors.white.withOpacity(0.05),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 6,
                      height: 6,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: isConnected
                            ? const Color(0xFF38B000)
                            : const Color(0xFF6C757D),
                      ),
                    ),
                    const SizedBox(width: 5),
                    Text(
                      isConnected ? 'Connected' : 'Not Connected',
                      style: GoogleFonts.outfit(
                        color: isConnected
                            ? const Color(0xFF38B000)
                            : const Color(0xFF6C757D),
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 8),

              // Connect / Disconnect button
              GestureDetector(
                onTap: isConnected ? onDisconnect : onConnect,
                child: Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
                  decoration: BoxDecoration(
                    color: isConnected
                        ? const Color(0xFFE63946).withOpacity(0.12)
                        : connector.accentColor.withOpacity(0.12),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(
                      color: isConnected
                          ? const Color(0xFFE63946).withOpacity(0.4)
                          : connector.accentColor.withOpacity(0.4),
                    ),
                  ),
                  child: Text(
                    isConnected ? 'Disconnect' : 'Connect',
                    style: GoogleFonts.outfit(
                      color: isConnected
                          ? const Color(0xFFE63946)
                          : connector.accentColor,
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
