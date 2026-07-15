import 'package:speech_to_text/speech_to_text.dart';
import 'package:speech_to_text/speech_recognition_result.dart';

/// SpeechService wraps the speech_to_text plugin.
///
/// **Key behaviour:**
/// Android's native SpeechRecognizer fires `finalResult: true` at every
/// *pause*, not just at the end of speech. Without correction, each segment
/// would overwrite the previous one and only the last clause would be sent.
///
/// This service solves that by:
///   1. Accumulating every intermediate final segment in [_accumulatedText].
///   2. Sending partial previews to the caller as `isFinal: false`.
///   3. Only calling `onResult(text, true)` **once** — right when the engine
///      fully stops — with the complete, joined transcript.
class SpeechService {
  final SpeechToText _stt = SpeechToText();
  bool _initialized = false;

  /// Running total of all pause-separated segments heard so far.
  String _accumulatedText = '';

  bool get isListening => _stt.isListening;
  bool get isAvailable => _initialized;

  // ── Public API ─────────────────────────────────────────────────────────────

  /// One-time initialization. Returns [true] if the device supports STT.
  Future<bool> initialize() async {
    if (_initialized) return true;
    _initialized = await _stt.initialize(
      onError: (error) {},
      onStatus: (_) {},
      debugLogging: false,
    );
    return _initialized;
  }

  /// Starts listening and calls [onResult] with each partial/full transcript.
  ///
  /// [onResult] is called with `isFinal: false` for every live update.
  /// It is called **exactly once** with `isFinal: true` (the complete text)
  /// right before [onDone] fires.
  ///
  /// [onDone] fires when recognition ends (silence timeout or manual stop).
  Future<void> startListening({
    required void Function(String transcript, bool isFinal) onResult,
    required void Function() onDone,
  }) async {
    if (!_initialized) {
      final ok = await initialize();
      if (!ok) {
        onResult('Speech recognition is not available on this device.', true);
        onDone();
        return;
      }
    }

    _accumulatedText = ''; // reset accumulator for this session

    await _stt.listen(
      onResult: (SpeechRecognitionResult result) {
        final words = result.recognizedWords;

        if (result.finalResult) {
          // Android fired an intermediate final due to a mid-speech pause.
          // Append to our accumulator but do NOT tell the caller we're done.
          if (words.trim().isNotEmpty) {
            _accumulatedText = _accumulatedText.isEmpty
                ? words.trim()
                : '$_accumulatedText ${words.trim()}';
          }
          // Show the accumulated text so far as a live (non-final) preview
          onResult(_accumulatedText, false);
        } else {
          // Partial result: preview = everything accumulated + current partial
          final preview = _accumulatedText.isEmpty
              ? words
              : '$_accumulatedText $words';
          onResult(preview, false);
        }
      },
      onDevice: false,
      listenFor: const Duration(seconds: 60),   // maximum recording window
      pauseFor: const Duration(seconds: 8),     // silence before auto-stop
      listenOptions: SpeechListenOptions(
        partialResults: true,
        cancelOnError: false,
        listenMode: ListenMode.dictation,
      ),
    );

    // When the engine fully stops, deliver the ONE true final result
    _pollUntilDone(() {
      final finalText = _accumulatedText.trim();
      if (finalText.isNotEmpty) {
        // Signal the real completion with the entire accumulated transcript
        onResult(finalText, true);
      }
      onDone();
    });
  }

  /// Manually stops recognition. The [onDone] callback still fires normally.
  Future<void> stopListening() async {
    if (_stt.isListening) {
      await _stt.stop();
    }
  }

  /// Cancels recognition without producing a final result.
  Future<void> cancel() async {
    if (_stt.isListening) {
      await _stt.cancel();
    }
    _accumulatedText = '';
  }

  // ── Private ────────────────────────────────────────────────────────────────

  /// Polls every 200 ms until the STT engine stops, then calls [onDone].
  /// The 65 s cap is a safety net — normal flow stops via pauseFor or stop().
  void _pollUntilDone(void Function() onDone) async {
    const pollInterval = Duration(milliseconds: 200);
    const maxWait = Duration(seconds: 65);
    final deadline = DateTime.now().add(maxWait);

    // Small initial delay — engine needs a tick to flip isListening → true
    await Future.delayed(const Duration(milliseconds: 300));

    while (_stt.isListening && DateTime.now().isBefore(deadline)) {
      await Future.delayed(pollInterval);
    }

    onDone();
  }
}
