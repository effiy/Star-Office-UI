"""
Unit tests for dsh_bridge components.

Tests state_reader, state_pusher, and agent_mapper with mock JSON data.
Uses stdlib unittest + mock — no extra dependencies.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import modules under test
import state_reader
import state_pusher
import agent_mapper


class TestStateReader(unittest.TestCase):
    """Tests for DSH state file parsing."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.state_file = Path(self.tmpdir.name) / "state.json"
        self.inflight_file = Path(self.tmpdir.name) / "inflight.json"

    def tearDown(self):
        self.tmpdir.cleanup()

    def _write_json(self, path: Path, data: dict) -> None:
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_empty_state_returns_empty_dict(self):
        """No state file → empty states dict."""
        with patch.object(state_reader, "DSH_STATE_FILE", self.state_file):
            with patch.object(state_reader, "DSH_INFLIGHT_FILE", self.inflight_file):
                result = state_reader.get_dsh_bot_states()
        self.assertEqual(result, {})

    def test_idle_bot_produces_idle_state(self):
        """Bot with no active segment and not in inflight → idle."""
        self._write_json(self.state_file, {
            "bots": {
                "bot-1": {"name": "TestBot", "segments": []}
            }
        })
        with patch.object(state_reader, "DSH_STATE_FILE", self.state_file):
            with patch.object(state_reader, "DSH_INFLIGHT_FILE", self.inflight_file):
                result = state_reader.get_dsh_bot_states()
        self.assertEqual(result, {"TestBot": "idle"})

    def test_active_segment_produces_writing_state(self):
        """Bot with an unterminated segment → writing."""
        self._write_json(self.state_file, {
            "bots": {
                "bot-1": {"name": "WriterBot", "segments": [
                    {"endedAt": None}
                ]}
            }
        })
        with patch.object(state_reader, "DSH_STATE_FILE", self.state_file):
            with patch.object(state_reader, "DSH_INFLIGHT_FILE", self.inflight_file):
                result = state_reader.get_dsh_bot_states()
        self.assertEqual(result, {"WriterBot": "writing"})

    def test_inflight_bot_produces_executing_state(self):
        """Bot in inflight → executing (overrides writing)."""
        self._write_json(self.state_file, {
            "bots": {
                "bot-1": {"name": "ExecBot", "segments": [
                    {"endedAt": None}
                ]}
            }
        })
        self._write_json(self.inflight_file, {
            "turns": {
                "turn-1": {"botId": "bot-1"}
            }
        })
        with patch.object(state_reader, "DSH_STATE_FILE", self.state_file):
            with patch.object(state_reader, "DSH_INFLIGHT_FILE", self.inflight_file):
                result = state_reader.get_dsh_bot_states()
        self.assertEqual(result, {"ExecBot": "executing"})

    def test_chief_is_excluded(self):
        """Chief bot is excluded from regular state push."""
        self._write_json(self.state_file, {
            "bots": {
                "bot-chief": {"name": "Chief", "segments": []},
                "bot-1": {"name": "Worker", "segments": []},
            }
        })
        with patch.object(state_reader, "DSH_STATE_FILE", self.state_file):
            with patch.object(state_reader, "DSH_INFLIGHT_FILE", self.inflight_file):
                result = state_reader.get_dsh_bot_states()
        self.assertNotIn("Chief", result)
        self.assertIn("Worker", result)

    def test_unnamed_bot_is_skipped(self):
        """Bots without a name field are skipped."""
        self._write_json(self.state_file, {
            "bots": {
                "bot-1": {"segments": []}  # no "name" field
            }
        })
        with patch.object(state_reader, "DSH_STATE_FILE", self.state_file):
            with patch.object(state_reader, "DSH_INFLIGHT_FILE", self.inflight_file):
                result = state_reader.get_dsh_bot_states()
        self.assertEqual(result, {})

    def test_is_chief_busy_false_when_no_match(self):
        """is_chief_busy returns False when Chief is not in inflight."""
        self._write_json(self.inflight_file, {
            "turns": {
                "turn-1": {"botId": "other-bot"}
            }
        })
        with patch.object(state_reader, "DSH_INFLIGHT_FILE", self.inflight_file):
            result = state_reader.is_chief_busy()
        self.assertFalse(result)

    def test_is_chief_busy_true_when_chief_active(self):
        """is_chief_busy returns True when Chief session is in inflight."""
        self._write_json(self.inflight_file, {
            "turns": {
                "turn-1": {"botId": state_reader.CHIEF_SESSION_ID}
            }
        })
        with patch.object(state_reader, "DSH_INFLIGHT_FILE", self.inflight_file):
            result = state_reader.is_chief_busy()
        self.assertTrue(result)


