from home_ventilation.daemon import _compute_wait_timeout


def test_poll_wakes_before_reconciliation():
    """poll_interval=30 should wake loop before reconciliation_interval=60."""
    timeout = _compute_wait_timeout(
        poll_interval=30,
        reconciliation_interval=60,
        last_sensor_poll=100.0,
        last_command_times={"fan1": 100.0},
        now_monotonic=100.0,
    )
    assert timeout == 30.0


def test_reconciliation_sooner_than_poll():
    """When reconciliation is due sooner, it should win."""
    timeout = _compute_wait_timeout(
        poll_interval=30,
        reconciliation_interval=60,
        last_sensor_poll=95.0,  # 5s ago, next poll in 25s
        last_command_times={"fan1": 50.0},  # 50s ago, next reconciliation in 10s
        now_monotonic=100.0,
    )
    assert timeout == 10.0


def test_overdue_deadlines_clamp_to_zero():
    """Overdue deadlines should result in 0, not negative."""
    timeout = _compute_wait_timeout(
        poll_interval=30,
        reconciliation_interval=60,
        last_sensor_poll=50.0,  # 50s ago, overdue
        last_command_times={"fan1": 30.0},  # 70s ago, overdue
        now_monotonic=100.0,
    )
    assert timeout == 0.0


def test_multiple_fans_soonest_reconciliation_wins():
    """With multiple fans, the soonest reconciliation deadline wins."""
    timeout = _compute_wait_timeout(
        poll_interval=30,
        reconciliation_interval=60,
        last_sensor_poll=100.0,  # just polled, next in 30s
        last_command_times={"fan1": 100.0, "fan2": 55.0},  # fan2 due in 15s
        now_monotonic=100.0,
    )
    assert timeout == 15.0


def test_initial_state_forces_immediate():
    """last_sensor_poll=0 means first poll is immediate."""
    timeout = _compute_wait_timeout(
        poll_interval=30,
        reconciliation_interval=60,
        last_sensor_poll=0.0,
        last_command_times={"fan1": 0.0},
        now_monotonic=100.0,
    )
    assert timeout == 0.0


def test_no_fans_uses_poll_interval():
    """With no fans, only poll interval matters."""
    timeout = _compute_wait_timeout(
        poll_interval=30,
        reconciliation_interval=60,
        last_sensor_poll=100.0,
        last_command_times={},
        now_monotonic=100.0,
    )
    assert timeout == 30.0
