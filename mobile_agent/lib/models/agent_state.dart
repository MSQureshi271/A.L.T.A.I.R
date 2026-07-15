enum AgentStatus {
  idle,
  listening,
  processing,
  speaking,
  actionPending,
}

enum SenderType {
  user,
  agent,
  system,
}

class ChatMessage {
  final String id;
  final String text;
  final DateTime timestamp;
  final SenderType sender;
  final List<String>? subLogs;

  const ChatMessage({
    required this.id,
    required this.text,
    required this.timestamp,
    required this.sender,
    this.subLogs,
  });

  ChatMessage copyWith({
    String? id,
    String? text,
    DateTime? timestamp,
    SenderType? sender,
    List<String>? subLogs,
  }) {
    return ChatMessage(
      id: id ?? this.id,
      text: text ?? this.text,
      timestamp: timestamp ?? this.timestamp,
      sender: sender ?? this.sender,
      subLogs: subLogs ?? this.subLogs,
    );
  }
}

class PendingAction {
  final String id;
  final String actionType; // 'send_email', 'create_event', etc.
  final Map<String, dynamic> data; // Detailed payload (to, subject, body, time, etc.)

  const PendingAction({
    required this.id,
    required this.actionType,
    required this.data,
  });
}

class AgentState {
  final AgentStatus status;
  final List<ChatMessage> messages;
  final String? currentTranscript;
  final String? activeLog;
  final PendingAction? pendingAction;
  final List<Map<String, dynamic>> conversationHistory;

  const AgentState({
    this.status = AgentStatus.idle,
    this.messages = const [],
    this.currentTranscript,
    this.activeLog,
    this.pendingAction,
    this.conversationHistory = const [],
  });

  AgentState copyWith({
    AgentStatus? status,
    List<ChatMessage>? messages,
    String? currentTranscript,
    String? activeLog,
    PendingAction? pendingAction,
    bool clearPendingAction = false,
    List<Map<String, dynamic>>? conversationHistory,
  }) {
    return AgentState(
      status: status ?? this.status,
      messages: messages ?? this.messages,
      currentTranscript: currentTranscript ?? this.currentTranscript,
      activeLog: activeLog ?? this.activeLog,
      pendingAction: clearPendingAction ? null : (pendingAction ?? this.pendingAction),
      conversationHistory: conversationHistory ?? this.conversationHistory,
    );
  }
}
