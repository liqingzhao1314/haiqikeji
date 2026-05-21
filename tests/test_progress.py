"""测试进度条渲染函数。"""

from __future__ import annotations

from haiqikeji.progress import _format_time, _render_progress_bar


class TestFormatTime:
    def test_zero(self):
        assert _format_time(0) == "00:00:00"

    def test_seconds_only(self):
        assert _format_time(45) == "00:00:45"

    def test_minutes_and_seconds(self):
        assert _format_time(125) == "00:02:05"

    def test_hours_minutes_seconds(self):
        assert _format_time(3725) == "01:02:05"

    def test_negative(self):
        assert _format_time(-10) == "00:00:00"

    def test_float(self):
        assert _format_time(61.7) == "00:01:01"


class TestRenderProgressBar:
    def test_basic_render(self):
        bar = _render_progress_bar(50, 100, 0, bar_width=20)
        assert bar.startswith("\r")
        assert "00:00:50" in bar
        assert "00:01:40" in bar
        assert "[" in bar
        assert "]" in bar

    def test_zero_progress(self):
        bar = _render_progress_bar(0, 100, 0, bar_width=10)
        assert "00:00:00" in bar
        # Should contain spinner at position 0
        assert "_" in bar

    def test_full_progress(self):
        bar = _render_progress_bar(100, 100, 0, bar_width=10)
        assert "00:01:40" in bar
        inner = bar.split("[")[1].split("]")[0]
        assert "-" in inner

    def test_spinner_rotation(self):
        bar1 = _render_progress_bar(50, 100, 0, bar_width=20)
        bar2 = _render_progress_bar(50, 100, 1, bar_width=20)
        # Different frames should produce different spinner characters
        spinner1 = bar1.split("[")[1].split("]")[0]
        spinner2 = bar2.split("[")[1].split("]")[0]
        # At least the spinner character should differ
        assert spinner1 != spinner2
