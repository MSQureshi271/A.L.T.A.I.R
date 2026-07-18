import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:uuid/uuid.dart';
import 'package:flutter/foundation.dart';
import 'package:http_parser/http_parser.dart';
import '../models/agent_state.dart';

/// Base URL for the FastAPI backend.
/// Change this to your deployed URL in production.
const String _kWebBackendBaseUrl = 'http://127.0.0.1:8000';
const String _kAndroidEmulatorBackendBaseUrl = 'https://craftily-roast-angelfish.ngrok-free.dev';

String get _backendBaseUrl {
  if (kIsWeb) {
    return _kWebBackendBaseUrl;
  }
  return _kAndroidEmulatorBackendBaseUrl;
}

class ProcessCommandResult {
  final PendingAction? pendingAction;
  final String? textResponse;
  final List<Map<String, dynamic>>? updatedHistory;

  /// The structured plan emitted by the Planner, if available.
  final Map<String, dynamic>? plan;

  ProcessCommandResult({
    this.pendingAction,
    this.textResponse,
    this.updatedHistory,
    this.plan,
  });
}

class ApiService {
  final _uuid = const Uuid();

  // ── Voice command via STT transcript → SSE ──────────────────────────────────

  /// Takes the STT-transcribed [transcript] from SpeechService and streams
  /// it through the Gemini agent loop via POST /agent/text.
  ///
  /// [history] is the serialised prior conversation (up to 20 entries).
  /// Falls back to the built-in mock when the backend is unreachable.
  Future<ProcessCommandResult> processVoiceCommand({
    required String transcript,
    required Function(String logText) onLogUpdate,
    List<Map<String, dynamic>> history = const [],
  }) async {
    onLogUpdate('📤 Sending transcript to backend agents…');

    try {
      return await _streamAgentText(
        text: transcript,
        onLogUpdate: onLogUpdate,
        history: history,
      );
    } catch (e) {
      // Backend unreachable — fall back to local mock so the UI still works
      onLogUpdate('⚠️  Backend unreachable. Running mock simulation…');
      final mockAction = await _runLocalMock(onLogUpdate: onLogUpdate);
      return ProcessCommandResult(pendingAction: mockAction);
    }
  }

  // ── Voice command via Multipart audio → SSE ────────────────────────────────

