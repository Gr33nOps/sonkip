package io.github.gr33nops.sonkip;

import android.media.MediaCodec;
import android.media.MediaExtractor;
import android.media.MediaFormat;
import android.media.MediaMuxer;

import java.io.File;
import java.nio.ByteBuffer;

/** Extracts an existing AAC track into an audio-only M4A container without transcoding. */
public final class AndroidAudioExtractor {
    private AndroidAudioExtractor() {}

    public static void extractM4a(String sourcePath, String targetPath) throws Exception {
        MediaExtractor extractor = new MediaExtractor();
        MediaMuxer muxer = null;
        boolean started = false;
        File target = new File(targetPath);
        try {
            extractor.setDataSource(sourcePath);
            int sourceTrack = -1;
            MediaFormat audioFormat = null;
            for (int index = 0; index < extractor.getTrackCount(); index++) {
                MediaFormat candidate = extractor.getTrackFormat(index);
                String mime = candidate.getString(MediaFormat.KEY_MIME);
                if (mime != null && mime.startsWith("audio/")) {
                    sourceTrack = index;
                    audioFormat = candidate;
                    break;
                }
            }
            if (sourceTrack < 0 || audioFormat == null) {
                throw new IllegalArgumentException("Downloaded MP4 has no audio track");
            }

            target.delete();
            extractor.selectTrack(sourceTrack);
            muxer = new MediaMuxer(targetPath, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4);
            int targetTrack = muxer.addTrack(audioFormat);
            muxer.start();
            started = true;

            int capacity = audioFormat.containsKey(MediaFormat.KEY_MAX_INPUT_SIZE)
                    ? Math.max(audioFormat.getInteger(MediaFormat.KEY_MAX_INPUT_SIZE), 256 * 1024)
                    : 1024 * 1024;
            ByteBuffer buffer = ByteBuffer.allocateDirect(capacity);
            MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
            while (true) {
                buffer.clear();
                int size = extractor.readSampleData(buffer, 0);
                if (size < 0) break;
                int sourceFlags = extractor.getSampleFlags();
                int codecFlags = 0;
                if ((sourceFlags & MediaExtractor.SAMPLE_FLAG_SYNC) != 0) {
                    codecFlags |= MediaCodec.BUFFER_FLAG_KEY_FRAME;
                }
                if ((sourceFlags & MediaExtractor.SAMPLE_FLAG_PARTIAL_FRAME) != 0) {
                    codecFlags |= MediaCodec.BUFFER_FLAG_PARTIAL_FRAME;
                }
                info.set(0, size, extractor.getSampleTime(), codecFlags);
                muxer.writeSampleData(targetTrack, buffer, info);
                extractor.advance();
            }
        } catch (Exception error) {
            target.delete();
            throw error;
        } finally {
            if (muxer != null) {
                try { if (started) muxer.stop(); } finally { muxer.release(); }
            }
            extractor.release();
        }
    }
}
