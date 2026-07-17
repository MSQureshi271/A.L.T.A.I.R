import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_fonts/google_fonts.dart';
import '../models/connector.dart';
import '../services/auth_notifier.dart';
import '../services/auth_service.dart';
import '../views/connectors_view.dart';
import '../views/memory_view.dart';


/// Left-side navigation drawer.
///
/// Layout:
///   TOP    — Connector status mini-list + "Manage Connectors" button
///   BOTTOM — Avatar, signed-in email, Sign Out button
class AppDrawer extends ConsumerStatefulWidget {
  const AppDrawer({super.key});

  @override
  ConsumerState<AppDrawer> createState() => _AppDrawerState();
}

class _AppDrawerState extends ConsumerState<AppDrawer> {
  final _authService = AuthService();
  Map<String, bool> _statusMap = {};
  bool _statusLoading = true;

  @override
  void initState() {
    super.initState();
    _loadStatuses();
  }

  Future<void> _loadStatuses() async {
    final status = await _authService.getGoogleStatus();
    final connected = status.connected;
    if (mounted) {
      setState(() {
        _statusMap = {
          'gmail': connected,
          'google_calendar': connected,
        };
        _statusLoading = false;
      });
    }
  }

  Future<void> _handleLogout() async {
    Navigator.pop(context); // close drawer first
    await ref.read(authProvider.notifier).logout();
    // Navigation to LoginView handled reactively by main.dart
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authProvider);
    final email = authState.email;

    return Drawer(
      backgroundColor: const Color(0xFF13131A),
      width: MediaQuery.of(context).size.width * 0.78,
      child: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // ── Header ──────────────────────────────────────────────────────
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 20, 16, 8),
              child: Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: const Color(0xFF7B2CBF).withOpacity(0.15),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: const Icon(
                      Icons.account_balance_wallet_rounded,
                      color: Color(0xFF7B2CBF),
                      size: 20,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      'EXECUTIVE AGENT',
                      style: GoogleFonts.outfit(
                        color: const Color(0xFFF8F9FA),
                        fontSize: 13,
                        fontWeight: FontWeight.w900,
                        letterSpacing: 1.5,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close_rounded,
                        color: Colors.white38, size: 20),
                    onPressed: () => Navigator.pop(context),
                  ),
                ],
              ),
            ),

            Divider(color: Colors.white.withOpacity(0.06)),

            // ── Connectors section ───────────────────────────────────────────
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 12, 20, 8),
              child: Text(
                'CONNECTORS',
                style: GoogleFonts.outfit(
                  color: const Color(0xFF6C757D),
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1.5,
                ),
              ),
            ),

            if (_statusLoading)
              const Padding(
                padding: EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                child: LinearProgressIndicator(
                  backgroundColor: Color(0xFF1E1E24),
                  valueColor:
                      AlwaysStoppedAnimation<Color>(Color(0xFF7B2CBF)),
                ),
              )
            else
              ...kConnectors.map((c) => _DrawerConnectorRow(
                    connector: c,
                    isConnected: _statusMap[c.id] ?? false,
                  )),

            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
              child: GestureDetector(
                onTap: () {
                  Navigator.pop(context);
                  Navigator.push(
                    context,
                    MaterialPageRoute(
                        builder: (_) => const ConnectorsView()),
                  );
                },
                child: Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(vertical: 11),
                  decoration: BoxDecoration(
                    color: const Color(0xFF1E1E24),
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(
                        color: const Color(0xFF7B2CBF).withOpacity(0.3)),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(Icons.tune_rounded,
                          color: Color(0xFF7B2CBF), size: 16),
                      const SizedBox(width: 8),
                      Text(
                        'Manage Connectors',
                        style: GoogleFonts.outfit(
                          color: const Color(0xFF7B2CBF),
                          fontSize: 13,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
            Divider(color: Colors.white.withOpacity(0.06)),

            Padding(
              padding: const EdgeInsets.fromLTRB(20, 12, 20, 4),
              child: Text(
                'ASSISTANT MEMORY',
                style: GoogleFonts.outfit(
                  color: const Color(0xFF6C757D),
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1.5,
                ),
              ),
            ),

            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 2),
              child: ListTile(
                contentPadding: EdgeInsets.zero,
                minLeadingWidth: 24,
                leading: const Icon(Icons.psychology_outlined, color: Color(0xFF00B4D8), size: 18),
                title: Text(
                  'Manage Memory Facts',
                  style: GoogleFonts.outfit(color: Colors.white70, fontSize: 13, fontWeight: FontWeight.w500),
                ),
                onTap: () {
                  Navigator.pop(context); // Close drawer
                  Navigator.push(
                    context,
                    MaterialPageRoute(builder: (_) => const MemoryView()),
                  );
                },
              ),
            ),

            const Spacer(),
            Divider(color: Colors.white.withOpacity(0.06)),

            // ── Bottom: Avatar + Logout ───────────────────────────────────────
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 20),
              child: Row(
                children: [
                  // Avatar circle with initial
                  CircleAvatar(
                    radius: 20,
                    backgroundColor: const Color(0xFF7B2CBF).withOpacity(0.2),
                    child: Text(
                      email.isNotEmpty ? email[0].toUpperCase() : 'U',
                      style: GoogleFonts.outfit(
                        color: const Color(0xFF7B2CBF),
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),

                  // Email
                  Expanded(
                    child: Text(
                      email.isNotEmpty ? email : 'Google Account',
                      style: GoogleFonts.outfit(
                        color: const Color(0xFFADB5BD),
                        fontSize: 13,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),

                  // Sign out button
                  IconButton(
                    tooltip: 'Sign Out',
                    onPressed: _handleLogout,
                    icon: const Icon(
                      Icons.logout_rounded,
                      color: Color(0xFFE63946),
                      size: 20,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ── Single connector row in the drawer ───────────────────────────────────────

class _DrawerConnectorRow extends StatelessWidget {
  final ConnectorConfig connector;
  final bool isConnected;

  const _DrawerConnectorRow({
    required this.connector,
    required this.isConnected,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 4),
      child: Row(
        children: [
          Icon(connector.icon, color: connector.accentColor, size: 18),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              connector.name,
              style: GoogleFonts.outfit(
                color: const Color(0xFFF8F9FA),
                fontSize: 14,
              ),
            ),
          ),
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: isConnected
                  ? const Color(0xFF38B000)
                  : const Color(0xFF6C757D),
              boxShadow: isConnected
                  ? [
                      BoxShadow(
                        color: const Color(0xFF38B000).withOpacity(0.5),
                        blurRadius: 6,
                        spreadRadius: 1,
                      )
                    ]
                  : null,
            ),
          ),
        ],
      ),
    );
  }
}