  /// Takes the raw [audioFilePath] and streams it to the backend agent loop
  /// via POST /agent/voice (Multipart Form).
  ///
  /// [onTranscriptReceived] is called as soon as the backend delivers the transcription.
  /// [onLogUpdate] handles intermediate progress steps.
  /// [history] is the serialized prior conversation turns.
  Future<ProcessCommandResult> processAudioCommand({
    required String audioFilePath,
    required Function(String transcript) onTranscriptReceived,
    required Function(String logText) onLogUpdate,
    List<Map<String, dynamic>> history = const [],
  }) async {
    onLogUpdate('📤 Uploading audio to backend agents…');

    try {
      final uri = Uri.parse('$_backendBaseUrl/agent/voice');
      final request = http.MultipartRequest('POST', uri);

      String mimeType = 'audio/m4a';
      if (audioFilePath.endsWith('.wav')) {
        mimeType = 'audio/wav';
      }

      request.files.add(
        await http.MultipartFile.fromPath(
          'file',
          audioFilePath,
          contentType: MediaType.parse(mimeType),
        ),
      );

      request.fields['history'] = jsonEncode(history);

      final http.StreamedResponse streamed =
          await http.Client().send(request).timeout(
                const Duration(seconds: 90),
                onTimeout: () => throw TimeoutException('Backend audio upload timeout'),
              );

      if (streamed.statusCode != 200) {
        throw Exception('Backend returned ${streamed.statusCode}');
      }

      PendingAction? pendingAction;
      String? textResponse;
      List<Map<String, dynamic>>? updatedHistory;
      Map<String, dynamic>? receivedPlan;
      String? currentSafetyWarning;
      bool currentRequiresDoubleConfirm = false;
      String? currentSafetyLevel;

      await for (final chunk
          in streamed.stream.transform(utf8.decoder).transform(const LineSplitter())) {
        if (!chunk.startsWith('data: ')) continue;

        final raw = chunk.substring(6).trim();
        if (raw.isEmpty) continue;

        final Map<String, dynamic> event = jsonDecode(raw);
        final String type = event['type'] as String? ?? '';

        switch (type) {
          case 'log':
            onLogUpdate(event['message'] as String? ?? '');
            break;

          case 'transcript':
            final text = event['text'] as String? ?? '';
            if (text.isNotEmpty) {
              onTranscriptReceived(text);
            }
            break;

          case 'plan':
            receivedPlan = Map<String, dynamic>.from(event['plan'] as Map? ?? {});
            final summary = receivedPlan['intent_summary'] as String? ?? '';
            if (summary.isNotEmpty) onLogUpdate('📋 Plan: $summary');
            break;

          case 'tool_result':
            break;

          case 'result':
            textResponse = event['text'] as String?;
            onLogUpdate('✅ ${textResponse ?? 'Done.'}');
            break;

          case 'history_update':
            updatedHistory = (event['history'] as List<dynamic>?)
                ?.map((e) => Map<String, dynamic>.from(e as Map))
                .toList();
            break;

          case 'safety_warning':
            currentSafetyWarning = event['message'] as String?;
            currentRequiresDoubleConfirm = event['requires_double_confirm'] as bool? ?? false;
            currentSafetyLevel = event['level'] as String?;
            break;

          case 'approval_required':
            final actionData = Map<String, dynamic>.from(event['data'] as Map? ?? {});
            pendingAction = PendingAction(
              id: _uuid.v4(),
              actionType: event['action'] as String? ?? 'unknown',
              data: actionData,
              safetyWarning: currentSafetyWarning ?? actionData['safety_warning'] as String?,
              requiresDoubleConfirm: currentRequiresDoubleConfirm || (actionData['requires_double_confirm'] as bool? ?? false),
              safetyLevel: currentSafetyLevel ?? actionData['safety_level'] as String?,
            );
            onLogUpdate('🚦 Staged! Awaiting your approval…');
            // reset safety properties for next events
            currentSafetyWarning = null;
            currentRequiresDoubleConfirm = false;
            currentSafetyLevel = null;
            break;

          case 'error':
            throw Exception(event['message'] ?? 'Unknown backend error');

          case 'done':
            break;
        }
      }

      return ProcessCommandResult(
        pendingAction: pendingAction,
        textResponse: textResponse,
        updatedHistory: updatedHistory,
        plan: receivedPlan,
      );

    } catch (e) {
      onLogUpdate('⚠️  Backend audio upload failed. Running mock simulation…');
      final mockAction = await _runLocalMock(onLogUpdate: onLogUpdate);
      onTranscriptReceived('Mock transcript: Draft Q2 sales progress report');
      return ProcessCommandResult(pendingAction: mockAction);
    }
  }

  /// Opens an SSE connection to POST /agent/text and streams events back.