class TestStatePusher(unittest.TestCase):
    """Tests for pixel office HTTP client."""

    def test_get_detail_known_states(self):
        """All known states should map to non-empty labels."""
        for state in ["executing", "writing", "idle", "syncing", "error"]:
            with self.subTest(state=state):
                label = state_pusher.get_detail(state)
                self.assertIsInstance(label, str)
                self.assertTrue(len(label) > 0, f"empty label for {state}")

    def test_get_detail_unknown_state(self):
        """Unknown states should return empty string."""
        self.assertEqual(state_pusher.get_detail("unknown"), "")

    def test_push_chief_state_payload(self):
        """push_chief_state sends correct JSON payload."""
        with patch("state_pusher._http_post") as mock_post:
            mock_post.return_value = {"ok": True}
            result = state_pusher.push_chief_state("executing")
        self.assertTrue(result)
        mock_post.assert_called_once()
        url, payload = mock_post.call_args[0]
        self.assertIn("/set_state", url)
        self.assertEqual(payload["state"], "executing")
        self.assertEqual(payload["detail"], state_pusher.get_detail("executing"))

    def test_push_agent_state_payload(self):
        """push_agent_state sends correct agent-push payload."""
        with patch("state_pusher._http_post") as mock_post:
            mock_post.return_value = {"ok": True}
            result = state_pusher.push_agent_state("TestBot", "agent-1", "executing")
        self.assertTrue(result)
        mock_post.assert_called_once()
        url, payload = mock_post.call_args[0]
        self.assertIn("/agent-push", url)
        self.assertEqual(payload["agentId"], "agent-1")
        self.assertEqual(payload["name"], "TestBot")
        self.assertEqual(payload["state"], "executing")

    def test_push_agent_state_returns_false_on_error(self):
        """Failed HTTP POST returns False."""
        with patch("state_pusher._http_post", return_value=None):
            result = state_pusher.push_agent_state("Bot", "id", "idle")
        self.assertFalse(result)

    def test_push_agent_state_returns_false_on_not_ok(self):
        """Non-ok response returns False."""
        with patch("state_pusher._http_post", return_value={"ok": False, "msg": "bad"}):
            result = state_pusher.push_agent_state("Bot", "id", "idle")
        self.assertFalse(result)


class TestAgentMapper(unittest.TestCase):
    """Tests for agent name → ID mapping cache."""

    def tearDown(self):
        # Reset module-level cache between tests
        agent_mapper._cache = None

    def test_get_agent_id_returns_none_when_not_loaded(self):
        """Without load_agent_mappings, get_agent_id returns None."""
        agent_mapper._cache = None
        self.assertIsNone(agent_mapper.get_agent_id("AnyBot"))

    def test_get_agent_id_after_load(self):
        """After loading, lookups work."""
        with patch("agent_mapper.fetch_agent_map") as mock_fetch:
            mock_fetch.return_value = {"BotA": "agent-a", "BotB": "agent-b"}
            agent_mapper.load_agent_mappings()
        self.assertEqual(agent_mapper.get_agent_id("BotA"), "agent-a")
        self.assertEqual(agent_mapper.get_agent_id("BotB"), "agent-b")
        self.assertIsNone(agent_mapper.get_agent_id("Unknown"))

    def test_refresh_mappings(self):
        """refresh_mappings updates the cache."""
        with patch("agent_mapper.fetch_agent_map") as mock_fetch:
            mock_fetch.side_effect = [
                {"BotA": "agent-a"},
                {"BotA": "agent-a-new"},
            ]
            agent_mapper.load_agent_mappings()
            self.assertEqual(agent_mapper.get_agent_id("BotA"), "agent-a")
            agent_mapper.refresh_mappings()
            self.assertEqual(agent_mapper.get_agent_id("BotA"), "agent-a-new")


if __name__ == "__main__":
    unittest.main()