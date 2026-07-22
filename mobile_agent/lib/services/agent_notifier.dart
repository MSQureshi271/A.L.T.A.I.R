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
        // Stream local background STT preview words live into transcript bar
        state = state.copyWith(currentTranscript: transcript);
      },
      onDone: () {
        if (!_processingStarted) {
          final audioPath = _speechService.latestAudioPath;
          if (audioPath != null) {
            _processAudioFile(audioPath);
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
    await _speechService.stopListening();
  }

  // ── Core processing ──────────────────────────────────────────────────────

  /// Uploads high-quality recorded audio file to backend for transcription and task run.
  Future<void> _processAudioFile(String audioPath) async {
    if (_processingStarted) return;
    _processingStarted = true;

    state = state.copyWith(
      status: AgentStatus.processing,
      activeLog: 'Uploading audio command…',
      clearPlan: true,
    );

    try {
      final result = await _apiService.processAudioCommand(
        audioFilePath: audioPath,
        onTranscriptReceived: (transcript) {
          // Surfaced during Pass 1: add the user's bubble dynamically
          final userMessage = ChatMessage(
            id: _uuid.v4(),
            text: transcript,
            timestamp: DateTime.now(),
            sender: SenderType.user,
          );
          state = state.copyWith(
            messages: [...state.messages, userMessage],
          );
        },
        onLogUpdate: (logText) {
          state = state.copyWith(activeLog: logText);
        },
        history: state.conversationHistory,
      );

      final newMessages = List<ChatMessage>.from(state.messages);

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
        conversationHistory: result.updatedHistory ?? state.conversationHistory,
        currentPlan: result.plan,
      );

    } catch (e) {
      state = state.copyWith(
        status: AgentStatus.idle,
        activeLog: 'Error processing voice command: $e',
        messages: [
          ...state.messages,
          ChatMessage(
            id: _uuid.v4(),
            text: 'Failed to complete voice command: $e',
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
        safetyWarning: state.pendingAction!.safetyWarning,
        requiresDoubleConfirm: state.pendingAction!.requiresDoubleConfirm,
        safetyLevel: state.pendingAction!.safetyLevel,
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

    final planId = action.data['plan_id'] as String?;
    final stepId = action.data['step_id'] as int?;

    try {
      if (planId != null && stepId != null) {
        // Multi-step resumption stream
        final result = await _apiService.resumePlan(
          planId: planId,
          stepId: stepId,
          editedData: action.data,
          onLogUpdate: (log) {
            state = state.copyWith(activeLog: log);
          },
          onPlanUpdate: (updatedPlan) {
            state = state.copyWith(currentPlan: updatedPlan);
          },
          onToolResult: (step, res) {
            // Can update UI state logs if needed
          },
        );

        final newMessages = List<ChatMessage>.from(state.messages);
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
          conversationHistory: result.updatedHistory ?? state.conversationHistory,
          currentPlan: result.plan ?? state.currentPlan,
        );

      } else {
        // Standard legacy single action execute (fallback)
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
      }
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

  /// Append an assistant-role message into the chat (e.g. after a HITL action
  /// completes in a widget that calls the API directly).
  void addAssistantMessage(String text) {
    state = state.copyWith(
      status: AgentStatus.idle,
      activeLog: '',
      messages: [
        ...state.messages,
        ChatMessage(
          id: _uuid.v4(),
          text: text,
          timestamp: DateTime.now(),
          sender: SenderType.agent,
        ),
      ],
    );
  }
}

final agentProvider = NotifierProvider<AgentNotifier, AgentState>(
  AgentNotifier.new,
);
