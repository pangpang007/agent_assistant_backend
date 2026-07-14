from app.services.rate_limit_service import is_over_limit, remaining_quota


class TestRateLimitHelpers:
    def test_not_over(self):
        assert is_over_limit(30, 30) is False
        assert is_over_limit(29, 30) is False

    def test_over(self):
        assert is_over_limit(31, 30) is True

    def test_remaining(self):
        assert remaining_quota(10, 30) == 20
        assert remaining_quota(30, 30) == 0
        assert remaining_quota(40, 30) == 0
