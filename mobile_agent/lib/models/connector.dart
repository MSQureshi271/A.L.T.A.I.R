import 'package:flutter/material.dart';

/// Descriptor for a single third-party tool integration.
///
/// The connector registry ([kConnectors]) is the single place to add new
/// integrations — the ConnectorsView and AppDrawer render dynamically from it.
class ConnectorConfig {
  final String id;
  final String name;
  final String description;
  final IconData icon;
  final Color accentColor;

  const ConnectorConfig({
    required this.id,
    required this.name,
    required this.description,
    required this.icon,
    required this.accentColor,
  });
}

/// The master registry of available connectors.
///
/// Add new tools here — the UI picks them up automatically.
const List<ConnectorConfig> kConnectors = [
  ConnectorConfig(
    id: 'gmail',
    name: 'Gmail',
    description: 'Read, draft and send emails on your behalf.',
    icon: Icons.email_rounded,
    accentColor: Color(0xFF00B4D8),
  ),
  ConnectorConfig(
    id: 'google_calendar',
    name: 'Google Calendar',
    description: 'Create and read calendar events.',
    icon: Icons.calendar_month_rounded,
    accentColor: Color(0xFF38B000),
  ),
  // ── Future connectors ──────────────────────────────────────────────────────
  // ConnectorConfig(
  //   id: 'notion',
  //   name: 'Notion',
  //   description: 'Read and write Notion pages and databases.',
  //   icon: Icons.note_rounded,
  //   accentColor: Color(0xFFFFB703),
  // ),
];
