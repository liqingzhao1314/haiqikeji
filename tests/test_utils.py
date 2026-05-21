"""测试工具函数。"""

from __future__ import annotations

from datetime import date

from haiqikeji.utils import (
    build_node_progress_map,
    coerce_duration_seconds,
    coerce_percentage,
    course_matches,
    get_resume_progress_percent,
    is_complete_progress,
    is_unexpired_course,
)


class TestCoercePercentage:
    def test_bool_values_are_not_numbers(self):
        assert coerce_percentage(True) is None
        assert coerce_percentage(False) is None

    def test_int(self):
        assert coerce_percentage(60) == 60.0

    def test_float(self):
        assert coerce_percentage(75.5) == 75.5

    def test_numeric_string(self):
        assert coerce_percentage("0.60") == 0.6
        assert coerce_percentage(" 100 ") == 100.0

    def test_percent_suffixed_string_is_invalid(self):
        assert coerce_percentage("100%") is None

    def test_string_empty(self):
        assert coerce_percentage("") is None

    def test_string_whitespace(self):
        assert coerce_percentage("   ") is None

    def test_string_invalid(self):
        assert coerce_percentage("abc") is None

    def test_none(self):
        assert coerce_percentage(None) is None

    def test_list(self):
        assert coerce_percentage([1, 2]) is None


class TestCoerceDurationSeconds:
    def test_positive_int_seconds(self):
        assert coerce_duration_seconds(300) == 300.0

    def test_non_int_values_are_invalid(self):
        assert coerce_duration_seconds(60.5) is None
        assert coerce_duration_seconds(True) is None
        assert coerce_duration_seconds("120") is None
        assert coerce_duration_seconds("13分27秒") is None
        assert coerce_duration_seconds(None) is None

    def test_non_positive_seconds_are_invalid(self):
        assert coerce_duration_seconds(0) is None
        assert coerce_duration_seconds(-1) is None


class TestIsUnexpiredCourse:
    def test_active_course(self):
        course = {"endDate": "2099-12-31"}
        assert is_unexpired_course(course, date(2026, 1, 1)) is True

    def test_expired_course(self):
        course = {"endDate": "2020-01-01"}
        assert is_unexpired_course(course, date(2026, 1, 1)) is False

    def test_missing_end_date(self):
        course = {}
        assert is_unexpired_course(course, date(2026, 1, 1)) is False

    def test_exact_match(self):
        course = {"endDate": "2026-05-17"}
        assert is_unexpired_course(course, date(2026, 5, 17)) is True


class TestCourseMatches:
    def test_no_filter(self):
        course = {"id": 1, "courseName": "数学"}
        assert course_matches(course, None, None) is True

    def test_id_match(self):
        course = {"id": 42, "courseName": "数学"}
        assert course_matches(course, 42, None) is True

    def test_id_no_match(self):
        course = {"id": 42, "courseName": "数学"}
        assert course_matches(course, 99, None) is False

    def test_name_match_case_insensitive(self):
        course = {"id": 1, "courseName": "Advanced Mathematics"}
        assert course_matches(course, None, "math") is True

    def test_name_no_match(self):
        course = {"id": 1, "courseName": "数学"}
        assert course_matches(course, None, "物理") is False

    def test_both_filters_match(self):
        course = {"id": 1, "courseName": "数学"}
        assert course_matches(course, 1, "数学") is True

    def test_both_filters_partial_no_match(self):
        course = {"id": 1, "courseName": "数学"}
        assert course_matches(course, 2, "数学") is False