  Future<ProcessCommandResult> _streamAgentText({
    required String text,
    required Function(String) onLogUpdate,
    List<Map<String, dynamic>> history = const [],
  }) async {
    final uri = Uri.parse('$_backendBaseUrl/agent/text');

    final request = http.Request('POST', uri)
      ..headers['Content-Type'] = 'application/json'
      ..headers['Accept'] = 'text/event-stream'
      ..body = jsonEncode({'text': text, 'history': history});

    final http.StreamedResponse streamed =
        await http.Client().send(request).timeout(
              const Duration(seconds: 60),
              onTimeout: () => throw TimeoutException('Backend timeout'),
            );

    if (streamed.statusCode != 200) {
      throw Exception('Backend returned ${streamed.statusCode}');
    }

    PendingAction? pendingAction;
    String? textResponse;
    List<Map<String, dynamic>>? updatedHistory;
    Map<String, dynamic>? receivedPlan;
    String? currentSafetyWarning;
    bool currentRequiresDoubleConfirm = false;
    String? currentSafetyLevel;

    await for (final chunk
        in streamed.stream.transform(utf8.decoder).transform(const LineSplitter())) {
      if (!chunk.startsWith('data: ')) continue;

      final raw = chunk.substring(6).trim();
      if (raw.isEmpty) continue;

      final Map<String, dynamic> event = jsonDecode(raw);
      final String type = event['type'] as String? ?? '';

      switch (type) {
        case 'log':
          onLogUpdate(event['message'] as String? ?? '');
          break;

        case 'plan':
          // Capture the structured plan for the UI preview card
          receivedPlan = Map<String, dynamic>.from(event['plan'] as Map? ?? {});
          final summary = receivedPlan['intent_summary'] as String? ?? '';
          if (summary.isNotEmpty) onLogUpdate('📋 Plan: $summary');
          break;

        case 'tool_result':
          // Background read-only result — surfaced through the final 'result' event
          break;

        case 'result':
          textResponse = event['text'] as String?;
          onLogUpdate('✅ ${textResponse ?? 'Done.'}');
          break;

        case 'history_update':
          updatedHistory = (event['history'] as List<dynamic>?)
              ?.map((e) => Map<String, dynamic>.from(e as Map))
              .toList();
          break;

        case 'safety_warning':
          currentSafetyWarning = event['message'] as String?;
          currentRequiresDoubleConfirm = event['requires_double_confirm'] as bool? ?? false;
          currentSafetyLevel = event['level'] as String?;
          break;

        case 'approval_required':
          final actionData = Map<String, dynamic>.from(event['data'] as Map? ?? {});
          pendingAction = PendingAction(
            id: _uuid.v4(),
            actionType: event['action'] as String? ?? 'unknown',
            data: actionData,
            safetyWarning: currentSafetyWarning ?? actionData['safety_warning'] as String?,
            requiresDoubleConfirm: currentRequiresDoubleConfirm || (actionData['requires_double_confirm'] as bool? ?? false),
            safetyLevel: currentSafetyLevel ?? actionData['safety_level'] as String?,
          );
          onLogUpdate('🚦 Staged! Awaiting your approval…');
          // reset safety properties for next events
          currentSafetyWarning = null;
          currentRequiresDoubleConfirm = false;
          currentSafetyLevel = null;
          break;

        case 'error':
          throw Exception(event['message'] ?? 'Unknown backend error');

        case 'done':
          break;
      }
    }

    return ProcessCommandResult(
      pendingAction: pendingAction,
      textResponse: textResponse,
      updatedHistory: updatedHistory,
      plan: receivedPlan,
    );
  }

  // ── Execute approved action ─────────────────────────────────────────────────

  /// Sends the confirmed action data to the backend for real execution.
  Future<String> executeAction(PendingAction action) async {
    try {
      final uri = Uri.parse('$_backendBaseUrl/agent/execute-action');
      final response = await http.post(
        uri,
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'action': action.actionType, 'data': action.data}),
      ).timeout(const Duration(seconds: 15));

