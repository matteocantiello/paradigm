"""Tests for the per-thread dashboard event stream (logging/stream.py)."""

import json
from pathlib import Path

from paradigm.logging.stream import ResearchEventStream


def _read_events(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class TestEnvelope:
    def test_emit_writes_complete_envelope(self, tmp_path: Path) -> None:
        stream = ResearchEventStream(tmp_path / "events.jsonl")
        stream.emit("run.started", {"thread_id": "thread-abc"}, agent=None)
        stream.close()

        events = _read_events(tmp_path / "events.jsonl")
        assert len(events) == 1
        event = events[0]
        assert set(event) == {"seq", "ts", "type", "phase", "round", "agent", "payload"}
        assert event["seq"] == 1
        assert event["type"] == "run.started"
        assert event["agent"] is None
        assert event["payload"] == {"thread_id": "thread-abc"}
        assert event["ts"].endswith("Z")

    def test_seq_is_strictly_monotone(self, tmp_path: Path) -> None:
        stream = ResearchEventStream(tmp_path / "events.jsonl")
        for i in range(5):
            stream.emit("round.started", {"round": i})
        stream.close()

        seqs = [e["seq"] for e in _read_events(tmp_path / "events.jsonl")]
        assert seqs == [1, 2, 3, 4, 5]

    def test_payload_defaults_to_empty_object(self, tmp_path: Path) -> None:
        stream = ResearchEventStream(tmp_path / "events.jsonl")
        stream.emit("phase.completed")
        stream.close()
        assert _read_events(tmp_path / "events.jsonl")[0]["payload"] == {}

    def test_non_serializable_payload_falls_back_to_str(self, tmp_path: Path) -> None:
        stream = ResearchEventStream(tmp_path / "events.jsonl")
        stream.emit("artifact.created", {"path": Path("/tmp/fig.png")})
        stream.close()
        events = _read_events(tmp_path / "events.jsonl")
        assert events[0]["payload"]["path"] == "/tmp/fig.png"


class TestContext:
    def test_context_stamped_on_events(self, tmp_path: Path) -> None:
        stream = ResearchEventStream(tmp_path / "events.jsonl")
        stream.emit("run.started")
        stream.set_context(phase="ideation", round_num=2)
        stream.emit("hypothesis.created", {"hypothesis_id": "h1"}, agent="theorist-0")
        stream.close()

        events = _read_events(tmp_path / "events.jsonl")
        assert events[0]["phase"] is None
        assert events[1]["phase"] == "ideation"
        assert events[1]["round"] == 2
        assert events[1]["agent"] == "theorist-0"

    def test_partial_context_update_preserves_other_field(self, tmp_path: Path) -> None:
        stream = ResearchEventStream(tmp_path / "events.jsonl")
        stream.set_context(phase="planning", round_num=3)
        stream.set_context(round_num=4)  # phase untouched
        stream.emit("round.started")
        stream.set_context(phase="execution", round_num=None)  # round cleared
        stream.emit("experiment.started")
        stream.close()

        events = _read_events(tmp_path / "events.jsonl")
        assert (events[0]["phase"], events[0]["round"]) == ("planning", 4)
        assert (events[1]["phase"], events[1]["round"]) == ("execution", None)


class TestResilience:
    def test_resume_continues_seq(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        first = ResearchEventStream(path)
        first.emit("run.started")
        first.emit("phase.started")
        first.close()

        second = ResearchEventStream(path)
        second.emit("phase.completed")
        second.close()

        seqs = [e["seq"] for e in _read_events(path)]
        assert seqs == [1, 2, 3]

    def test_unwritable_path_never_raises(self, tmp_path: Path) -> None:
        # A directory at the target path makes open() fail
        bad = tmp_path / "events.jsonl"
        bad.mkdir()
        stream = ResearchEventStream(bad)
        stream.emit("run.started", {"k": "v"})  # must not raise
        stream.close()

    def test_emit_after_close_is_noop(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        stream = ResearchEventStream(path)
        stream.emit("run.started")
        stream.close()
        stream.emit("run.completed")  # must not raise nor write
        assert len(_read_events(path)) == 1

    def test_flushes_after_every_write(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        stream = ResearchEventStream(path)
        stream.emit("run.started")
        # Read WITHOUT closing: live mode tails the file mid-run
        assert len(_read_events(path)) == 1
        stream.close()


class TestCheckEventsScript:
    def _run_check(self, path: Path) -> int:
        import importlib.util
        import sys

        spec = importlib.util.spec_from_file_location(
            "check_events", Path(__file__).parent.parent / "scripts" / "check_events.py"
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules["check_events"] = mod
        spec.loader.exec_module(mod)
        return mod.check(path)

    def test_valid_stream_passes(self, tmp_path: Path) -> None:
        stream = ResearchEventStream(tmp_path / "events.jsonl")
        stream.set_context(phase="ideation", round_num=1)
        stream.emit("run.started", {"thread_id": "t"})
        stream.emit("hypothesis.created", {"hypothesis_id": "h1", "statement": "x"})
        stream.emit("run.completed", {"status": "published"})
        stream.close()
        assert self._run_check(tmp_path / "events.jsonl") == 0

    def test_seq_gap_fails(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        good = {
            "seq": 1,
            "ts": "2026-01-01T00:00:00Z",
            "type": "run.started",
            "phase": None,
            "round": None,
            "agent": None,
            "payload": {},
        }
        bad = {**good, "seq": 1, "type": "run.completed"}  # repeated seq
        path.write_text(json.dumps(good) + "\n" + json.dumps(bad) + "\n")
        assert self._run_check(path) == 1

    def test_garbage_line_fails(self, tmp_path: Path) -> None:
        path = tmp_path / "events.jsonl"
        path.write_text("not json\n")
        assert self._run_check(path) == 1
