from dataclasses import dataclass
from datetime import datetime,timezone
from enum import Enum
from typing import Optional
from uuid import uuid4
from pydantic import BaseModel,ConfigDict,Field,model_validator
from backend_memory_pipeline.ingestion.ingestion import SessionRecordV1
class SessionManagerErrorCode(str,Enum):
    INVALID_SESSION="INVALID_SESSION"
    SESSION_NOT_FOUND="SESSION_NOT_FOUND"
    SESSION_ALREADY_EXISTS="SESSION_ALREADY_EXISTS"
    SUBJECT_MISMATCH="SUBJECT_MISMATCH"
    SESSION_ALREADY_ENDED="SESSION_ALREADY_ENDED"
    SESSION_ALREADY_EXPIRED="SESSION_ALREADY_EXPIRED"
    INVALID_TIMESTAMP="INVALID_TIMESTAMP"
class SessionManagerError(Exception):
    def __init__(self,code:SessionManagerErrorCode,message:str):
        self.code=code
        self.message=message
        super().__init__(message)
class SessionStatus(str,Enum):
    ACTIVE="active"
    ENDED="ended"
    EXPIRED="expired"
class SessionStartRequestV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    subject_id:str=Field(min_length=1,max_length=128)
    session_id:Optional[str]=Field(default=None,max_length=128)
    session_start:datetime
    primary_domain:Optional[str]=Field(default=None,max_length=128)
    session_context:Optional[str]=Field(default=None,max_length=256)
    device_type:Optional[str]=Field(default=None,max_length=64)
    platform:Optional[str]=Field(default=None,max_length=64)
    synthetic:bool=False
    @model_validator(mode="after")
    def validate_request(self):
        if self.session_start.tzinfo is None or self.session_start.utcoffset() is None:
            raise ValueError("session_start must be timezone-aware.")
        if self.session_id is not None and not self.session_id.strip():
            raise ValueError("session_id cannot be empty when supplied.")
        return self
class SessionStartResultV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    session_id:str=Field(min_length=1,max_length=128)
    subject_id:str=Field(min_length=1,max_length=128)
    session_start:datetime
    last_activity_at:datetime
    status:SessionStatus
    synthetic:bool
class SessionStateV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    session_id:str=Field(min_length=1,max_length=128)
    subject_id:str=Field(min_length=1,max_length=128)
    session_start:datetime
    last_activity_at:datetime
    session_end:Optional[datetime]=None
    primary_domain:Optional[str]=None
    session_context:Optional[str]=None
    device_type:Optional[str]=None
    platform:Optional[str]=None
    synthetic:bool=False
    status:SessionStatus=SessionStatus.ACTIVE
    @model_validator(mode="after")
    def validate_state(self):
        if self.session_start.tzinfo is None or self.session_start.utcoffset() is None:
            raise ValueError("session_start must be timezone-aware.")
        if self.last_activity_at.tzinfo is None or self.last_activity_at.utcoffset() is None:
            raise ValueError("last_activity_at must be timezone-aware.")
        if self.last_activity_at<self.session_start:
            raise ValueError("last_activity_at cannot be before session_start.")
        if self.session_end is not None:
            if self.session_end.tzinfo is None or self.session_end.utcoffset() is None:
                raise ValueError("session_end must be timezone-aware.")
            if self.session_end<=self.session_start:
                raise ValueError("session_end must be after session_start.")
            if self.session_end<self.last_activity_at:
                raise ValueError("session_end cannot be before last_activity_at.")
        if self.status==SessionStatus.ACTIVE and self.session_end is not None:
            raise ValueError("Active sessions cannot have a session_end.")
        if self.status in {SessionStatus.ENDED,SessionStatus.EXPIRED} and self.session_end is None:
            raise ValueError("Ended or expired sessions must have a session_end.")
        return self
    def to_session_record(self)->SessionRecordV1:
        if self.status not in {SessionStatus.ENDED,SessionStatus.EXPIRED}:
            raise SessionManagerError(
                SessionManagerErrorCode.INVALID_SESSION,
                "Only ended or expired sessions can be converted to SessionRecordV1."
            )
        if self.session_end is None:
            raise SessionManagerError(
                SessionManagerErrorCode.INVALID_SESSION,
                "Completed session must have a session_end."
            )
        duration=int((self.session_end-self.session_start).total_seconds())
        return SessionRecordV1(
            schema_version=self.schema_version,
            session_id=self.session_id,
            user_id=self.subject_id,
            session_start=self.session_start,
            session_end=self.session_end,
            session_duration_seconds=duration,
            primary_domain=self.primary_domain,
            session_context=self.session_context,
            device_type=self.device_type,
            platform=self.platform
        )
