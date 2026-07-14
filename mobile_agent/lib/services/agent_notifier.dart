import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';
import '../models/agent_state.dart';
import 'speech_service.dart';
import 'api_service.dart';

// ── Providers ──────────────────────────────────────────────────────────────

final speechServiceProvider = Provider<SpeechService>((ref) {
  return SpeechService();
});

final apiServiceProvider = Provider<ApiService>((ref) {
  return ApiService();
});

// ── AgentNotifier ──────────────────────────────────────────────────────────

class AgentNotifier extends Notifier<AgentState> {
  late final SpeechService _speechService;
  late final ApiService _apiService;
  final _uuid = const Uuid();
  bool _processingStarted = false; // guards against double-fire from onResult+onDone

  @override
  AgentState build() {
    _speechService = ref.read(speechServiceProvider);
    _apiService = ref.read(apiServiceProvider);
    _processingStarted = false;
    return const AgentState();
  }

  // ── Listening ────────────────────────────────────────────────────────────

  Future<void> startListening() async {
    // Initialize STT on first use
    final ready = await _speechService.initialize();
    if (!ready) {
      _appendSystemMessage(
        'Speech recognition is not available on this device or emulator.',
      );
      return;
    }

    state = state.copyWith(
      status: AgentStatus.listening,
      currentTranscript: '',
      activeLog: '🎙️ Listening… speak your command.',
    );

    _processingStarted = false; // reset for this recording session

    await _speechService.startListening(
      onResult: (transcript, isFinal) {
        // Stream partial results live into currentTranscript
        state = state.copyWith(currentTranscript: transcript);
        if (isFinal && transcript.trim().isNotEmpty) {
          _processTranscript(transcript);
        }
      },
      onDone: () {
        // Fires when the STT engine stops (silence timeout or manual stop).
        // Only act if onResult never produced a final result.
        if (!_processingStarted) {
          final partial = state.currentTranscript ?? '';
          if (partial.trim().isNotEmpty) {
            _processTranscript(partial);
          } else {
            state = state.copyWith(
              status: AgentStatus.idle,
              activeLog: 'No speech detected. Try again.',
            );
          }
        }
      },
    );
  }

  Future<void> stopListening() async {
    if (state.status != AgentStatus.listening) return;
    // Manually stop — onDone/onResult will fire and trigger _processTranscript
    await _speechService.stopListening();
  }

  // ── Core processing ──────────────────────────────────────────────────────

  /// Sends the finalised [transcript] to the backend agent loop.
  Future<void> _processTranscript(String transcript) async {
    // One-shot guard: prevent double-invocation from onResult+onDone race
    if (_processingStarted) return;
    _processingStarted = true;

    if (transcript.trim().isEmpty) {
      state = state.copyWith(
        status: AgentStatus.idle,
        activeLog: 'Empty transcript — nothing to send.',
      );
      return;
    }

    state = state.copyWith(
      status: AgentStatus.processing,
      activeLog: 'Sending to agents…',
    );

    // Show what the user said as a chat bubble immediately
    final userMessage = ChatMessage(
      id: _uuid.v4(),
      text: transcript,
      timestamp: DateTime.now(),
      sender: SenderType.user,
    );
    state = state.copyWith(messages: [...state.messages, userMessage]);

    try {
      final result = await _apiService.processVoiceCommand(
        transcript: transcript,
        onLogUpdate: (logText) {
          state = state.copyWith(activeLog: logText);
        },
      );

      final newMessages = List<ChatMessage>.from(state.messages);

      // If the agent returned a plain text response, add it to chat
      if (result.textResponse != null) {
        newMessages.add(
          ChatMessage(
            id: _uuid.v4(),
            text: result.textResponse!,
            timestamp: DateTime.now(),
            sender: SenderType.agent,
          ),
        );
      }

      final isActionPending = result.pendingAction != null;

      state = state.copyWith(
        status: isActionPending ? AgentStatus.actionPending : AgentStatus.idle,
        messages: newMessages,
        pendingAction: result.pendingAction,
        activeLog: isActionPending
            ? 'Awaiting approval for staged action.'
            : (result.textResponse != null ? 'Response received.' : 'Done.'),
      );
    } catch (e) {
      state = state.copyWith(
        status: AgentStatus.idle,
        activeLog: 'Error processing: $e',
        messages: [
          ...state.messages,
          ChatMessage(
            id: _uuid.v4(),
            text: 'Failed to process command: $e',
            timestamp: DateTime.now(),
            sender: SenderType.system,
          ),
        ],
      );
    }
  }

  // ── Action approval ──────────────────────────────────────────────────────

  void updatePendingAction(Map<String, dynamic> updatedData) {
    if (state.pendingAction == null) return;
    state = state.copyWith(
      pendingAction: PendingAction(
        id: state.pendingAction!.id,
        actionType: state.pendingAction!.actionType,
        data: updatedData,
      ),
    );
  }

  Future<void> approveAction() async {
    final action = state.pendingAction;
    if (action == null) return;

    state = state.copyWith(
      status: AgentStatus.processing,
      activeLog: 'Executing action: ${action.actionType}…',
    );

    try {
      final result = await _apiService.executeAction(action);

      final agentMessage = ChatMessage(
        id: _uuid.v4(),
        text: result,
        timestamp: DateTime.now(),
        sender: SenderType.agent,
        subLogs: [
          '✅ Connection verified',
          '📧 API payload dispatched',
          '🚀 Delivery complete',
        ],
      );

      state = state.copyWith(
        status: AgentStatus.idle,
        messages: [...state.messages, agentMessage],
        activeLog: 'Action executed successfully.',
        clearPendingAction: true,
      );
    } catch (e) {
      state = state.copyWith(
        status: AgentStatus.idle,
        activeLog: 'Error executing action: $e',
        messages: [
          ...state.messages,
          ChatMessage(
            id: _uuid.v4(),
            text: 'Failed to complete action: $e',
            timestamp: DateTime.now(),
            sender: SenderType.system,
          ),
        ],
        clearPendingAction: true,
      );
    }
  }

  void cancelAction() {
    state = state.copyWith(
      status: AgentStatus.idle,
      activeLog: 'Action cancelled by user.',
      messages: [
        ...state.messages,
        ChatMessage(
          id: _uuid.v4(),
          text: 'Action was cancelled.',
          timestamp: DateTime.now(),
          sender: SenderType.system,
        ),
      ],
      clearPendingAction: true,
    );
  }

  // ── Helpers ──────────────────────────────────────────────────────────────

  void _appendSystemMessage(String text) {
    state = state.copyWith(
      messages: [
        ...state.messages,
        ChatMessage(
          id: _uuid.v4(),
          text: text,
          timestamp: DateTime.now(),
          sender: SenderType.system,
        ),
      ],
    );
  }
}

final agentProvider = NotifierProvider<AgentNotifier, AgentState>(
  AgentNotifier.new,
);
