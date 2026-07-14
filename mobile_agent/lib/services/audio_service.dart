import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:record/record.dart';

class AudioService {
  final AudioRecorder _recorder = AudioRecorder();
  String? _currentPath;

  Future<bool> hasPermission() async {
    return await _recorder.hasPermission();
  }

  Future<bool> isRecording() async {
    return await _recorder.isRecording();
  }

  Future<void> startRecording() async {
    try {
      if (!await hasPermission()) {
        throw Exception('Microphone permission not granted');
      }

      // Stop any active recording first
      if (await _recorder.isRecording()) {
        await _recorder.stop();
      }

      String filePath = '';
      if (!kIsWeb) {
        final tempDir = Directory.systemTemp;
        filePath = '${tempDir.path}/voice_cmd_${DateTime.now().millisecondsSinceEpoch}.m4a';
      }
      _currentPath = filePath;

      try {
        await _recorder.start(
          const RecordConfig(
            encoder: AudioEncoder.aacLc,
            sampleRate: 44100, // 44.1kHz is widely supported for AAC on Windows/Desktop
            bitRate: 128000,
            numChannels: 1,
          ),
          path: filePath,
        );
      } catch (firstError) {
        if (!kIsWeb) {
          // Fall back to WAV (PCM 16bit) which doesn't require encoding codecs
          final tempDir = Directory.systemTemp;
          final String fallbackPath = '${tempDir.path}/voice_cmd_${DateTime.now().millisecondsSinceEpoch}.wav';
          _currentPath = fallbackPath;
          await _recorder.start(
            const RecordConfig(
              encoder: AudioEncoder.wav,
              sampleRate: 16000, // 16kHz raw PCM is supported everywhere
              numChannels: 1,
            ),
            path: fallbackPath,
          );
        } else {
          rethrow;
        }
      }
    } catch (e) {
      rethrow;
    }
  }

  Future<String?> stopRecording() async {
    try {
      if (!await _recorder.isRecording()) {
        return null;
      }
      final path = await _recorder.stop();
      return path ?? _currentPath;
    } catch (e) {
      return null;
    }
  }

  Future<void> dispose() async {
    await _recorder.dispose();
  }
}
