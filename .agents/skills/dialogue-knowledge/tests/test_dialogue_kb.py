import importlib.util
import io
import json
import sys
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


TEST_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = TEST_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from adapters.cursor import CursorAdapter  # noqa: E402


def load_dialogue_kb_module():
    module_path = SCRIPTS_DIR / "dialogue-kb.py"
    spec = importlib.util.spec_from_file_location("dialogue_kb", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class DialogueKnowledgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dialogue_kb = load_dialogue_kb_module()

    def test_cursor_archive_sessions_support_nested_remote_transcripts(self):
        adapter = CursorAdapter()
        with TemporaryDirectory() as tmpdir:
            archive_dir = Path(tmpdir)
            remote_conv = (
                archive_dir
                / "archive"
                / "remote-devbox"
                / "cursor"
                / "project-alpha"
                / "agent-transcripts"
                / "session-1"
                / "conv-123.jsonl"
            )
            remote_conv.parent.mkdir(parents=True, exist_ok=True)
            remote_conv.write_text(
                "\n".join(
                    [
                        '{"role":"user","message":{"content":[{"type":"text","text":"<user_query>How do I fix caching?</user_query>"}]}}',
                        '{"role":"assistant","message":{"content":[{"type":"text","text":"Invalidate the stale key before retrying."}]}}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            sessions = adapter.archive_sessions(archive_dir)

            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0][0], remote_conv)
            self.assertEqual(sessions[0][1], "project-alpha")
            self.assertEqual(sessions[0][2], "remote-devbox")

            index = self.dialogue_kb.build_index(archive_dir)
            self.assertEqual(index["total"], 1)
            self.assertEqual(index["conversations"][0]["id"], "conv-123")
            self.assertEqual(index["conversations"][0]["host"], "remote-devbox")
            self.assertEqual(index["conversations"][0]["project"], "project-alpha")

    def test_cmd_collect_surfaces_remote_errors(self):
        args = Namespace(archive_dir="/tmp/dialogue-kb-test")
        with patch.object(self.dialogue_kb, "resolve_remote_hosts", return_value=(["remote-devbox"], "指定 1 台: remote-devbox")), \
             patch.object(self.dialogue_kb, "collect_local", return_value=[]), \
             patch.object(
                 self.dialogue_kb,
                 "collect_remote",
                 return_value=[
                     {
                         "host": "remote-devbox",
                         "tool": "cursor",
                         "status": "error",
                         "files_synced": 0,
                         "message": "SSH timeout after 180s",
                     }
                 ],
             ), \
             patch.object(
                 self.dialogue_kb,
                 "build_index",
                 return_value={"total": 0, "stats": {}},
             ):
            output = io.StringIO()
            with redirect_stdout(output):
                self.dialogue_kb.cmd_collect(args)

        rendered = output.getvalue()
        self.assertIn("SSH timeout after 180s", rendered)
        self.assertNotIn("remote-devbox ... 无新文件", rendered)


class ApplyDistillStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_dialogue_kb_module()

    def test_new_entry_gets_pending(self):
        entry = {}
        self.m._apply_distill_state(entry, None, 5)
        self.assertEqual(entry["distill_state"], "pending")

    def test_done_with_growth_becomes_outdated(self):
        entry = {}
        old = {"distill_state": "done", "turn_count": 5, "distilled_at": "2026-01-01"}
        self.m._apply_distill_state(entry, old, 8)
        self.assertEqual(entry["distill_state"], "outdated")
        self.assertEqual(entry["_prev_turn_count"], 5)
        self.assertEqual(entry["distilled_at"], "2026-01-01")

    def test_done_without_growth_stays_done(self):
        entry = {}
        old = {"distill_state": "done", "turn_count": 5}
        self.m._apply_distill_state(entry, old, 5)
        self.assertEqual(entry["distill_state"], "done")

    def test_skipped_stays_skipped(self):
        entry = {}
        old = {"distill_state": "skipped", "turn_count": 3, "skip_reason": "too short"}
        self.m._apply_distill_state(entry, old, 10)
        self.assertEqual(entry["distill_state"], "skipped")
        self.assertEqual(entry["skip_reason"], "too short")

    def test_pending_with_growth_stays_pending(self):
        entry = {}
        old = {"distill_state": "pending", "turn_count": 3}
        self.m._apply_distill_state(entry, old, 6)
        self.assertEqual(entry["distill_state"], "pending")


class ComputeWorthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_dialogue_kb_module()

    def test_too_few_turns(self):
        self.assertEqual(self.m._compute_worth({"turn_count": 1, "user_turns": 1, "assistant_turns": 0}), "auto_skip")

    def test_no_assistant_turns(self):
        self.assertEqual(self.m._compute_worth({"turn_count": 3, "user_turns": 3, "assistant_turns": 0}), "auto_skip")

    def test_no_user_turns(self):
        self.assertEqual(self.m._compute_worth({"turn_count": 3, "user_turns": 0, "assistant_turns": 3}), "auto_skip")

    def test_command_title(self):
        entry = {"turn_count": 5, "user_turns": 3, "assistant_turns": 2, "title": "test", "first_question": "/model gpt-4"}
        self.assertEqual(self.m._compute_worth(entry), "auto_skip")

    def test_untitled_short(self):
        entry = {"turn_count": 3, "user_turns": 2, "assistant_turns": 1, "title": "Untitled", "first_question": "hi"}
        self.assertEqual(self.m._compute_worth(entry), "auto_skip")

    def test_normal_conversation(self):
        entry = {"turn_count": 6, "user_turns": 3, "assistant_turns": 3, "title": "Fix ESLint config", "first_question": "How to fix ESLint?"}
        self.assertEqual(self.m._compute_worth(entry), "normal")


class TimestampSortValueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_dialogue_kb_module()

    def test_none(self):
        self.assertEqual(self.m._timestamp_sort_value(None), 0.0)

    def test_empty_string(self):
        self.assertEqual(self.m._timestamp_sort_value(""), 0.0)

    def test_iso_string(self):
        val = self.m._timestamp_sort_value("2026-03-15T10:00:00+00:00")
        self.assertGreater(val, 0)

    def test_iso_z_suffix(self):
        val = self.m._timestamp_sort_value("2026-03-15T10:00:00Z")
        self.assertGreater(val, 0)

    def test_unix_seconds(self):
        val = self.m._timestamp_sort_value(1710500000)
        self.assertAlmostEqual(val, 1710500000.0)

    def test_unix_milliseconds(self):
        val = self.m._timestamp_sort_value(1710500000000)
        self.assertAlmostEqual(val, 1710500000.0)

    def test_invalid_string(self):
        self.assertEqual(self.m._timestamp_sort_value("not-a-date"), 0.0)


class ResolveConvIdsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_dialogue_kb_module()

    def test_resolve_by_number(self):
        with TemporaryDirectory() as tmpdir:
            archive_dir = Path(tmpdir)
            index = {"conversations": [
                {"id": "aaa"}, {"id": "bbb"}, {"id": "ccc"}
            ]}
            (archive_dir / "index.json").write_text(
                json.dumps(index), encoding="utf-8"
            )
            result = self.m._resolve_conv_ids(archive_dir, ["2"])
            self.assertEqual(result, ["bbb"])

    def test_resolve_by_id(self):
        with TemporaryDirectory() as tmpdir:
            archive_dir = Path(tmpdir)
            index = {"conversations": [
                {"id": "aaa"}, {"id": "bbb"}
            ]}
            (archive_dir / "index.json").write_text(
                json.dumps(index), encoding="utf-8"
            )
            result = self.m._resolve_conv_ids(archive_dir, ["aaa"])
            self.assertEqual(result, ["aaa"])

    def test_resolve_mixed(self):
        with TemporaryDirectory() as tmpdir:
            archive_dir = Path(tmpdir)
            index = {"conversations": [
                {"id": "aaa"}, {"id": "bbb"}, {"id": "ccc"}
            ]}
            (archive_dir / "index.json").write_text(
                json.dumps(index), encoding="utf-8"
            )
            result = self.m._resolve_conv_ids(archive_dir, ["1", "ccc", "999"])
            self.assertEqual(result, ["aaa", "ccc"])

    def test_resolve_missing_index(self):
        with TemporaryDirectory() as tmpdir:
            result = self.m._resolve_conv_ids(Path(tmpdir), ["1"])
            self.assertEqual(result, [])

    def test_resolve_corrupt_index(self):
        with TemporaryDirectory() as tmpdir:
            archive_dir = Path(tmpdir)
            (archive_dir / "index.json").write_text(
                "not valid json{{{", encoding="utf-8"
            )
            result = self.m._resolve_conv_ids(archive_dir, ["1"])
            self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
