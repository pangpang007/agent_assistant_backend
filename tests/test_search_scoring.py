from app.services.search_service import compute_search_score


class TestComputeSearchScore:
    def test_exact_match(self):
        assert compute_search_score("代码审查", "代码审查") == 1.0

    def test_prefix_match(self):
        assert compute_search_score("代码审查工作流", "代码") == 0.8

    def test_substring_match(self):
        assert compute_search_score("我的代码审查", "代码") == 0.5

    def test_no_match(self):
        assert compute_search_score("hello", "world") == 0.1

    def test_empty(self):
        assert compute_search_score("", "x") == 0.0
        assert compute_search_score("x", "") == 0.0
        assert compute_search_score("x", "   ") == 0.0

    def test_case_insensitive(self):
        assert compute_search_score("HelloWorld", "hello") == 0.8
