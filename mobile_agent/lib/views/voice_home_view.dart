import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_fonts/google_fonts.dart';
import '../models/agent_state.dart';
import '../services/agent_notifier.dart';
import '../widgets/voice_visualizer.dart';
import '../widgets/agent_status_card.dart';
import '../widgets/approval_drawer.dart';
import '../widgets/approval_card_attachment.dart';
import '../widgets/app_drawer.dart';
import '../widgets/plan_preview_card.dart';
import '../widgets/workflow_progress_card.dart';


class VoiceHomeView extends ConsumerStatefulWidget {
  const VoiceHomeView({super.key});

  @override
  ConsumerState<VoiceHomeView> createState() => _VoiceHomeViewState();
}

class _VoiceHomeViewState extends ConsumerState<VoiceHomeView> {
  final ScrollController _scrollController = ScrollController();
  final GlobalKey<ScaffoldState> _scaffoldKey = GlobalKey<ScaffoldState>();

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  void _showApprovalDrawer(BuildContext context, AgentState state) {
    final action = state.pendingAction!;
    final actionType = action.actionType;

    // Route download_attachment to the batch checkbox card
    if (actionType == 'download_attachment') {
      showModalBottomSheet(
        context: context,
        isScrollControlled: true,
        backgroundColor: Colors.transparent,
        builder: (context) => DraggableScrollableSheet(
          initialChildSize: 0.6,
          minChildSize: 0.4,
          maxChildSize: 0.9,
          expand: false,
          builder: (context, scrollController) => Container(
            decoration: const BoxDecoration(
              color: Color(0xFF0F0F12),
              borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
            ),
            child: SingleChildScrollView(
              controller: scrollController,
              child: ApprovalCardAttachment(
                approvalData: {
                  'type': 'approval_required',
                  'action': actionType,
                  'data': action.data,
                },
                onCancel: () {
                  ref.read(agentProvider.notifier).cancelAction();
                  Navigator.pop(context);
                },
                onSuccess: (message) {
                  Navigator.pop(context);
                  ref.read(agentProvider.notifier).cancelAction();
                  ref.read(agentProvider.notifier).addAssistantMessage(message);
                },
              ),
            ),
          ),
        ),
      );
      return;
    }

    // Default path: use the generic schema-driven ApprovalDrawer
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (context) => ApprovalDrawer(
        action: action,
        onCancel: () {
          ref.read(agentProvider.notifier).cancelAction();
          Navigator.pop(context);
        },
        onConfirm: (updatedData) {
          final notifier = ref.read(agentProvider.notifier);
          notifier.updatePendingAction(updatedData);
          notifier.approveAction();
          Navigator.pop(context);
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(agentProvider);

    // Auto-scroll on new messages
    ref.listen<AgentState>(agentProvider, (previous, next) {
      if (previous?.messages.length != next.messages.length ||
          previous?.activeLog != next.activeLog) {
        _scrollToBottom();
      }

      // Auto-trigger approval sheet
      if (next.status == AgentStatus.actionPending &&
          next.pendingAction != null &&
          previous?.status != AgentStatus.actionPending) {
        _showApprovalDrawer(context, next);
      }
    });

    return Scaffold(
      key: _scaffoldKey,
      backgroundColor: const Color(0xFF0F0F12),
      drawer: const AppDrawer(),
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        leading: IconButton(
          onPressed: () => _scaffoldKey.currentState!.openDrawer(),
          icon: const Icon(Icons.menu_rounded, color: Colors.white70),
        ),
        title: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: const Color(0xFF1E1E24),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.white.withOpacity(0.05)),
              ),
              child: const Icon(
                Icons.account_balance_wallet_rounded,
                color: Color(0xFF7B2CBF),
                size: 20,
              ),
            ),
            const SizedBox(width: 12),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'EXECUTIVE AGENT',
                  style: GoogleFonts.outfit(
                    color: const Color(0xFFF8F9FA),
                    fontSize: 14,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 1.5,
                  ),
                ),
                Text(
                  'Active Session',
                  style: GoogleFonts.outfit(
                    color: const Color(0xFF38B000),
                    fontSize: 10,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
      body: SafeArea(
        child: Column(
          children: [
            // Banner/Status Header
            _buildStatusHeader(state),

            // Chat Feed
            Expanded(
              child: state.messages.isEmpty && (state.activeLog == null || state.activeLog!.isEmpty) && state.currentPlan == null
                  ? _buildEmptyState()
                  : _buildChatList(state),
            ),

            // Live Transcript box
            if (state.currentTranscript != null && state.currentTranscript!.isNotEmpty)
              Container(
                margin: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: const Color(0xFF1E1E24).withOpacity(0.5),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: Colors.white.withOpacity(0.04)),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.hearing_rounded, color: Color(0xFF00B4D8), size: 16),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        '"${state.currentTranscript}"',
                        style: GoogleFonts.outfit(
                          color: const Color(0xFFADB5BD),
                          fontSize: 13,
                          fontStyle: FontStyle.italic,
                        ),
                      ),
                    ),
                  ],
                ),
              ),

            // Controls Zone
            Container(
              padding: const EdgeInsets.only(top: 12, bottom: 24, left: 24, right: 24),
              decoration: BoxDecoration(
                color: const Color(0xFF15151A),
                borderRadius: const BorderRadius.only(
                  topLeft: Radius.circular(24),
                  topRight: Radius.circular(24),
                ),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withOpacity(0.3),
                    blurRadius: 20,
                    offset: const Offset(0, -4),
                  ),
                ],
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (state.status == AgentStatus.listening) ...[
                    VoiceVisualizer(isRecording: state.status == AgentStatus.listening),
                    const SizedBox(height: 12),
                  ],
                  _buildControlPanel(state),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStatusHeader(AgentState state) {
    Color indicatorColor = const Color(0xFFADB5BD);
    String statusText = "Ready for instructions";

    switch (state.status) {
      case AgentStatus.idle:
        indicatorColor = const Color(0xFFADB5BD);
        statusText = "Ready for instructions";
        break;
      case AgentStatus.listening:
        indicatorColor = const Color(0xFFE63946);
        statusText = "Listening...";
        break;
      case AgentStatus.processing:
        indicatorColor = const Color(0xFF00B4D8);
        statusText = "Agents working...";
        break;
      case AgentStatus.speaking:
        indicatorColor = const Color(0xFF7B2CBF);
        statusText = "Speaking response...";
        break;
      case AgentStatus.actionPending:
        indicatorColor = const Color(0xFFFFB703);
        statusText = "Action staged - Awaiting approval";
        break;
    }

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 20),
      decoration: BoxDecoration(
        color: const Color(0xFF1E1E24).withOpacity(0.4),
        border: Border(
          bottom: BorderSide(color: Colors.white.withOpacity(0.05)),
        ),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              color: indicatorColor,
              shape: BoxShape.circle,
              boxShadow: [
                BoxShadow(
                  color: indicatorColor.withOpacity(0.5),
                  blurRadius: 8,
                  spreadRadius: 2,
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Text(
            statusText,
            style: GoogleFonts.outfit(
              color: const Color(0xFFADB5BD),
              fontSize: 12,
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: SingleChildScrollView(
        child: Padding(
          padding: const EdgeInsets.all(32.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Container(
                width: 80,
                height: 80,
                decoration: BoxDecoration(
                  color: const Color(0xFF1E1E24),
                  shape: BoxShape.circle,
                  border: Border.all(color: Colors.white.withOpacity(0.04)),
                ),
                child: const Icon(
                  Icons.mic_none_rounded,
                  color: Color(0xFF7B2CBF),
                  size: 40,
                ),
              ),
              const SizedBox(height: 24),
              Text(
                "Tap the mic and speak",
                style: GoogleFonts.outfit(
                  color: const Color(0xFFF8F9FA),
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                "Try saying: 'Draft a summary of Q2 and email it to finance@company.com'",
                style: GoogleFonts.outfit(
                  color: const Color(0xFFADB5BD),
                  fontSize: 13,
                ),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 24),
              _buildInstructionHint("💡 Safe Guard: Actions will require approval before sending."),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildInstructionHint(String text) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFF1E1E24).withOpacity(0.4),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(
        text,
        style: GoogleFonts.outfit(color: Colors.white60, fontSize: 11),
      ),
    );
  }

  /// Builds the main chat feed, optionally injecting a [PlanPreviewCard] as a
  /// virtual item after the last agent message and before any processing indicator.
  Widget _buildChatList(AgentState state) {
    final showPlan = state.currentPlan != null;
    final showProcessing = state.status == AgentStatus.processing;

    // Total virtual items = messages + optional plan card + optional processing
    final int extraItems = (showPlan ? 1 : 0) + (showProcessing ? 1 : 0);
    final int totalItems = state.messages.length + extraItems;

    return ListView.builder(
      controller: _scrollController,
      padding: const EdgeInsets.only(bottom: 24, top: 12),
      itemCount: totalItems,
      itemBuilder: (context, index) {
        // First section: chat messages
        if (index < state.messages.length) {
          return AgentStatusCard(message: state.messages[index]);
        }

        final extraIndex = index - state.messages.length;

        // Second section: plan progress stepper card (if available)
        if (showPlan && extraIndex == 0) {
          return WorkflowProgressCard(plan: state.currentPlan!);
        }

        // Third section: processing indicator
        return _buildProcessingItem(state.activeLog ?? 'Processing…');
      },
    );
  }

  Widget _buildProcessingItem(String activeLog) {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 8, horizontal: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1E1E24).withOpacity(0.5),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFF00B4D8).withOpacity(0.15)),
      ),
      child: Row(
        children: [
          const SizedBox(
            width: 20,
            height: 20,
            child: CircularProgressIndicator(
              strokeWidth: 2,
              valueColor: AlwaysStoppedAnimation<Color>(Color(0xFF00B4D8)),
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Text(
              activeLog,
              style: GoogleFonts.outfit(
                color: const Color(0xFF00B4D8),
                fontSize: 13,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildControlPanel(AgentState state) {
    final notifier = ref.read(agentProvider.notifier);

    if (state.status == AgentStatus.processing) {
      return Container(
        padding: const EdgeInsets.all(16),
        decoration: const BoxDecoration(
          color: Color(0xFF1E1E24),
          shape: BoxShape.circle,
        ),
        child: const SizedBox(
          width: 32,
          height: 32,
          child: CircularProgressIndicator(
            strokeWidth: 3,
            valueColor: AlwaysStoppedAnimation<Color>(Color(0xFF00B4D8)),
          ),
        ),
      );
    }

    if (state.status == AgentStatus.actionPending) {
      return Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          IconButton(
            onPressed: notifier.cancelAction,
            icon: const Icon(Icons.close_rounded, color: Color(0xFFE63946)),
            style: IconButton.styleFrom(
              backgroundColor: const Color(0xFF1E1E24),
              padding: const EdgeInsets.all(14),
            ),
          ),
          const SizedBox(width: 20),
          GestureDetector(
            onTap: () => _showApprovalDrawer(context, state),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
              decoration: BoxDecoration(
                color: const Color(0xFFFFB703),
                borderRadius: BorderRadius.circular(30),
                boxShadow: [
                  BoxShadow(
                    color: const Color(0xFFFFB703).withOpacity(0.3),
                    blurRadius: 12,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.security_rounded, color: Color(0xFF0F0F12), size: 18),
                  const SizedBox(width: 8),
                  Text(
                    'Review Action',
                    style: GoogleFonts.outfit(
                      color: const Color(0xFF0F0F12),
                      fontSize: 14,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      );
    }

    final isListening = state.status == AgentStatus.listening;

    return GestureDetector(
      onTap: () {
        if (isListening) {
          notifier.stopListening();
        } else {
          notifier.startListening();
        }
      },
      child: Container(
        width: 72,
        height: 72,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: LinearGradient(
            colors: isListening
                ? [const Color(0xFFE63946), const Color(0xFFD62828)]
                : [const Color(0xFF7B2CBF), const Color(0xFF5A189A)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          boxShadow: [
            BoxShadow(
              color: (isListening ? const Color(0xFFE63946) : const Color(0xFF7B2CBF)).withOpacity(0.4),
              blurRadius: 20,
              spreadRadius: 2,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Icon(
          isListening ? Icons.stop_rounded : Icons.mic_rounded,
          color: Colors.white,
          size: 32,
        ),
      ),
    );
  }
}
