import 'package:flutter/material.dart';
import '../models/agent_state.dart';

class AgentStatusCard extends StatelessWidget {
  final ChatMessage message;

  const AgentStatusCard({super.key, required this.message});

  @override
  Widget build(BuildContext context) {
    final isUser = message.sender == SenderType.user;
    final isSystem = message.sender == SenderType.system;

    if (isSystem) {
      return Center(
        child: Container(
          margin: const EdgeInsets.symmetric(vertical: 8, horizontal: 16),
          padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 12),
          decoration: BoxDecoration(
            color: const Color(0xFF1E1E24).withOpacity(0.6),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(color: Colors.white.withOpacity(0.05)),
          ),
          child: Text(
            message.text,
            style: const TextStyle(
              color: Color(0xFFADB5BD),
              fontSize: 12,
              fontWeight: FontWeight.w500,
            ),
            textAlign: TextAlign.center,
          ),
        ),
      );
    }

    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 8, horizontal: 16),
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.8,
        ),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(16),
            topRight: const Radius.circular(16),
            bottomLeft: Radius.circular(isUser ? 16 : 4),
            bottomRight: Radius.circular(isUser ? 4 : 16),
          ),
          gradient: isUser
              ? const LinearGradient(
                  colors: [Color(0xFF7B2CBF), Color(0xFF5A189A)],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                )
              : null,
          color: isUser ? null : const Color(0xFF1E1E24),
          border: isUser
              ? null
              : Border.all(color: Colors.white.withOpacity(0.08)),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.15),
              blurRadius: 10,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header showing Sender
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  isUser ? Icons.person_rounded : Icons.smart_toy_rounded,
                  color: isUser ? Colors.white70 : const Color(0xFF00B4D8),
                  size: 16,
                ),
                const SizedBox(width: 6),
                Text(
                  isUser ? 'You' : 'Executive Assistant',
                  style: TextStyle(
                    color: isUser ? Colors.white70 : const Color(0xFF00B4D8),
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const Spacer(),
                Text(
                  _formatTime(message.timestamp),
                  style: TextStyle(
                    color: isUser ? Colors.white38 : Colors.white24,
                    fontSize: 10,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            // Text Body
            Text(
              message.text,
              style: const TextStyle(
                color: Color(0xFFF8F9FA),
                fontSize: 14,
                height: 1.4,
              ),
            ),
            // Optional Sub-logs for step-by-step agent tracking
            if (message.subLogs != null && message.subLogs!.isNotEmpty) ...[
              const SizedBox(height: 12),
              const Divider(color: Colors.white12, height: 1),
              const SizedBox(height: 8),
              ...message.subLogs!.map((log) => Padding(
                    padding: const EdgeInsets.symmetric(vertical: 2.0),
                    child: Row(
                      children: [
                        const Icon(
                          Icons.arrow_right_rounded,
                          color: Color(0xFF38B000),
                          size: 16,
                        ),
                        const SizedBox(width: 4),
                        Expanded(
                          child: Text(
                            log,
                            style: const TextStyle(
                              color: Color(0xFFADB5BD),
                              fontSize: 12,
                            ),
                          ),
                        ),
                      ],
                    ),
                  )),
            ],
          ],
        ),
      ),
    );
  }

  String _formatTime(DateTime dt) {
    final hour = dt.hour.toString().padLeft(2, '0');
    final minute = dt.minute.toString().padLeft(2, '0');
    return '$hour:$minute';
  }
}
