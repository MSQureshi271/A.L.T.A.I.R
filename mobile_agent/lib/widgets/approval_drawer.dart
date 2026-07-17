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

  ActionSchema(
    actionType: 'delete_email',
    displayName: 'Delete Email',
    confirmLabel: 'Approve & Trash Email',
    headerIcon: Icons.delete_outline_rounded,
    accentColor: Color(0xFFE63946),
    fields: [
      ActionField(
        key: 'email_id',
        label: 'Email ID',
        icon: Icons.key_rounded,
      ),
      ActionField(
        key: 'sender',
        label: 'Sender Filter',
        icon: Icons.person_search_rounded,
      ),
      ActionField(
        key: 'subject',
        label: 'Subject Filter',
        icon: Icons.title_rounded,
      ),
    ],
  ),

  ActionSchema(
    actionType: 'reschedule_calendar_event',
    displayName: 'Reschedule Event',
    confirmLabel: 'Approve & Reschedule',
    headerIcon: Icons.edit_calendar_rounded,
    accentColor: Color(0xFFFFB703),
    fields: [
      ActionField(
        key: 'event_id',
        label: 'Event ID',
        icon: Icons.key_rounded,
      ),
      ActionField(
        key: 'title',
        label: 'Event Title Lookup',
        icon: Icons.search_rounded,
      ),
      ActionField(
        key: 'new_date',
        label: 'New Date (YYYY-MM-DD)',
        icon: Icons.calendar_today_rounded,
      ),
      ActionField(
        key: 'new_time',
        label: 'New Start Time (HH:MM)',
        icon: Icons.access_time_rounded,
      ),
      ActionField(
        key: 'new_duration_minutes',
        label: 'New Duration (minutes)',
        icon: Icons.timelapse_rounded,
      ),
    ],
  ),

  ActionSchema(
    actionType: 'delete_calendar_event',
    displayName: 'Cancel Event',
    confirmLabel: 'Approve & Delete Event',
    headerIcon: Icons.calendar_today_rounded, // Wait, delete calendar icon
    accentColor: Color(0xFFE63946),
    fields: [
      ActionField(
        key: 'event_id',
        label: 'Event ID',
        icon: Icons.key_rounded,
      ),
      ActionField(
        key: 'title',
        label: 'Event Title Lookup',
        icon: Icons.search_rounded,
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
  bool _isEditing = false;

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
                    _isEditing ? 'Edit: ${_schema.displayName}' : 'Review: ${_schema.displayName}',
                    style: GoogleFonts.outfit(
                      color: const Color(0xFFF8F9FA),
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
                // Edit/View toggle
                if (_schema.fields.isNotEmpty) ...[
                  IconButton(
                    icon: Icon(
                      _isEditing ? Icons.check_circle_outline_rounded : Icons.edit_rounded,
                      color: _isEditing ? const Color(0xFF38B000) : _schema.accentColor,
                      size: 22,
                    ),
                    onPressed: () {
                      setState(() {
                        _isEditing = !_isEditing;
                      });
                    },
                    tooltip: _isEditing ? 'View Preview' : 'Edit Details',
                  ),
                  const SizedBox(width: 4),
                ],
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
              _isEditing
                  ? 'Modify the details below and toggle back to preview, or approve when ready.'
                  : 'Review the details below before the agent executes this action.',
              style: GoogleFonts.outfit(
                color: const Color(0xFFADB5BD),
                fontSize: 13,
              ),
            ),
            const SizedBox(height: 20),

            // ── Safety Warning Banner ───────────────────────────────────────
            if (widget.action.safetyWarning != null) ...[
              Container(
                margin: const EdgeInsets.only(bottom: 20),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: const Color(0xFFE63946).withOpacity(0.12),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: const Color(0xFFE63946).withOpacity(0.3)),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(
                      Icons.warning_amber_rounded,
                      color: Color(0xFFE63946),
                      size: 22,
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            widget.action.safetyLevel == 'dangerous'
                                ? '⚠️ DANGEROUS ACTION'
                                : '⚠️ SAFETY WARNING',
                            style: GoogleFonts.outfit(
                              color: const Color(0xFFE63946),
                              fontSize: 12,
                              fontWeight: FontWeight.w800,
                              letterSpacing: 0.5,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            widget.action.safetyWarning!,
                            style: GoogleFonts.outfit(
                              color: const Color(0xFFF8F9FA),
                              fontSize: 13,
                              height: 1.3,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ],

            // ── Dynamic fields ──────────────────────────────────────────────
            if (_schema.fields.isEmpty)
              // Fallback for unknown/future action types — show raw JSON data
              _buildRawDataView()
            else
              for (int i = 0; i < _schema.fields.length; i++) ...[
                if (i > 0) const SizedBox(height: 14),
                _isEditing
                    ? _buildField(_schema.fields[i])
                    : _buildReadOnlyField(_schema.fields[i]),
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
                  flex: widget.action.requiresDoubleConfirm ? 2 : 1,
                  child: widget.action.requiresDoubleConfirm
                      ? SlideToConfirm(
                          accentColor: _schema.accentColor,
                          label: 'Slide to Confirm',
                          onConfirmed: () {
                            final updated = _buildUpdatedData();
                            updated['double_confirmed'] = true;
                            widget.onConfirm(updated);
                          },
                        )
                      : Container(
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

  // ── Field builders ──────────────────────────────────────────────────────────

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

  Widget _buildReadOnlyField(ActionField field) {
    final value = _controllers[field.key]?.text ?? '';
    final maxLines = field.type == FieldType.multiLine ? null : 1;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          field.label,
          style: GoogleFonts.outfit(
            color: const Color(0xFF6C757D),
            fontSize: 12,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 6),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          decoration: BoxDecoration(
            color: const Color(0xFF0F0F12).withOpacity(0.4),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: Colors.white.withOpacity(0.02)),
          ),
          child: Row(
            crossAxisAlignment: maxLines == 1 ? CrossAxisAlignment.center : CrossAxisAlignment.start,
            children: [
              Icon(field.icon, color: _schema.accentColor.withOpacity(0.6), size: 18),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  value.isNotEmpty ? value : '(empty)',
                  style: GoogleFonts.outfit(
                    color: value.isNotEmpty ? const Color(0xFFF8F9FA) : const Color(0xFF6C757D),
                    fontSize: 14,
                    height: 1.4,
                  ),
                  maxLines: maxLines,
                ),
              ),
            ],
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

// ── Slide to Confirm Slider ──────────────────────────────────────────────────

class SlideToConfirm extends StatefulWidget {
  final VoidCallback onConfirmed;
  final Color accentColor;
  final String label;

  const SlideToConfirm({
    super.key,
    required this.onConfirmed,
    required this.accentColor,
    required this.label,
  });

  @override
  State<SlideToConfirm> createState() => _SlideToConfirmState();
}

class _SlideToConfirmState extends State<SlideToConfirm> {
  double _position = 0.0;
  bool _confirmed = false;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final double maxDistance = constraints.maxWidth - 56.0; // handle diameter is 50 + margins
        return Container(
          height: 56,
          decoration: BoxDecoration(
            color: const Color(0xFF0F0F12),
            borderRadius: BorderRadius.circular(28),
            border: Border.all(color: widget.accentColor.withOpacity(0.35)),
          ),
          child: Stack(
            children: [
              // Track instructions text
              Center(
                child: Text(
                  _confirmed ? 'CONFIRMED' : widget.label,
                  style: GoogleFonts.outfit(
                    color: _confirmed ? const Color(0xFF38B000) : Colors.white60,
                    fontSize: 13,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
              // Swipe slider handle
              Positioned(
                left: _position + 3.0,
                top: 3,
                bottom: 3,
                child: GestureDetector(
                  onHorizontalDragUpdate: _confirmed
                      ? null
                      : (details) {
                          setState(() {
                            _position = (_position + details.delta.dx).clamp(0.0, maxDistance);
                          });
                        },
                  onHorizontalDragEnd: _confirmed
                      ? null
                      : (details) {
                          if (_position >= maxDistance - 10.0) {
                            setState(() {
                              _position = maxDistance;
                              _confirmed = true;
                            });
                            widget.onConfirmed();
                          } else {
                            setState(() {
                              _position = 0.0;
                            });
                          }
                        },
                  child: Container(
                    width: 48,
                    height: 48,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: widget.accentColor,
                      boxShadow: [
                        BoxShadow(
                          color: widget.accentColor.withOpacity(0.4),
                          blurRadius: 8,
                          offset: const Offset(0, 2),
                        ),
                      ],
                    ),
                    child: const Icon(
                      Icons.arrow_forward_rounded,
                      color: Colors.white,
                      size: 22,
                    ),
                  ),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
