import math
from pathlib import Path
import tempfile
import unittest

from python.spikes import (
    ChunkedWaveformReader,
    ChunkedWaveformWriter,
    EventCaptureEngine,
    RollingSampleBuffer,
    StreamChannel,
    TriggerSpec,
    UniformStreamSchema,
    WaveformSizeLimitError,
    compare_codecs,
)


def schema(channel_count=1):
    return UniformStreamSchema(
        "converter.run",
        tuple(StreamChannel(f"ch{index}", "V") for index in range(channel_count)),
        sample_interval_s=1e-6,
        source_sha256="a" * 64,
    )


class RollingBufferTests(unittest.TestCase):
    def test_fixed_capacity_overwrites_oldest_and_counts_drops(self):
        buffer = RollingSampleBuffer(schema(), 3)
        for value in range(5):
            buffer.append((value,))
        window = buffer.snapshot()
        self.assertEqual(window.first_sample_index, 2)
        self.assertEqual(window.frames, ((2.0,), (3.0,), (4.0,)))
        self.assertEqual(window.dropped_samples, 2)
        with self.assertRaises(ValueError):
            buffer.append((5.0,), sample_index=7)


class EventCaptureTests(unittest.TestCase):
    def test_rising_trigger_keeps_only_pre_and_post_window(self):
        trigger = TriggerSpec(
            channel_index=0,
            level=0.0,
            edge="rising",
            hysteresis=0.1,
            pretrigger_samples=2,
            posttrigger_samples=2,
        )
        engine = EventCaptureEngine(schema(), trigger)
        completed = []
        for value in (-1.0, -0.5, -0.2, 0.25, 0.5, 0.75, 1.0):
            event = engine.feed((value,))
            if event is not None:
                completed.append(event)
        self.assertEqual(len(completed), 1)
        event = completed[0]
        self.assertEqual(event.first_sample_index, 1)
        self.assertEqual(event.trigger_sample_index, 3)
        self.assertEqual(event.frames, ((-0.5,), (-0.2,), (0.25,), (0.5,), (0.75,)))
        self.assertEqual(engine.pop_event(), event)

    def test_event_queue_and_incomplete_capture_are_bounded(self):
        trigger = TriggerSpec(0, 0.0, pretrigger_samples=0, posttrigger_samples=0)
        engine = EventCaptureEngine(schema(), trigger, max_queued_events=1)
        for value in (-1.0, 1.0, -1.0, 1.0):
            engine.feed((value,))
        self.assertEqual(len(engine.queued_events), 1)
        self.assertEqual(engine.dropped_events, 1)
        self.assertEqual(engine.queued_events[0].event_sequence, 2)

    def test_manual_limit_event_reuses_pretrigger_history(self):
        trigger = TriggerSpec(
            0, 0.0, edge="manual", pretrigger_samples=2, posttrigger_samples=1
        )
        engine = EventCaptureEngine(schema(), trigger)
        for value in (10.0, 11.0, 12.0):
            engine.feed((value,))
        self.assertIsNone(engine.trigger_now("limit:overcurrent"))
        event = engine.feed((13.0,))
        self.assertIsNotNone(event)
        self.assertEqual(event.reason, "limit:overcurrent")
        self.assertEqual(event.frames, ((10.0,), (11.0,), (12.0,), (13.0,)))


class ChunkedStoreTests(unittest.TestCase):
    def frames(self, count=1000):
        return tuple(
            (math.sin(index * 0.01), 12.0 + index * 1e-6)
            for index in range(count)
        )

    def test_every_codec_round_trips_exact_float_bits_and_chunks(self):
        stream = schema(2)
        frames = self.frames(37)
        with tempfile.TemporaryDirectory() as directory:
            for codec in ("none", "zlib-fast", "zlib", "xor-zlib", "lzma"):
                with self.subTest(codec=codec):
                    path = Path(directory) / f"trace-{codec}.spkw"
                    with ChunkedWaveformWriter(
                        path, stream, codec=codec, max_chunk_samples=8
                    ) as writer:
                        writer.append(frames)
                    with ChunkedWaveformReader(path) as reader:
                        chunks = tuple(reader.iter_chunks())
                        restored = tuple(frame for chunk in chunks for frame in chunk.frames)
                        self.assertTrue(reader.complete)
                        self.assertFalse(reader.issues)
                        self.assertEqual(restored, frames)
                        self.assertEqual([item.sample_count for item in chunks], [8, 8, 8, 8, 5])

    def test_torn_tail_recovers_all_complete_chunks(self):
        stream = schema(2)
        path = None
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "interrupted.spkw"
            writer = ChunkedWaveformWriter(path, stream, max_chunk_samples=4)
            writer.append(self.frames(9))
            writer.close(complete=False)
            with ChunkedWaveformReader(path) as reader:
                restored = tuple(frame for chunk in reader.iter_chunks() for frame in chunk.frames)
                self.assertEqual(restored, self.frames(9))
                self.assertFalse(reader.complete)
                self.assertTrue(reader.issues)

    def test_file_size_admission_stops_before_unbounded_growth(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bounded.spkw"
            writer = ChunkedWaveformWriter(
                path, schema(), codec="none", max_chunk_samples=1000, max_file_bytes=4096
            )
            with self.assertRaises(WaveformSizeLimitError):
                writer.append(tuple((float(index),) for index in range(600)))
            writer.close(complete=False)
            self.assertLessEqual(path.stat().st_size, 4096)

    def test_codec_comparison_is_size_only_and_lossless(self):
        report = compare_codecs(schema(2), self.frames(1000))
        self.assertEqual(report["contract"], "spikes/waveform-compression-comparison/v1")
        self.assertEqual(len(report["trials"]), 5)
        self.assertTrue(all(not item["lossy"] for item in report["trials"]))
        self.assertIn(report["recommended_for_size"], {item["codec"] for item in report["trials"]})


if __name__ == "__main__":
    unittest.main()
