"""测试 API 函数（使用 mock）。"""

from __future__ import annotations

import pytest

from haiqikeji.api import extract_token


class TestExtractToken:
    def test_data_is_token_string(self):
        result = {"code": 200, "data": "abc123.token.here"}
        assert extract_token(result) == "abc123.token.here"

    def test_data_is_token_with_whitespace(self):
        result = {"code": 200, "data": "  abc123  "}
        assert extract_token(result) == "abc123"

    def test_no_token_raises(self):
        result = {"code": 200, "data": {"userId": 1}}
        with pytest.raises(ValueError, match="未找到 token"):
            extract_token(result)

    def test_empty_data_string_raises(self):
        result = {"code": 200, "data": ""}
        with pytest.raises(ValueError, match="未找到 token"):
            extract_token(result)

    def test_data_dict_empty_token_raises(self):
        result = {"code": 200, "data": {"token": "  "}}
        with pytest.raises(ValueError, match="未找到 token"):
            extract_token(result)
