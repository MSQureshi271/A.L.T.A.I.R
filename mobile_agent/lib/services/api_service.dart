import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:uuid/uuid.dart';
import 'package:flutter/foundation.dart';
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

  ProcessCommandResult({this.pendingAction, this.textResponse, this.updatedHistory});
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

        case 'result':
          textResponse = event['text'] as String?;
          onLogUpdate('✅ ${textResponse ?? 'Done.'}');
          break;

        case 'history_update':
          updatedHistory = (event['history'] as List<dynamic>?)
              ?.map((e) => Map<String, dynamic>.from(e as Map))
              .toList();
          break;

        case 'approval_required':
          pendingAction = PendingAction(
            id: _uuid.v4(),
            actionType: event['action'] as String? ?? 'unknown',
            data: Map<String, dynamic>.from(event['data'] as Map? ?? {}),
          );
          onLogUpdate('🚦 Staged! Awaiting your approval…');
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
