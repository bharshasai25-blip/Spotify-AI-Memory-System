import pytest
from datetime import datetime,timezone,timedelta
from backend_memory_pipeline.session_management.session_management import (
    InMemorySessionStore,
    SessionManager,
    SessionManagerError,
    SessionManagerErrorCode,
    SessionStartRequestV1,
    SessionStateV1,
    SessionStatus
)
def make_start_request(
    subject_id="TEST_USER_001",
    session_id=None,
    start=None,
    synthetic=False
):
    return SessionStartRequestV1(
        subject_id=subject_id,
        session_id=session_id,
        session_start=start or datetime(2026,8,26,10,0,0,tzinfo=timezone.utc),
        primary_domain="music",
        session_context="general",
        device_type="mobile",
        platform="app",
        synthetic=synthetic
    )
def test_real_session_generates_session_id():
    manager=SessionManager()
    result=manager.start_session(
        make_start_request()
    )
    assert result.status=="started"
    assert result.session.status==SessionStatus.ACTIVE
    assert result.session.session_id.startswith("session:")
    assert result.session.subject_id=="TEST_USER_001"
def test_synthetic_session_preserves_supplied_session_id():
    manager=SessionManager()
    result=manager.start_session(
        make_start_request(
            session_id="SESSION_SYNTHETIC_001",
            synthetic=True
        )
    )
    assert result.session.session_id=="SESSION_SYNTHETIC_001"
    assert result.session.synthetic is True
    assert result.session.status==SessionStatus.ACTIVE
def test_new_session_starts_active():
    manager=SessionManager()
    start=datetime(2026,8,26,10,0,0,tzinfo=timezone.utc)
    result=manager.start_session(
        make_start_request(start=start)
    )
    assert result.session.status==SessionStatus.ACTIVE
    assert result.session.session_start==start
    assert result.session.last_activity_at==start
    assert result.session.session_end is None
def test_session_can_be_retrieved():
    manager=SessionManager()
    result=manager.start_session(
        make_start_request()
    )
    session_id=result.session.session_id
    fetched=manager.get_session(
        session_id,
        authorized_subject_id="TEST_USER_001",
        now=datetime(2026,8,26,10,5,0,tzinfo=timezone.utc)
    )
    assert fetched.session.session_id==session_id
    assert fetched.session.status==SessionStatus.ACTIVE
def test_touch_session_updates_last_activity():
    manager=SessionManager()
    result=manager.start_session(
        make_start_request()
    )
    session_id=result.session.session_id
    activity_at=datetime(2026,8,26,10,10,0,tzinfo=timezone.utc)
    touched=manager.touch_session(
        session_id,
        activity_at=activity_at,
        authorized_subject_id="TEST_USER_001"
    )
    assert touched.status=="active"
    assert touched.session.status==SessionStatus.ACTIVE
    assert touched.session.last_activity_at==activity_at
def test_explicit_end_changes_status_to_ended():
    manager=SessionManager()
    result=manager.start_session(
        make_start_request()
    )
    session_id=result.session.session_id
    end=datetime(2026,8,26,10,30,0,tzinfo=timezone.utc)
    ended=manager.end_session(
        session_id,
        session_end=end,
        authorized_subject_id="TEST_USER_001"
    )
    assert ended.status=="ended"
    assert ended.session.status==SessionStatus.ENDED
    assert ended.session.session_end==end
    assert ended.session.session_end is not None
def test_ended_session_converts_to_session_record():
    manager=SessionManager()
    result=manager.start_session(
        make_start_request()
    )
    session_id=result.session.session_id
    manager.end_session(
        session_id,
        session_end=datetime(2026,8,26,10,30,0,tzinfo=timezone.utc),
        authorized_subject_id="TEST_USER_001"
    )
    fetched=manager.get_session(
        session_id,
        authorized_subject_id="TEST_USER_001",
        now=datetime(2026,8,26,10,31,0,tzinfo=timezone.utc)
    )
    record=fetched.session.to_session_record()
    assert record.session_id==session_id
    assert record.user_id=="TEST_USER_001"
    assert record.session_duration_seconds==1800
def test_idle_session_expires():
    manager=SessionManager(
        idle_timeout_seconds=1800
    )
    result=manager.start_session(
        make_start_request()
    )
    session_id=result.session.session_id
    expiry_check=datetime(2026,8,26,10,30,0,tzinfo=timezone.utc)
    fetched=manager.get_session(
        session_id,
        authorized_subject_id="TEST_USER_001",
        now=expiry_check
    )
    assert fetched.status=="expired"
    assert fetched.session.status==SessionStatus.EXPIRED
    assert fetched.session.session_end==expiry_check
