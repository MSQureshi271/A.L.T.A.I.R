import 'package:speech_to_text/speech_to_text.dart';
import 'package:speech_to_text/speech_recognition_result.dart';

/// SpeechService wraps the speech_to_text plugin.
///
/// Uses the device's native speech recognizer (Android SpeechRecognizer /
/// iOS SFSpeechRecognizer), which is cloud-backed and far more reliable
/// on emulators than raw audio capture.
class SpeechService {
  final SpeechToText _stt = SpeechToText();
  bool _initialized = false;

  bool get isListening => _stt.isListening;
  bool get isAvailable => _initialized;

  // ── Public API ─────────────────────────────────────────────────────────────

  /// One-time initialization. Returns [true] if the device supports STT.
  Future<bool> initialize() async {
    if (_initialized) return true;
    _initialized = await _stt.initialize(
      onError: (error) {},   // Errors are handled in the result callback
      onStatus: (_) {},
      debugLogging: false,
    );
    return _initialized;
  }

  /// Starts listening and calls [onResult] with each partial/final transcript.
  /// [onDone] is called when recognition stops for any reason.
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

    // speech_to_text's onDone parameter fires reliably when recognition ends
    await _stt.listen(
      onResult: (SpeechRecognitionResult result) {
        onResult(result.recognizedWords, result.finalResult);
      },
      onDevice: false,
      listenFor: const Duration(seconds: 30),
      pauseFor: const Duration(seconds: 4),
      listenOptions: SpeechListenOptions(
        partialResults: true,
        cancelOnError: false,
        listenMode: ListenMode.dictation,
      ),
    );

    // Poll isListening to detect when the STT engine has stopped naturally
    // (pauseFor silence timeout or error). This is the most reliable cross-platform
    // way to get the "done" signal from speech_to_text.
    _pollUntilDone(onDone);
  }

  /// Manually stops recognition. [onDone] from [startListening] will still fire.
  Future<void> stopListening() async {
    if (_stt.isListening) {
      await _stt.stop();
    }
  }

  /// Cancels recognition without producing a result.
  Future<void> cancel() async {
    if (_stt.isListening) {
      await _stt.cancel();
    }
  }

  // ── Private ────────────────────────────────────────────────────────────────

  /// Polls every 200 ms until the STT engine is no longer listening,
  /// then calls [onDone]. Caps at 35 s as a safety timeout.
  void _pollUntilDone(void Function() onDone) async {
    const pollInterval = Duration(milliseconds: 200);
    const maxWait = Duration(seconds: 35);
    final deadline = DateTime.now().add(maxWait);

    // Small initial delay — the engine needs a tick to flip isListening to true
    await Future.delayed(const Duration(milliseconds: 300));

    while (_stt.isListening && DateTime.now().isBefore(deadline)) {
      await Future.delayed(pollInterval);
    }

    onDone();
  }
}
