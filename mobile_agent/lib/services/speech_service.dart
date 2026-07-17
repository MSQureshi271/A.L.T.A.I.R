import 'dart:io';
import 'package:record/record.dart';
import 'package:path_provider/path_provider.dart';

/// SpeechService handles high-quality local recording.
///
/// **Key design:**
/// To avoid Android microphone resource collisions (where running speech_to_text
/// and record together causes record to fail and yield empty files), this
/// service uses ONLY the `record` package.
///
/// Silence detection is implemented natively in Dart by polling the microphone's
/// amplitude levels every 200 ms.
class SpeechService {
  final AudioRecorder _recorder = AudioRecorder();
  
  bool _initialized = false;
  String? _latestAudioPath;
  bool _isListening = false;

  bool get isListening => _isListening;
  bool get isAvailable => _initialized;
  String? get latestAudioPath => _latestAudioPath;

  // ── Public API ─────────────────────────────────────────────────────────────

  /// One-time initialization of recorder permissions.
  Future<bool> initialize() async {
    if (_initialized) return true;
    try {
      _initialized = await _recorder.hasPermission();
    } catch (_) {
      _initialized = false;
    }
    return _initialized;
  }

  /// Starts recording high-quality audio and listening for silence.
  ///
  /// [onResult] passes back live status messages so the UI is updated.
  /// [onDone] is called when silence is detected or manually stopped.
  Future<void> startListening({
    required void Function(String statusText, bool isFinal) onResult,
    required void Function() onDone,
  }) async {
    if (!_initialized) {
      final ok = await initialize();
      if (!ok) {
        onResult('Microphone permission is required for voice commands.', true);
        onDone();
        return;
      }
    }

    _latestAudioPath = null;
    _isListening = true;

    try {
      // 1. Prepare temporary file for high-quality audio recording
      final tempDir = await getTemporaryDirectory();
      final path = '${tempDir.path}/command_${DateTime.now().millisecondsSinceEpoch}.m4a';
      _latestAudioPath = path;

      // 2. Start high-quality recording (AAC format, standard sample rate)
      await _recorder.start(
        const RecordConfig(
          encoder: AudioEncoder.aacLc,
          sampleRate: 44100,
          bitRate: 128000,
        ),
        path: path,
      );

      // Give visual feedback immediately
      onResult('🎙️ Listening... please speak.', false);

      // 3. Start silence detection polling loop in background
      _startSilenceDetection(onDone, onResult);

    } catch (e) {
      _isListening = false;
      onResult('Failed to start audio recording: $e', true);
      onDone();
    }
  }

  /// Manually stops recording.
  Future<void> stopListening() async {
    _isListening = false;
    await _stopRecorderSilently();
  }

  /// Cancels active recording and discards the temporary audio file.
  Future<void> cancel() async {
    _isListening = false;
    await _stopRecorderSilently();

    if (_latestAudioPath != null) {
      try {
        final file = File(_latestAudioPath!);
        if (await file.exists()) {
          await file.delete();
        }
      } catch (_) {}
      _latestAudioPath = null;
    }
  }

  // ── Private Helpers ────────────────────────────────────────────────────────

  /// Stops the recorder package helper if it is active.
  Future<void> _stopRecorderSilently() async {
    try {
      if (await _recorder.isRecording()) {
        await _recorder.stop();
      }
    } catch (_) {}
  }

  /// Polling loop in background that reads amplitude.
  /// Stops the recording if 3 seconds of silence are detected or if no speech
  /// is detected within the first 6 seconds.
  void _startSilenceDetection(
    void Function() onDone,
    void Function(String, bool) onResult,
  ) async {
    const pollInterval = Duration(milliseconds: 200);
    const silenceThresholdDb = -45.0; // Quiet ambient room noise is typically below -45dB
    const silenceDurationLimit = Duration(seconds: 3); // 3 seconds of silence to auto-stop
    const initialSpeechTimeout = Duration(seconds: 6);  // 6 seconds to start speaking

    final maxDurationLimit = const Duration(seconds: 60);
    final startTime = DateTime.now();
    
    int consecutiveSilencePolls = 0;
    final pollsNeededForSilence = (silenceDurationLimit.inMilliseconds / pollInterval.inMilliseconds).round();
    final pollsNeededForInitialTimeout = (initialSpeechTimeout.inMilliseconds / pollInterval.inMilliseconds).round();
    
    bool speechDetected = false;
    int totalPolls = 0;

    // Small delay before polling starts to allow recorder to initialize
    await Future.delayed(const Duration(milliseconds: 250));

    while (_isListening && await _recorder.isRecording()) {
      await Future.delayed(pollInterval);
      totalPolls++;

      final elapsed = DateTime.now().difference(startTime);
      if (elapsed >= maxDurationLimit) {
        break; // maximum recording limit reached
      }

      try {
        final amp = await _recorder.getAmplitude();
        final currentDb = amp.current;

        // Speaking levels are typically -10.0 to -35.0 dB.
        // We consider anything above -38.0 dB as active speech.
        if (currentDb > -38.0) {
          speechDetected = true;
          consecutiveSilencePolls = 0;
        } else if (currentDb < silenceThresholdDb) {
          consecutiveSilencePolls++;
        } else {
          // Sound level is between -38dB and -45dB.
          // Count it as silence if speech was already detected, otherwise reset
          if (speechDetected) {
            consecutiveSilencePolls++;
          }
        }

        // Provide status updates to UI
        if (speechDetected) {
          onResult('🎙️ Speak now (recording audio)...', false);
        } else {
          onResult('🎙️ Listening... please speak.', false);
        }

        // Check if silence triggered after speaking started
        if (speechDetected && consecutiveSilencePolls >= pollsNeededForSilence) {
          break;
        }

        // Check if user never spoke (initial timeout)
        if (!speechDetected && totalPolls >= pollsNeededForInitialTimeout) {
          break;
        }

      } catch (_) {
        // Handle read failures gracefully
      }
    }

    _isListening = false;
    await _stopRecorderSilently();
    onDone();
  }
}