def test_session_remains_active_before_idle_timeout():
    manager=SessionManager(
        idle_timeout_seconds=1800
    )
    result=manager.start_session(
        make_start_request()
    )
    session_id=result.session.session_id
    check_time=datetime(2026,8,26,10,29,59,tzinfo=timezone.utc)
    fetched=manager.get_session(
        session_id,
        authorized_subject_id="TEST_USER_001",
        now=check_time
    )
    assert fetched.status=="active"
    assert fetched.session.status==SessionStatus.ACTIVE
def test_expire_inactive_sessions_expires_only_idle_sessions():
    manager=SessionManager(
        idle_timeout_seconds=1800
    )
    first=manager.start_session(
        make_start_request(
            session_id="SESSION_001"
        )
    )
    second=manager.start_session(
        make_start_request(
            session_id="SESSION_002"
        )
    )
    manager.touch_session(
        "SESSION_002",
        activity_at=datetime(
            2026,8,26,10,20,0,tzinfo=timezone.utc
        ),
        authorized_subject_id="TEST_USER_001"
    )
    results=manager.expire_inactive_sessions(
        now=datetime(
            2026,8,26,10,30,0,tzinfo=timezone.utc
        )
    )
    assert len(results)==1
    assert results[0].session.session_id=="SESSION_001"
    assert manager.get_session(
        "SESSION_001",
        authorized_subject_id="TEST_USER_001",
        now=datetime(
            2026,8,26,10,30,0,tzinfo=timezone.utc
        )
    ).session.status==SessionStatus.EXPIRED
    assert manager.get_session(
        "SESSION_002",
        authorized_subject_id="TEST_USER_001",
        now=datetime(
            2026,8,26,10,30,0,tzinfo=timezone.utc
        )
    ).session.status==SessionStatus.ACTIVE
def test_already_ended_session_cannot_be_ended_again():
    manager=SessionManager()
    result=manager.start_session(
        make_start_request()
    )
    session_id=result.session.session_id
    manager.end_session(
        session_id,
        session_end=datetime(
            2026,8,26,10,20,0,tzinfo=timezone.utc
        ),
        authorized_subject_id="TEST_USER_001"
    )
    with pytest.raises(SessionManagerError) as exc:
        manager.end_session(
            session_id,
            session_end=datetime(
                2026,8,26,10,30,0,tzinfo=timezone.utc
            ),
            authorized_subject_id="TEST_USER_001"
        )
    assert exc.value.code==SessionManagerErrorCode.SESSION_ALREADY_ENDED
def test_expired_session_cannot_be_touched():
    manager=SessionManager(
        idle_timeout_seconds=1800
    )
    result=manager.start_session(
        make_start_request()
    )
    session_id=result.session.session_id
    manager.expire_session(
        session_id,
        expired_at=datetime(
            2026,8,26,10,30,0,tzinfo=timezone.utc
        ),
        authorized_subject_id="TEST_USER_001"
    )
    with pytest.raises(SessionManagerError) as exc:
        manager.touch_session(
            session_id,
            activity_at=datetime(
                2026,8,26,10,31,0,tzinfo=timezone.utc
            ),
            authorized_subject_id="TEST_USER_001"
        )
    assert exc.value.code==SessionManagerErrorCode.SESSION_ALREADY_EXPIRED
def test_cross_subject_session_access_is_rejected():
    manager=SessionManager()
    result=manager.start_session(
        make_start_request(
            subject_id="TEST_USER_001"
        )
    )
    session_id=result.session.session_id
    with pytest.raises(SessionManagerError) as exc:
        manager.get_session(
            session_id,
            authorized_subject_id="TEST_USER_999"
        )
    assert exc.value.code==SessionManagerErrorCode.SUBJECT_MISMATCH
def test_cross_subject_session_touch_is_rejected():
    manager=SessionManager()
    result=manager.start_session(
        make_start_request(
            subject_id="TEST_USER_001"
        )
    )
    session_id=result.session.session_id
    with pytest.raises(SessionManagerError) as exc:
        manager.touch_session(
            session_id,
            activity_at=datetime(
                2026,8,26,10,10,0,tzinfo=timezone.utc
            ),
            authorized_subject_id="TEST_USER_999"
        )
    assert exc.value.code==SessionManagerErrorCode.SUBJECT_MISMATCH
