import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../models/agent_state.dart';

// ── Action Field Schema ─────────────────────────────────────────────────────
// This is the single place to define how each action type is displayed and
// edited in the approval drawer. Adding a new tool only requires adding a
// new ActionSchema entry here — no other UI code needs to change.

enum FieldType { singleLine, multiLine, readOnly }

class ActionField {
  final String key;       // maps to data['key']
  final String label;
  final IconData icon;
  final FieldType type;

  const ActionField({
    required this.key,
    required this.label,
    required this.icon,
    this.type = FieldType.singleLine,
  });
}

class ActionSchema {
  final String actionType;    // matches PendingAction.actionType
  final String displayName;   // e.g. 'Email Draft'
  final String confirmLabel;  // button label e.g. 'Approve & Send'
  final IconData headerIcon;
  final Color accentColor;
  final List<ActionField> fields;

  const ActionSchema({
    required this.actionType,
    required this.displayName,
    required this.confirmLabel,
    required this.headerIcon,
    required this.accentColor,
    required this.fields,
  });
}

// ── Registry ─────────────────────────────────────────────────────────────────
// Add new action schemas here as new tools are added in future milestones.

const _kUnknownSchema = ActionSchema(
  actionType: '_unknown',
  displayName: 'Agent Action',
  confirmLabel: 'Approve & Execute',
  headerIcon: Icons.auto_fix_high_rounded,
  accentColor: Color(0xFF7B2CBF),
  fields: [],
);

const List<ActionSchema> _kActionSchemas = [
  ActionSchema(
    actionType: 'send_email',
    displayName: 'Email Draft',
    confirmLabel: 'Approve & Send Email',
    headerIcon: Icons.email_rounded,
    accentColor: Color(0xFF00B4D8),
    fields: [
      ActionField(
        key: 'to',
        label: 'Recipient (To)',
        icon: Icons.alternate_email_rounded,
      ),
      ActionField(
        key: 'subject',
        label: 'Subject',
        icon: Icons.title_rounded,
      ),
      ActionField(
        key: 'body',
        label: 'Email Body',
        icon: Icons.article_rounded,
        type: FieldType.multiLine,
      ),
    ],
  ),

  ActionSchema(
    actionType: 'create_calendar_event',
    displayName: 'Calendar Event',
    confirmLabel: 'Approve & Create Event',
    headerIcon: Icons.event_rounded,
    accentColor: Color(0xFF38B000),
    fields: [
      ActionField(
        key: 'title',
        label: 'Event Title',
        icon: Icons.title_rounded,
      ),
      ActionField(
        key: 'date',
        label: 'Date (YYYY-MM-DD)',
        icon: Icons.calendar_today_rounded,
      ),
      ActionField(
        key: 'time',
        label: 'Start Time (HH:MM)',
        icon: Icons.access_time_rounded,
      ),
      ActionField(
        key: 'duration_minutes',
        label: 'Duration (minutes)',
        icon: Icons.timelapse_rounded,
      ),
      ActionField(
        key: 'attendees',
        label: 'Attendees (comma-separated)',
        icon: Icons.people_rounded,
        type: FieldType.multiLine,
      ),
    ],
  ),

  // ── Future tool schemas go here ──────────────────────────────────────────
  // Example:
  // ActionSchema(
  //   actionType: 'create_task',
  //   displayName: 'Task',
  //   confirmLabel: 'Approve & Create Task',
  //   headerIcon: Icons.task_alt_rounded,
  //   accentColor: Color(0xFFFFB703),
  //   fields: [
  //     ActionField(key: 'title',    label: 'Title',    icon: Icons.title_rounded),
  //     ActionField(key: 'due_date', label: 'Due Date', icon: Icons.event_rounded),
  //     ActionField(key: 'notes',    label: 'Notes',    icon: Icons.notes_rounded,
  //                 type: FieldType.multiLine),
  //   ],
  // ),
];

ActionSchema _schemaFor(String actionType) {
  return _kActionSchemas.firstWhere(
    (s) => s.actionType == actionType,
    orElse: () => _kUnknownSchema,
  );
}


// ── ApprovalDrawer ──────────────────────────────────────────────────────────

class ApprovalDrawer extends StatefulWidget {
  final PendingAction action;
  final VoidCallback onCancel;
  final Function(Map<String, dynamic> updatedData) onConfirm;

  const ApprovalDrawer({
    super.key,
    required this.action,
    required this.onCancel,
    required this.onConfirm,
  });

  @override
  State<ApprovalDrawer> createState() => _ApprovalDrawerState();
}

class _ApprovalDrawerState extends State<ApprovalDrawer> {
  late ActionSchema _schema;
  late Map<String, TextEditingController> _controllers;

  @override
  void initState() {
    super.initState();
    _schema = _schemaFor(widget.action.actionType);

    // Build one TextEditingController per field defined in the schema
    _controllers = {
      for (final field in _schema.fields)
        field.key: TextEditingController(
          text: _stringValue(widget.action.data[field.key]),
        ),
    };
  }

  /// Safely converts any data value to a display string (handles lists, etc.)
  String _stringValue(dynamic value) {
    if (value == null) return '';
    if (value is List) return value.join(', ');
    return value.toString();
  }

  @override
  void dispose() {
    for (final c in _controllers.values) {
      c.dispose();
    }
    super.dispose();
  }