class TestIsCompleteProgress:
    def test_none(self):
        assert is_complete_progress(None) is False

    def test_non_dict_values_are_incomplete(self):
        assert is_complete_progress(True) is False
        assert is_complete_progress(100) is False
        assert is_complete_progress("已完成") is False
        assert is_complete_progress([{"state": 1}]) is False

    def test_real_completed_record(self):
        progress = {
            "progressRatio": "1.00",
            "statusText": "已完成",
            "progressPercent": 100,
            "state": 1,
        }
        assert is_complete_progress(progress) is True

    def test_complete_when_state_is_one(self):
        assert is_complete_progress({"state": 1}) is True

    def test_bool_state_one_is_not_complete(self):
        assert is_complete_progress({"state": True}) is False

    def test_complete_when_status_text_is_completed(self):
        assert is_complete_progress({"statusText": "已完成"}) is True

    def test_other_status_text_is_incomplete(self):
        assert is_complete_progress({"statusText": "学习中"}) is False

    def test_complete_when_progress_percent_reaches_100(self):
        assert is_complete_progress({"progressPercent": 100}) is True
        assert is_complete_progress({"progressPercent": "100"}) is True

    def test_percent_suffixed_progress_percent_is_not_supported(self):
        assert is_complete_progress({"progressPercent": "100%"}) is False

    def test_incomplete_when_progress_percent_below_100(self):
        assert is_complete_progress({"progressPercent": 99.99}) is False

    def test_complete_when_progress_ratio_reaches_one(self):
        assert is_complete_progress({"progressRatio": 1}) is True
        assert is_complete_progress({"progressRatio": "1.00"}) is True

    def test_incomplete_when_progress_ratio_below_one(self):
        assert is_complete_progress({"progressRatio": 0.99}) is False
        assert is_complete_progress({"progressRatio": "0.99"}) is False

    def test_ignores_old_hypothetical_fields(self):
        assert is_complete_progress({"isComplete": True}) is False
        assert is_complete_progress({"status": "done"}) is False
        assert is_complete_progress({"progress": 100}) is False


class TestBuildNodeProgressMap:
    def test_builds_map_from_progress_list(self):
        first = {"nodeId": 1, "progressRatio": "1.00"}
        second = {"nodeId": 2, "progressPercent": 50}
        progress_data = {"nodeProgressList": [first, second]}

        assert build_node_progress_map(progress_data) == {1: first, 2: second}

    def test_ignores_items_without_int_node_id(self):
        progress_data = {
            "nodeProgressList": [
                {"nodeId": "1", "progressRatio": "1.00"},
                {"nodeId": True, "progressRatio": "1.00"},
                {"nodeId": False, "progressRatio": "1.00"},
                {"progressRatio": "0.50"},
                ["not", "a", "dict"],
                {"nodeId": 3, "progressPercent": 20},
            ]
        }

        assert build_node_progress_map(progress_data) == {3: {"nodeId": 3, "progressPercent": 20}}

    def test_missing_progress_list_returns_empty_map(self):
        assert build_node_progress_map({}) == {}

    def test_non_dict_input_returns_empty_map(self):
        assert build_node_progress_map(None) == {}
        assert build_node_progress_map([]) == {}


class TestGetResumeProgressPercent:
    def test_last_progress_string_ratio(self):
        assert get_resume_progress_percent("0.60") == 60.0

    def test_last_progress_string_clamped_max(self):
        assert get_resume_progress_percent("1.00") == 99.0

    def test_last_progress_invalid_string(self):
        assert get_resume_progress_percent("abc") == 0.0

    def test_non_dict_non_string(self):
        assert get_resume_progress_percent(123) == 0.0

    def test_dict_prefers_progress_ratio(self):
        progress = {"progressRatio": "0.60", "progressPercent": 30}
        assert get_resume_progress_percent(progress) == 60.0

    def test_dict_progress_ratio_is_clamped(self):
        assert get_resume_progress_percent({"progressRatio": "1.00"}) == 99.0

    def test_dict_uses_progress_percent_after_ratio(self):
        progress = {"progressPercent": 75}
        assert get_resume_progress_percent(progress) == 75.0

    def test_dict_progress_percent_is_clamped(self):
        assert get_resume_progress_percent({"progressPercent": 100}) == 99.0

    def test_dict_ignores_old_hypothetical_fields(self):
        progress = {"currentProgress": 75, "lastProgress": 80, "watchPercent": 90}
        assert get_resume_progress_percent(progress) == 0.0
