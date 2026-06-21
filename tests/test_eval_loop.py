from litnav.eval.loop import should_stop


def test_stops_on_plateau():
    assert should_stop([0.50, 0.505, 0.508], eps=0.01, cap=10, plateau_n=2)[0] is True


def test_continues_when_still_climbing():
    assert should_stop([0.50, 0.60, 0.72], eps=0.01, cap=10, plateau_n=2)[0] is False


def test_stops_at_cap():
    assert should_stop([0.1] * 10, eps=0.01, cap=10, plateau_n=2)[0] is True


def test_short_curve_continues():
    assert should_stop([0.50], eps=0.01, cap=10, plateau_n=2)[0] is False