def test_invalid_timezone_session_start_is_rejected():
    with pytest.raises(ValueError,match="session_start must be timezone-aware"):
        make_start_request(
            start=datetime(2026,8,26,10,0,0)
        )
def test_invalid_timezone_activity_timestamp_is_rejected():
    manager=SessionManager()
    result=manager.start_session(
        make_start_request()
    )
    session_id=result.session.session_id
    with pytest.raises(SessionManagerError) as exc:
        manager.touch_session(
            session_id,
            activity_at=datetime(2026,8,26,10,10,0),
            authorized_subject_id="TEST_USER_001"
        )
    assert exc.value.code==SessionManagerErrorCode.INVALID_TIMESTAMP
def test_duplicate_session_id_is_rejected():
    manager=SessionManager()
    manager.start_session(
        make_start_request(
            session_id="SESSION_DUPLICATE"
        )
    )
    with pytest.raises(SessionManagerError) as exc:
        manager.start_session(
            make_start_request(
                session_id="SESSION_DUPLICATE"
            )
        )
    assert exc.value.code==SessionManagerErrorCode.SESSION_ALREADY_EXISTS
def test_get_active_session_returns_latest_active_session():
    manager=SessionManager()
    manager.start_session(
        make_start_request(
            session_id="SESSION_001",
            start=datetime(
                2026,8,26,10,0,0,tzinfo=timezone.utc
            )
        )
    )
    manager.start_session(
        make_start_request(
            session_id="SESSION_002",
            start=datetime(
                2026,8,26,11,0,0,tzinfo=timezone.utc
            )
        )
    )
    active=manager.get_active_session(
        "TEST_USER_001",
        now=datetime(
            2026,8,26,11,5,0,tzinfo=timezone.utc
        )
    )
    assert active is not None
    assert active.session_id=="SESSION_002"
def test_get_active_session_returns_none_when_all_sessions_are_finished():
    manager=SessionManager()
    manager.start_session(
        make_start_request(
            session_id="SESSION_001"
        )
    )
    manager.end_session(
        "SESSION_001",
        session_end=datetime(
            2026,8,26,10,30,0,tzinfo=timezone.utc
        ),
        authorized_subject_id="TEST_USER_001"
    )
    active=manager.get_active_session(
        "TEST_USER_001",
        now=datetime(
            2026,8,26,11,0,0,tzinfo=timezone.utc
        )
    )
    assert active is None
def test_is_session_active_returns_correct_state():
    manager=SessionManager(
        idle_timeout_seconds=1800
    )
    result=manager.start_session(
        make_start_request()
    )
    session_id=result.session.session_id
    assert manager.is_session_active(
        session_id,
        authorized_subject_id="TEST_USER_001",
        now=datetime(
            2026,8,26,10,10,0,tzinfo=timezone.utc
        )
    ) is True
    assert manager.is_session_active(
        session_id,
        authorized_subject_id="TEST_USER_001",
        now=datetime(
            2026,8,26,10,30,0,tzinfo=timezone.utc
        )
    ) is False
def test_session_end_cannot_precede_last_activity():
    manager=SessionManager()
    result=manager.start_session(
        make_start_request()
    )
    session_id=result.session.session_id
    manager.touch_session(
        session_id,
        activity_at=datetime(
            2026,8,26,10,20,0,tzinfo=timezone.utc
        ),
        authorized_subject_id="TEST_USER_001"
    )
    with pytest.raises(SessionManagerError) as exc:
        manager.end_session(
            session_id,
            session_end=datetime(
                2026,8,26,10,10,0,tzinfo=timezone.utc
            ),
            authorized_subject_id="TEST_USER_001"
        )
    assert exc.value.code==SessionManagerErrorCode.INVALID_TIMESTAMP
def test_invalid_idle_timeout_is_rejected():
    with pytest.raises(ValueError,match="idle_timeout_seconds must be greater than zero"):
        SessionManager(
            idle_timeout_seconds=0
        )
def test_active_session_cannot_convert_to_session_record():
    manager=SessionManager()
    result=manager.start_session(
        make_start_request()
    )
    with pytest.raises(SessionManagerError) as exc:
        result.session.to_session_record()
    assert exc.value.code==SessionManagerErrorCode.INVALID_SESSION