  Map<String, dynamic> _buildUpdatedData() {
    // Reconstruct data map from controllers; preserve original types where possible
    final updated = Map<String, dynamic>.from(widget.action.data);
    for (final field in _schema.fields) {
      final text = _controllers[field.key]?.text ?? '';
      final original = widget.action.data[field.key];
      if (original is List) {
        // Re-split comma-separated values back into a list
        updated[field.key] =
            text.split(',').map((e) => e.trim()).where((e) => e.isNotEmpty).toList();
      } else if (original is int) {
        updated[field.key] = int.tryParse(text) ?? original;
      } else {
        updated[field.key] = text;
      }
    }
    return updated;
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        top: 24,
        bottom: MediaQuery.of(context).viewInsets.bottom + 24,
      ),
      decoration: const BoxDecoration(
        color: Color(0xFF1E1E24),
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(24),
          topRight: Radius.circular(24),
        ),
      ),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Drag handle
            Center(
              child: Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: Colors.white24,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            const SizedBox(height: 20),

            // ── Header ─────────────────────────────────────────────────────
            Row(
              children: [
                Icon(_schema.headerIcon, color: _schema.accentColor, size: 24),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'Review: ${_schema.displayName}',
                    style: GoogleFonts.outfit(
                      color: const Color(0xFFF8F9FA),
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
                // Action type badge
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: _schema.accentColor.withOpacity(0.15),
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(color: _schema.accentColor.withOpacity(0.35)),
                  ),
                  child: Text(
                    _schema.displayName.toUpperCase(),
                    style: GoogleFonts.outfit(
                      color: _schema.accentColor,
                      fontSize: 9,
                      fontWeight: FontWeight.w800,
                      letterSpacing: 0.8,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              'Review and edit the details below before the agent executes this action.',
              style: GoogleFonts.outfit(
                color: const Color(0xFFADB5BD),
                fontSize: 13,
              ),
            ),
            const SizedBox(height: 20),

            // ── Dynamic fields ──────────────────────────────────────────────
            if (_schema.fields.isEmpty)
              // Fallback for unknown/future action types — show raw JSON data
              _buildRawDataView()
            else
              for (int i = 0; i < _schema.fields.length; i++) ...[
                if (i > 0) const SizedBox(height: 14),
                _buildField(_schema.fields[i]),
              ],

            const SizedBox(height: 24),

            // ── Action buttons ──────────────────────────────────────────────
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: widget.onCancel,
                    style: OutlinedButton.styleFrom(
                      foregroundColor: const Color(0xFFE63946),
                      side: const BorderSide(color: Color(0xFFE63946)),
                      padding: const EdgeInsets.symmetric(vertical: 14),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12)),
                    ),
                    child: Text(
                      'Cancel',
                      style: GoogleFonts.outfit(fontWeight: FontWeight.bold),
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Container(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        colors: [
                          _schema.accentColor,
                          _schema.accentColor.withOpacity(0.75),
                        ],
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                      ),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: ElevatedButton(
                      onPressed: () => widget.onConfirm(_buildUpdatedData()),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.transparent,
                        shadowColor: Colors.transparent,
                        padding: const EdgeInsets.symmetric(vertical: 14),
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12)),
                      ),
                      child: Text(
                        _schema.confirmLabel,
                        style: GoogleFonts.outfit(
                          color: Colors.white,
                          fontWeight: FontWeight.bold,
                          fontSize: 13,
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  // ── Field builder ──────────────────────────────────────────────────────────

  Widget _buildField(ActionField field) {
    final controller = _controllers[field.key]!;
    final isReadOnly = field.type == FieldType.readOnly;
    final maxLines = field.type == FieldType.multiLine ? 4 : 1;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          field.label,
          style: GoogleFonts.outfit(
            color: const Color(0xFFADB5BD),
            fontSize: 12,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 6),
        TextField(
          controller: controller,
          readOnly: isReadOnly,
          maxLines: maxLines,
          style: GoogleFonts.outfit(
            color: isReadOnly
                ? const Color(0xFF6C757D)
                : const Color(0xFFF8F9FA),
            fontSize: 14,
          ),
          decoration: InputDecoration(
            prefixIcon: Icon(field.icon, color: Colors.white30, size: 18),
            filled: true,
            fillColor: isReadOnly
                ? const Color(0xFF0F0F12).withOpacity(0.5)
                : const Color(0xFF0F0F12),
            contentPadding: const EdgeInsets.all(14),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide:
                  BorderSide(color: Colors.white.withOpacity(0.05)),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
              borderSide: BorderSide(color: _schema.accentColor),
            ),
          ),
        ),
      ],
    );
  }

  // Fallback for completely unknown action types — shows raw key/value pairs
  Widget _buildRawDataView() {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF0F0F12),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.white.withOpacity(0.05)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: widget.action.data.entries.map((entry) {
          return Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${entry.key}: ',
                  style: GoogleFonts.outfit(
                    color: const Color(0xFF6C757D),
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                Expanded(
                  child: Text(
                    _stringValue(entry.value),
                    style: GoogleFonts.outfit(
                      color: const Color(0xFFADB5BD),
                      fontSize: 12,
                    ),
                  ),
                ),
              ],
            ),
          );
        }).toList(),
      ),
    );
  }
}
