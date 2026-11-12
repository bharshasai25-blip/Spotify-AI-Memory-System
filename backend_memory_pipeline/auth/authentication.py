from dataclasses import dataclass
from datetime import datetime,timezone
from typing import FrozenSet,Optional,Protocol

class AuthenticationError(Exception):
    pass
@dataclass(frozen=True)
class AuthContext:
    subject_id:str
    authenticated:bool
    authenticated_at:datetime
    auth_method:str
    scopes:FrozenSet[str]
    token_id:Optional[str]=None

class Authenticator(Protocol):
    def authenticate(self,credential:str)->AuthContext:
        ...

class AuthenticationService:
    def __init__(self,authenticator:Authenticator):
        self.authenticator=authenticator

    def authenticate(self,credential:str)->AuthContext:
        if not credential or not credential.strip():
            raise AuthenticationError("Authentication credential is required.")
        context=self.authenticator.authenticate(credential)
        self._validate_context(context)
        return context
    
    @staticmethod
    def _validate_context(context:AuthContext)->None:
        if not isinstance(context,AuthContext):
            raise AuthenticationError("Authenticator returned an invalid authentication context.")
        if not context.authenticated:
            raise AuthenticationError("Authentication failed.")
        if not context.subject_id or not context.subject_id.strip():
            raise AuthenticationError("Authenticated identity is missing.")
        if not context.auth_method or not context.auth_method.strip():
            raise AuthenticationError("Authentication method is missing.")
        if not isinstance(context.scopes,frozenset):
            raise AuthenticationError("Authentication scopes must be a frozen set.")
        if context.authenticated_at.tzinfo is None:
            raise AuthenticationError("Authentication timestamp must be timezone-aware.")
        
class MockAuthenticator:
    def __init__(self,credentials:dict[str,AuthContext]):
        self._credentials=credentials.copy()

    def authenticate(self,credential:str)->AuthContext:
        context=self._credentials.get(credential)
        if context is None:
            raise AuthenticationError("Invalid authentication credential.")
        return context
    
def create_test_auth_context(subject_id:str,scopes:set[str],auth_method:str="mock")->AuthContext:
    return AuthContext(
        subject_id=subject_id,
        authenticated=True,
        authenticated_at=datetime.now(timezone.utc),
        auth_method=auth_method,
        scopes=frozenset(scopes)
    )