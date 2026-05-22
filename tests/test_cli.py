"""测试 CLI 参数和刷课生命周期。"""

from __future__ import annotations

from unittest.mock import ANY, Mock

import pytest
import requests

from haiqikeji import cli
from haiqikeji.logging_config import DEFAULT_LOG_FILE


class TestBuildParser:
    def test_log_file_defaults_to_project_log_file(self):
        args = cli.build_parser().parse_args(["-n", "user", "-p", "password"])

        assert args.log_file == DEFAULT_LOG_FILE


class TestAutoStudyNode:
    def test_ctrl_c_ends_session_once_and_reraises(self, monkeypatch):
        study_session_end = Mock(return_value={"code": 200})
        monkeypatch.setattr(
            cli, "study_session_start", Mock(return_value={"code": 200, "data": "sid-1"})
        )
        monkeypatch.setattr(cli, "study_session_end", study_session_end)
        monkeypatch.setattr(cli.time, "sleep", Mock(side_effect=KeyboardInterrupt))

        with pytest.raises(KeyboardInterrupt):
            cli.auto_study_node(
                session=Mock(),
                token="token",
                school_id=10,
                student_id=20,
                course_id=30,
                node_id=40,
                node_name="小节",
                video_duration=100,
                heartbeat_interval_seconds=25,
                resume_progress=False,
            )

        study_session_end.assert_called_once_with(ANY, "token", "sid-1", 30)

    def test_normal_completion_ends_session_once(self, monkeypatch):
        study_session_end = Mock(return_value={"code": 200})
        monkeypatch.setattr(
            cli, "study_session_start", Mock(return_value={"code": 200, "data": "sid-1"})
        )
        monkeypatch.setattr(cli, "study_session_heartbeat", Mock(return_value={"code": 200}))
        monkeypatch.setattr(cli, "study_session_end", study_session_end)
        monkeypatch.setattr(cli.time, "monotonic", Mock(side_effect=[0, 2]))

        assert (
            cli.auto_study_node(
                session=Mock(),
                token="token",
                school_id=10,
                student_id=20,
                course_id=30,
                node_id=40,
                node_name="小节",
                video_duration=1,
                heartbeat_interval_seconds=1,
                resume_progress=False,
            )
            is True
        )

        study_session_end.assert_called_once_with(ANY, "token", "sid-1", 30)

    def test_heartbeat_failure_ends_session_once(self, monkeypatch):
        study_session_end = Mock(return_value={"code": 200})
        monkeypatch.setattr(
            cli, "study_session_start", Mock(return_value={"code": 200, "data": "sid-1"})
        )
        monkeypatch.setattr(
            cli, "study_session_heartbeat", Mock(return_value={"code": 500, "msg": "fail"})
        )
        monkeypatch.setattr(cli, "study_session_end", study_session_end)
        monkeypatch.setattr(cli.time, "monotonic", Mock(side_effect=[0, 2]))

        assert (
            cli.auto_study_node(
                session=Mock(),
                token="token",
                school_id=10,
                student_id=20,
                course_id=30,
                node_id=40,
                node_name="小节",
                video_duration=1,
                heartbeat_interval_seconds=1,
                resume_progress=False,
            )
            is False
        )

        study_session_end.assert_called_once_with(ANY, "token", "sid-1", 30)

    def test_request_exception_sends_last_progress_then_ends_session_once(self, monkeypatch):
        study_session_heartbeat = Mock(
            side_effect=[{"code": 200}, requests.RequestException("network"), {"code": 200}]
        )
        study_session_end = Mock(return_value={"code": 200})
        monkeypatch.setattr(
            cli, "study_session_start", Mock(return_value={"code": 200, "data": "sid-1"})
        )
        monkeypatch.setattr(cli, "study_session_heartbeat", study_session_heartbeat)
        monkeypatch.setattr(cli, "study_session_end", study_session_end)
        monkeypatch.setattr(cli.time, "monotonic", Mock(side_effect=[0, 2, 3, 5]))

        with pytest.raises(requests.RequestException):
            cli.auto_study_node(
                session=Mock(),
                token="token",
                school_id=10,
                student_id=20,
                course_id=30,
                node_id=40,
                node_name="小节",
                video_duration=2,
                heartbeat_interval_seconds=1,
                resume_progress=False,
            )

        assert study_session_heartbeat.call_count == 3
        study_session_end.assert_called_once_with(ANY, "token", "sid-1", 30)