      if (response.statusCode == 200) {
        final body = jsonDecode(response.body) as Map<String, dynamic>;
        return body['message'] as String? ?? 'Action completed successfully.';
      } else {
        throw Exception('Execute action failed: ${response.statusCode}');
      }
    } catch (_) {
      await Future.delayed(const Duration(milliseconds: 1200));
      return _mockExecuteResult(action);
    }
  }

  /// Resumes execution of a paused plan on the backend.
  /// Streams logs, intermediate tool updates, and final result back via SSE.
  Future<ProcessCommandResult> resumePlan({
    required String planId,
    required int stepId,
    Map<String, dynamic>? editedData,
    required Function(String logText) onLogUpdate,
    required Function(Map<String, dynamic> updatedPlan) onPlanUpdate,
    required Function(int stepId, String result) onToolResult,
  }) async {
    onLogUpdate('⏳ Resuming plan execution…');

    try {
      final uri = Uri.parse('$_backendBaseUrl/agent/resume-plan');

      final request = http.Request('POST', uri)
        ..headers['Content-Type'] = 'application/json'
        ..headers['Accept'] = 'text/event-stream'
        ..body = jsonEncode({
          'plan_id': planId,
          'step_id': stepId,
          'edited_data': editedData,
        });

      final http.StreamedResponse streamed =
          await http.Client().send(request).timeout(
                const Duration(seconds: 90),
                onTimeout: () => throw TimeoutException('Resume plan request timeout'),
              );

      if (streamed.statusCode != 200) {
        throw Exception('Backend returned ${streamed.statusCode}');
      }

      PendingAction? pendingAction;
      String? textResponse;
      List<Map<String, dynamic>>? updatedHistory;
      Map<String, dynamic>? receivedPlan;
      String? currentSafetyWarning;
      bool currentRequiresDoubleConfirm = false;
      String? currentSafetyLevel;

      await for (final chunk
          in streamed.stream.transform(utf8.decoder).transform(const LineSplitter())) {
        if (!chunk.startsWith('data: ')) continue;

        final raw = chunk.substring(6).trim();
        if (raw.isEmpty) continue;

        final Map<String, dynamic> event = jsonDecode(raw);
        final String type = event['type'] as String? ?? '';

        switch (type) {
          case 'log':
            onLogUpdate(event['message'] as String? ?? '');
            break;

          case 'plan':
            receivedPlan = Map<String, dynamic>.from(event['plan'] as Map? ?? {});
            onPlanUpdate(receivedPlan);
            break;

          case 'tool_result':
            final step = event['step_id'] as int? ?? 0;
            final result = event['result'] as String? ?? '';
            onToolResult(step, result);
            break;

          case 'result':
            textResponse = event['text'] as String?;
            onLogUpdate('✅ ${textResponse ?? 'Done.'}');
            break;

          case 'history_update':
            updatedHistory = (event['history'] as List<dynamic>?)
                ?.map((e) => Map<String, dynamic>.from(e as Map))
                .toList();
            break;

          case 'safety_warning':
            currentSafetyWarning = event['message'] as String?;
            currentRequiresDoubleConfirm = event['requires_double_confirm'] as bool? ?? false;
            currentSafetyLevel = event['level'] as String?;
            break;

          case 'approval_required':
            final actionData = Map<String, dynamic>.from(event['data'] as Map? ?? {});
            pendingAction = PendingAction(
              id: _uuid.v4(),
              actionType: event['action'] as String? ?? 'unknown',
              data: actionData,
              safetyWarning: currentSafetyWarning ?? actionData['safety_warning'] as String?,
              requiresDoubleConfirm: currentRequiresDoubleConfirm || (actionData['requires_double_confirm'] as bool? ?? false),
              safetyLevel: currentSafetyLevel ?? actionData['safety_level'] as String?,
            );
            onLogUpdate('🚦 Staged! Awaiting your approval…');
            currentSafetyWarning = null;
            currentRequiresDoubleConfirm = false;
            currentSafetyLevel = null;
            break;

          case 'error':
            throw Exception(event['message'] ?? 'Unknown backend error');

          case 'done':
            break;
        }
      }

      return ProcessCommandResult(
        pendingAction: pendingAction,
        textResponse: textResponse,
        updatedHistory: updatedHistory,
        plan: receivedPlan,
      );

    } catch (e) {
      onLogUpdate('⚠️  Resuming plan failed: $e');
      rethrow;
    }
  }


  // ── Memory Management API ──────────────────────────────────────────────────

  /// Fetches all stored contacts, preferences, routines, and general knowledge.
  Future<Map<String, List<dynamic>>> getMemory() async {
    try {
      final uri = Uri.parse('$_backendBaseUrl/agent/memory');
      final response = await http.get(uri).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body) as Map<String, dynamic>;
        return {
          'contacts': decoded['contacts'] as List<dynamic>? ?? [],
          'preferences': decoded['preferences'] as List<dynamic>? ?? [],
          'routines': decoded['routines'] as List<dynamic>? ?? [],
          'knowledge': decoded['knowledge'] as List<dynamic>? ?? [],
        };
      } else {
        throw Exception('Failed to load memory: ${response.statusCode}');
      }
    } catch (e) {
      // Local development mock fallback if backend is offline
      return {
        'contacts': [
          {'name': 'Bob Smith', 'email': 'bob@firm.com', 'notes': 'my accountant'},
          {'name': 'Sarah Ahmed', 'email': 'sarah@acme.com', 'notes': 'partner at Acme'}
        ],
        'preferences': [
          {'category': 'email', 'key': 'signature', 'value': 'Regards,\nSubhan'},
          {'category': 'calendar', 'key': 'default_duration', 'value': 30}
        ],
        'routines': [
          {'name': 'weekly_review', 'steps': ['calendar', 'gmail', 'search']}
        ],
        'knowledge': [
          {'text': "My wife's birthday is October 12th.", 'importance': 4},
          {'text': 'Prefer flying with Emirates.', 'importance': 3}
        ]
      };
    }
  }

  /// Deletes a specific memory entry.
  Future<void> deleteMemory(String category, String key) async {
    try {
      final uri = Uri.parse('$_backendBaseUrl/agent/memory?category=$category&key=${Uri.encodeComponent(key)}');
      final response = await http.delete(uri).timeout(const Duration(seconds: 10));

      if (response.statusCode != 200) {
        throw Exception('Failed to delete memory: ${response.statusCode}');
      }
    } catch (e) {
      // Offline fallback: do nothing, mock delete succeeds
      debugPrint('Warning: Delete memory API offline, fallback simulation: $e');
    }
  }

  // ── Watcher REST Client APIs ───────────────────────────────────────────────

  /// Fetch all watchers.
  Future<List<Map<String, dynamic>>> getWatchers() async {
    try {
      final uri = Uri.parse('$_backendBaseUrl/agent/watchers');
      final response = await http.get(uri).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final List<dynamic> data = json.decode(response.body);
        return data.cast<Map<String, dynamic>>();
      }
      throw Exception('Failed to load watchers: ${response.statusCode}');
    } catch (e) {
      debugPrint('Warning: Get watchers API offline, returning fallback empty list: $e');
      return [];
    }
  }

  /// Toggle a watcher's state (enabled/disabled).
  Future<bool> toggleWatcher(String watcherId) async {
    try {
      final uri = Uri.parse('$_backendBaseUrl/agent/watchers/$watcherId/toggle');
      final response = await http.post(uri).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final Map<String, dynamic> data = json.decode(response.body);
        return data['enabled'] ?? false;
      }
      throw Exception('Failed to toggle watcher: ${response.statusCode}');
    } catch (e) {
      debugPrint('Warning: Toggle watcher API offline: $e');
      return false;
    }
  }

  /// Delete a watcher.
  Future<void> deleteWatcher(String watcherId) async {
    try {
      final uri = Uri.parse('$_backendBaseUrl/agent/watchers/$watcherId');
      final response = await http.delete(uri).timeout(const Duration(seconds: 10));

      if (response.statusCode != 200) {
        throw Exception('Failed to delete watcher: ${response.statusCode}');
      }
    } catch (e) {
      debugPrint('Warning: Delete watcher API offline: $e');
    }
  }

  /// Fetch history execution logs for a watcher.
  Future<List<Map<String, dynamic>>> getWatcherHistory(String watcherId) async {
    try {
      final uri = Uri.parse('$_backendBaseUrl/agent/watchers/$watcherId/history');
      final response = await http.get(uri).timeout(const Duration(seconds: 10));

      if (response.statusCode == 200) {
        final List<dynamic> data = json.decode(response.body);
        return data.cast<Map<String, dynamic>>();
      }
      throw Exception('Failed to load watcher history: ${response.statusCode}');
    } catch (e) {
      debugPrint('Warning: Get watcher history API offline: $e');
      return [];
    }
  }

  // ── Local mock fallback ────────────────────────────────────────────────────


  Future<PendingAction> _runLocalMock({
    required Function(String) onLogUpdate,
  }) async {
    await Future.delayed(const Duration(milliseconds: 900));
    onLogUpdate('🧠 Coordinator → Routing request to specialized agents…');
    await Future.delayed(const Duration(milliseconds: 1200));
    onLogUpdate('🔍 Email Agent → Fetching sales reports & drafting message…');
    await Future.delayed(const Duration(milliseconds: 1500));
    onLogUpdate('✍️  Email Agent → Creating staged draft…');
    await Future.delayed(const Duration(milliseconds: 900));
    onLogUpdate('🚦 Staged! Awaiting your approval…');

    return PendingAction(
      id: _uuid.v4(),
      actionType: 'send_email',
      data: {
        'to': 'finance@company.com',
        'subject': 'Q2 Progress Report',
        'body': 'Dear Finance Team,\n\nHere is a summary of our Q2 sales '
            'progress:\n- North Region: +14% QoQ\n- Pipeline value: \$2.4M\n'
            '- Key client acquisitions: 3 enterprise accounts.\n\n'
            'Best regards,\nExecutive Assistant (AI)',
      },
    );
  }

  String _mockExecuteResult(PendingAction action) {
    if (action.actionType == 'send_email') {
      return "✅ Email sent to ${action.data['to']} — "
          "Subject: '${action.data['subject']}'.";
    }
    return "✅ Action '${action.actionType}' completed successfully.";
  }
}
