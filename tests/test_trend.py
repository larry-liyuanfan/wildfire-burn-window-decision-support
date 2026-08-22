import pytest

from burnwindows.trend import moving_block_bootstrap_mean_ci


def test_moving_block_bootstrap_mean_is_seeded_and_bounded() -> None:
    interval = moving_block_bootstrap_mean_ci(
        [0.1, 0.2, 0.3, 0.4],
        block_size=2,
        samples=200,
        seed=7,
    )

    assert interval == pytest.approx((0.15, 0.35))
    assert moving_block_bootstrap_mean_ci(
        [0.1, 0.2, 0.3, 0.4],
        block_size=2,
        samples=200,
        seed=7,
    ) == pytest.approx(interval)