@dataclass(frozen=True)
class SessionManagerResultV1:
    status:str
    session:SessionStateV1
class SessionStore:
    def get(self,session_id:str)->Optional[SessionStateV1]:
        raise NotImplementedError
    def save(self,session:SessionStateV1)->None:
        raise NotImplementedError
    def delete(self,session_id:str)->None:
        raise NotImplementedError
    def list_by_subject(self,subject_id:str)->list[SessionStateV1]:
        raise NotImplementedError
    def list_all(self)->list[SessionStateV1]:
        raise NotImplementedError
class InMemorySessionStore(SessionStore):
    def __init__(self):
        self._records:dict[str,SessionStateV1]={}
    def get(self,session_id:str)->Optional[SessionStateV1]:
        return self._records.get(session_id)
    def save(self,session:SessionStateV1)->None:
        self._records[session.session_id]=session
    def delete(self,session_id:str)->None:
        self._records.pop(session_id,None)
    def list_by_subject(self,subject_id:str)->list[SessionStateV1]:
        return [
            session
            for session in self._records.values()
            if session.subject_id==subject_id
        ]
    def list_all(self)->list[SessionStateV1]:
        return list(self._records.values())
class SessionManager:
    def __init__(
        self,
        store:Optional[SessionStore]=None,
        idle_timeout_seconds:int=1800,
        max_session_duration_seconds:Optional[int]=None
    ):
        if idle_timeout_seconds<=0:
            raise ValueError("idle_timeout_seconds must be greater than zero.")
        self.store=store or InMemorySessionStore()
        self.idle_timeout_seconds=idle_timeout_seconds
        self.max_session_duration_seconds=max_session_duration_seconds
    def start_session(
        self,
        request:SessionStartRequestV1
    )->SessionManagerResultV1:
        if not isinstance(request,SessionStartRequestV1):
            raise SessionManagerError(
                SessionManagerErrorCode.INVALID_SESSION,
                "Input must be a SessionStartRequestV1."
            )
        session_id=(
            request.session_id
            if request.session_id is not None
            else self.new_session_id()
        )
        existing=self.store.get(session_id)
        if existing is not None:
            raise SessionManagerError(
                SessionManagerErrorCode.SESSION_ALREADY_EXISTS,
                "Session ID is already associated with an existing session."
            )
        session=SessionStateV1(
            schema_version=request.schema_version,
            session_id=session_id,
            subject_id=request.subject_id,
            session_start=request.session_start,
            last_activity_at=request.session_start,
            session_end=None,
            primary_domain=request.primary_domain,
            session_context=request.session_context,
            device_type=request.device_type,
            platform=request.platform,
            synthetic=request.synthetic,
            status=SessionStatus.ACTIVE
        )
        self.store.save(session)
        return SessionManagerResultV1(
            status="started",
            session=session
        )
    def get_session(
        self,
        session_id:str,
        authorized_subject_id:Optional[str]=None,
        now:Optional[datetime]=None
    )->SessionManagerResultV1:
        session=self._get_authorized_session(
            session_id,
            authorized_subject_id
        )
        current_time=self._normalize_now(now)
        if session.status==SessionStatus.ACTIVE and self._is_idle(
            session,
            current_time
        ):
            session=self._expire_session(
                session,
                current_time
            )
            return SessionManagerResultV1(
                status="expired",
                session=session
            )
        return SessionManagerResultV1(
            status=session.status.value,
            session=session
        )
    def touch_session(
        self,
        session_id:str,
        activity_at:Optional[datetime]=None,
        authorized_subject_id:Optional[str]=None
    )->SessionManagerResultV1:
        session=self._get_authorized_session(
            session_id,
            authorized_subject_id
        )
        activity_timestamp=self._normalize_now(activity_at)
        if session.status==SessionStatus.ENDED:
            raise SessionManagerError(
                SessionManagerErrorCode.SESSION_ALREADY_ENDED,
                "Session has already ended."
            )
        if session.status==SessionStatus.EXPIRED:
            raise SessionManagerError(
                SessionManagerErrorCode.SESSION_ALREADY_EXPIRED,
                "Session has already expired."
            )
        if activity_timestamp<session.last_activity_at:
            raise SessionManagerError(
                SessionManagerErrorCode.INVALID_TIMESTAMP,
                "activity_at cannot be before last_activity_at."
            )
        updated=SessionStateV1(
            schema_version=session.schema_version,
            session_id=session.session_id,
            subject_id=session.subject_id,
            session_start=session.session_start,
            last_activity_at=activity_timestamp,
            session_end=None,
            primary_domain=session.primary_domain,
            session_context=session.session_context,
            device_type=session.device_type,
            platform=session.platform,
            synthetic=session.synthetic,
            status=SessionStatus.ACTIVE
        )
        self.store.save(updated)
        return SessionManagerResultV1(
            status="active",
            session=updated
        )
    def end_session(
        self,
        session_id:str,
        session_end:Optional[datetime]=None,
        authorized_subject_id:Optional[str]=None
    )->SessionManagerResultV1:
        session=self._get_authorized_session(
            session_id,
            authorized_subject_id
        )
        if session.status==SessionStatus.ENDED:
            raise SessionManagerError(
                SessionManagerErrorCode.SESSION_ALREADY_ENDED,
                "Session has already ended."
            )
        if session.status==SessionStatus.EXPIRED:
            raise SessionManagerError(
                SessionManagerErrorCode.SESSION_ALREADY_EXPIRED,
                "Session has already expired."
            )
        end_timestamp=self._normalize_now(session_end)
        if end_timestamp<=session.session_start:
            raise SessionManagerError(
                SessionManagerErrorCode.INVALID_TIMESTAMP,
                "session_end must be after session_start."
            )
        if end_timestamp<session.last_activity_at:
            raise SessionManagerError(
                SessionManagerErrorCode.INVALID_TIMESTAMP,
                "session_end cannot be before last_activity_at."
            )
        completed=SessionStateV1(
            schema_version=session.schema_version,
            session_id=session.session_id,
            subject_id=session.subject_id,
            session_start=session.session_start,
            last_activity_at=session.last_activity_at,
            session_end=end_timestamp,
            primary_domain=session.primary_domain,
            session_context=session.session_context,
            device_type=session.device_type,
            platform=session.platform,
            synthetic=session.synthetic,
            status=SessionStatus.ENDED
        )
        self.store.save(completed)
        return SessionManagerResultV1(
            status="ended",
            session=completed
        )
    def expire_session(
        self,
        session_id:str,
        expired_at:Optional[datetime]=None,
        authorized_subject_id:Optional[str]=None
    )->SessionManagerResultV1:
        session=self._get_authorized_session(
            session_id,
            authorized_subject_id
        )
        if session.status==SessionStatus.ENDED:
            raise SessionManagerError(
                SessionManagerErrorCode.SESSION_ALREADY_ENDED,
                "Session has already ended."
            )
        if session.status==SessionStatus.EXPIRED:
            return SessionManagerResultV1(
                status="expired",
                session=session
            )
        expiration_timestamp=self._normalize_now(expired_at)
        if expiration_timestamp<session.last_activity_at:
            expiration_timestamp=session.last_activity_at
        expired=self._expire_session(
            session,
            expiration_timestamp
        )
        return SessionManagerResultV1(
            status="expired",
            session=expired
        )
    def expire_inactive_sessions(
        self,
        now:Optional[datetime]=None
    )->list[SessionManagerResultV1]:
        current_time=self._normalize_now(now)
        results=[]
        for session in self.store.list_all():
            if session.status!=SessionStatus.ACTIVE:
                continue
            if self._is_idle(session,current_time):
                expired=self._expire_session(
                    session,
                    current_time
                )
                results.append(
                    SessionManagerResultV1(
                        status="expired",
                        session=expired
                    )
                )
        return results
    def get_current_subject_sessions(
        self,
        subject_id:str,
        now:Optional[datetime]=None
    )->list[SessionStateV1]:
        if not isinstance(subject_id,str) or not subject_id.strip():
            raise SessionManagerError(
                SessionManagerErrorCode.INVALID_SESSION,
                "subject_id is required."
            )
        current_time=self._normalize_now(now)
        sessions=[]
        for session in self.store.list_by_subject(subject_id):
            if session.status==SessionStatus.ACTIVE and self._is_idle(
                session,
                current_time
            ):
                session=self._expire_session(
                    session,
                    current_time
                )
            sessions.append(session)
        return sessions
    def get_active_session(
        self,
        subject_id:str,
        now:Optional[datetime]=None
    )->Optional[SessionStateV1]:
        sessions=self.get_current_subject_sessions(
            subject_id,
            now
        )
        active=[
            session
            for session in sessions
            if session.status==SessionStatus.ACTIVE
        ]
        if not active:
            return None
        active.sort(
            key=lambda session:session.last_activity_at,
            reverse=True
        )
        return active[0]
    def is_session_active(
        self,
        session_id:str,
        authorized_subject_id:Optional[str]=None,
        now:Optional[datetime]=None
    )->bool:
        result=self.get_session(
            session_id,
            authorized_subject_id,
            now
        )
        return result.session.status==SessionStatus.ACTIVE
    @staticmethod
    def new_session_id()->str:
        return f"session:{uuid4()}"
    def _get_authorized_session(
        self,
        session_id:str,
        authorized_subject_id:Optional[str]
    )->SessionStateV1:
        if not isinstance(session_id,str) or not session_id.strip():
            raise SessionManagerError(
                SessionManagerErrorCode.INVALID_SESSION,
                "session_id is required."
            )
        session=self.store.get(session_id)
        if session is None:
            raise SessionManagerError(
                SessionManagerErrorCode.SESSION_NOT_FOUND,
                "Session was not found."
            )
        if (
            authorized_subject_id is not None
            and session.subject_id!=authorized_subject_id
        ):
            raise SessionManagerError(
                SessionManagerErrorCode.SUBJECT_MISMATCH,
                "Authenticated subject does not match session subject."
            )
        return session
    def _is_idle(
        self,
        session:SessionStateV1,
        now:datetime
    )->bool:
        idle_seconds=(
            now-session.last_activity_at
        ).total_seconds()
        return idle_seconds>=self.idle_timeout_seconds
    def _expire_session(
        self,
        session:SessionStateV1,
        expiration_timestamp:datetime
    )->SessionStateV1:
        expired=SessionStateV1(
            schema_version=session.schema_version,
            session_id=session.session_id,
            subject_id=session.subject_id,
            session_start=session.session_start,
            last_activity_at=session.last_activity_at,
            session_end=expiration_timestamp,
            primary_domain=session.primary_domain,
            session_context=session.session_context,
            device_type=session.device_type,
            platform=session.platform,
            synthetic=session.synthetic,
            status=SessionStatus.EXPIRED
        )
        self.store.save(expired)
        return expired
    @staticmethod
    def _normalize_now(value:Optional[datetime])->datetime:
        timestamp=value or datetime.now(timezone.utc)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise SessionManagerError(
                SessionManagerErrorCode.INVALID_TIMESTAMP,
                "Timestamp must be timezone-aware."
            )
        return timestamp