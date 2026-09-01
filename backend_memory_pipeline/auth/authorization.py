from dataclasses import dataclass
from typing import Optional
from .authentication import AuthContext

class AuthorizationError(Exception):
    pass

@dataclass(frozen=True)
class AuthorizationRequest:
    operation:str
    subject_id:str
    resource_subject_id:Optional[str]=None

class AuthorizationService:
    def __init__(self,operation_scopes:Optional[dict[str,str]]=None):
        self.operation_scopes=operation_scopes or {
            "memory:read":"memory:read",
            "memory:write":"memory:write",
            "memory:correct":"memory:correct",
            "memory:delete":"memory:delete",
            "memory:explain":"memory:explain"
        }
    def authorize(self,auth_context:AuthContext,operation:str,subject_id:str,resource_subject_id:Optional[str]=None)->None:
        self._validate_authentication(auth_context)
        self._validate_operation(operation)
        self._validate_subject(subject_id)
        if auth_context.subject_id!=subject_id:
            raise AuthorizationError("Authenticated subject does not match requested subject.")
        if resource_subject_id is not None:
            self._validate_subject(resource_subject_id)
            if auth_context.subject_id!=resource_subject_id:
               raise AuthorizationError("Cross-subject access is not authorized.")
        required_scope=self.operation_scopes[operation]
        if required_scope not in auth_context.scopes:
            raise AuthorizationError(f"Missing required scope: {required_scope}")
        
    def authorize_request(self,auth_context:AuthContext,request:AuthorizationRequest)->None:
        self.authorize(
            auth_context=auth_context,
            operation=request.operation,
            subject_id=request.subject_id,
            resource_subject_id=request.resource_subject_id
        )

    @staticmethod
    def _validate_authentication(auth_context:AuthContext)->None:
        if not isinstance(auth_context,AuthContext):
            raise AuthorizationError("Invalid authentication context.")
        if not auth_context.authenticated:
            raise AuthorizationError("Authenticated identity is required.")
        if not auth_context.subject_id or not auth_context.subject_id.strip():
            raise AuthorizationError("Authenticated subject identity is missing.")
        
    def _validate_operation(self,operation:str)->None:
        if not operation or not operation.strip():
            raise AuthorizationError("Authorization operation is required.")
        if operation not in self.operation_scopes:
            raise AuthorizationError(f"Unsupported authorization operation: {operation}")
        
    @staticmethod
    def _validate_subject(subject_id:str)->None:
        if not subject_id or not subject_id.strip():
            raise AuthorizationError("Subject identity is required.")