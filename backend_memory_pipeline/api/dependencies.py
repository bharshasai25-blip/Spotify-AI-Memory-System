import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime,timedelta,timezone
from typing import Annotated,Optional
from fastapi import Depends,HTTPException,status
from fastapi.security import HTTPAuthorizationCredentials,HTTPBearer
from functools import lru_cache
from backend_memory_pipeline.persistence.neo4j.graph_store import Neo4jGraphStore
from backend_memory_pipeline.context_composition.context_composition import ContextCompositionService
from backend_memory_pipeline.embedding.embedding import EmbeddingService,InMemoryEmbeddingStore,SentenceTransformerEmbeddingProvider
from backend_memory_pipeline.event_validation.event_validation import EventValidator
from backend_memory_pipeline.graph_memory.graph import GraphMemoryService,InMemoryGraphStore
from backend_memory_pipeline.ingestion.ingestion import IngestionService
from backend_memory_pipeline.memory_extraction.memory_extraction import MemoryExtractionService
from backend_memory_pipeline.session_management.session_management import (SessionManager)
from backend_memory_pipeline.memory_lifecycle.memory_lifecycle import InMemoryMemoryStore,MemoryLifecycleService
from backend_memory_pipeline.orchestration.orchestration import (
    InMemoryEvidenceHistoryStore,
    MemoryControlOrchestrator,
    MemoryQueryOrchestrator,
    MemoryWriteOrchestrator
)
from backend_memory_pipeline.policy_consent.policy_consent import (
    DefaultPolicyEngine,
    PolicyConsentService
)
from backend_memory_pipeline.response_generation.response_generation import ResponseGenerationService,DeterministicMemoryGroundedGenerator
from backend_memory_pipeline.retrieval.retrieval import InMemoryRetrievalStore,RetrievalService,SentenceTransformerQueryEmbeddingProvider
@dataclass(frozen=True)
class APIUser:
    username:str
    subject_id:str
    password_hash:str
    metadata:dict[str,object]
class InMemoryUserRepository:
    def __init__(self):
        self._users:dict[str,APIUser]={}
        self._subjects:dict[str,str]={}
    def get_by_username(self,username:str)->Optional[APIUser]:
        return self._users.get(username)
    def get_by_subject_id(self,subject_id:str)->Optional[APIUser]:
        username=self._subjects.get(subject_id)
        if username is None:
            return None
        return self._users.get(username)
    def create_user(
        self,
        username:str,
        password_hash:str,
        subject_id:Optional[str]=None,
        metadata:Optional[dict[str,object]]=None
    )->APIUser:
        normalized_username=username.strip().lower()
        if not normalized_username:
            raise ValueError("username cannot be empty.")
        if normalized_username in self._users:
            raise ValueError("username already exists.")
        new_subject_id=subject_id or f"USER_{secrets.token_hex(12).upper()}"
        while new_subject_id in self._subjects:
            new_subject_id=f"USER_{secrets.token_hex(12).upper()}"
        user=APIUser(
            username=normalized_username,
            subject_id=new_subject_id,
            password_hash=password_hash,
            metadata=dict(metadata or {})
        )
        self._users[normalized_username]=user
        self._subjects[new_subject_id]=normalized_username
        return user
_user_repository=InMemoryUserRepository()
@dataclass(frozen=True)
class AuthenticatedSubject:
    subject_id:str
    username:str
    token_id:str
class InMemoryRevokedTokenStore:
    def __init__(self):
        self._revoked_tokens:set[str]=set()

    def revoke(self,token_id:str)->None:
        if not token_id or not token_id.strip():
            raise ValueError("token_id is required.")
        self._revoked_tokens.add(token_id)

    def is_revoked(self,token_id:str)->bool:
        return token_id in self._revoked_tokens

    def clear(self)->None:
        self._revoked_tokens.clear()


_revoked_token_store=InMemoryRevokedTokenStore()


def get_revoked_token_store()->InMemoryRevokedTokenStore:
    return _revoked_token_store


def revoke_token(token_id:str)->None:
    get_revoked_token_store().revoke(token_id)


def is_token_revoked(token_id:str)->bool:
    return get_revoked_token_store().is_revoked(token_id)    
def get_user_repository()->InMemoryUserRepository:
    return _user_repository
bearer_scheme=HTTPBearer(auto_error=False)
def _get_auth_secret()->str:
    secret=os.getenv("API_AUTH_SECRET")
    if not secret:
        raise RuntimeError(
            "API_AUTH_SECRET is not configured."
        )
    if len(secret)<32:
        raise RuntimeError(
            "API_AUTH_SECRET must contain at least 32 characters."
        )
    return secret
def _get_password_salt()->str:
    return os.getenv(
        "API_PASSWORD_SALT",
        "spotify-ai-memory-development-salt"
    )
def _hash_password(password:str)->str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        _get_password_salt().encode("utf-8"),
        200000
    ).hex()
def verify_password(password:str,password_hash:str)->bool:
    supplied_hash=_hash_password(password)
    return hmac.compare_digest(
        supplied_hash,
        password_hash
    )
def authenticate_user(
    username:str,
    password:str,
    user_repository:Optional[InMemoryUserRepository]=None
)->Optional[APIUser]:
    repository=user_repository or get_user_repository()
    normalized_username=username.strip().lower()
    user=repository.get_by_username(normalized_username)
    if user is None:
        return None
    if not verify_password(password,user.password_hash):
        return None
    return user
def register_user(
    username:str,
    password:str,
    metadata:Optional[dict[str,object]]=None,
    user_repository:Optional[InMemoryUserRepository]=None
)->APIUser:
    repository=user_repository or get_user_repository()
    password_hash=_hash_password(password)
    return repository.create_user(
        username=username,
        password_hash=password_hash,
        metadata=metadata
    )
def _urlsafe_encode(value:bytes)->str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")
def _urlsafe_decode(value:str)->bytes:
    padding="="*((4-len(value)%4)%4)
    return base64.urlsafe_b64decode(
        value+padding
    )
def create_access_token(
    subject_id:str,
    username:str,
    expires_in_seconds:int=3600
)->str:
    if expires_in_seconds<=0:
        raise ValueError(
            "expires_in_seconds must be greater than zero."
        )
    now=datetime.now(timezone.utc)
    token_id=secrets.token_hex(16)
    payload={
        "sub":subject_id,
        "username":username,
        "iat":int(now.timestamp()),
        "exp":int(
            (
                now+timedelta(
                    seconds=expires_in_seconds
                )
            ).timestamp()
        ),
        "token_id":token_id
    }
    header={
        "alg":"HS256",
        "typ":"JWT"
    }
    encoded_header=_urlsafe_encode(
        json.dumps(
            header,
            separators=(",",":"),
            sort_keys=True
        ).encode("utf-8")
    )
    encoded_payload=_urlsafe_encode(
        json.dumps(
            payload,
            separators=(",",":"),
            sort_keys=True
        ).encode("utf-8")
    )
    signing_input=f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature=hmac.new(
        _get_auth_secret().encode("utf-8"),
        signing_input,
        hashlib.sha256
    ).digest()
    encoded_signature=_urlsafe_encode(signature)
    return f"{encoded_header}.{encoded_payload}.{encoded_signature}"
def decode_access_token(token:str)->AuthenticatedSubject:
    parts=token.split(".")
    if len(parts)!=3:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate":"Bearer"}
        )
    encoded_header,encoded_payload,encoded_signature=parts
    signing_input=f"{encoded_header}.{encoded_payload}".encode("ascii")
    expected_signature=hmac.new(
        _get_auth_secret().encode("utf-8"),
        signing_input,
        hashlib.sha256
    ).digest()
    try:
        supplied_signature=_urlsafe_decode(encoded_signature)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate":"Bearer"}
        ) from exc
    if not hmac.compare_digest(
        supplied_signature,
        expected_signature
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate":"Bearer"}
        )
    try:
        header=json.loads(
            _urlsafe_decode(encoded_header).decode("utf-8")
        )
        payload=json.loads(
            _urlsafe_decode(encoded_payload).decode("utf-8")
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate":"Bearer"}
        ) from exc
    if header.get("alg")!="HS256" or header.get("typ")!="JWT":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate":"Bearer"}
        )
    subject_id=payload.get("sub")
    username=payload.get("username")
    token_id=payload.get("token_id")
    expires_at=payload.get("exp")
    issued_at=payload.get("iat")
    if not isinstance(subject_id,str) or not subject_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has no valid subject.",
            headers={"WWW-Authenticate":"Bearer"}
        )
    if not isinstance(username,str) or not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has no valid username.",
            headers={"WWW-Authenticate":"Bearer"}
        )
    if not isinstance(token_id,str) or not token_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has no valid token identity.",
            headers={"WWW-Authenticate":"Bearer"}
        )
    if not isinstance(expires_at,int):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has no valid expiry.",
            headers={"WWW-Authenticate":"Bearer"}
        )
    if not isinstance(issued_at,int):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has no valid issued-at timestamp.",
            headers={"WWW-Authenticate":"Bearer"}
        )
    now_timestamp=int(datetime.now(timezone.utc).timestamp())
    if now_timestamp>=expires_at:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired.",
            headers={"WWW-Authenticate":"Bearer"}
        )
    return AuthenticatedSubject(
        subject_id=subject_id,
        username=username,
        token_id=token_id
    )
def get_current_subject(
    credentials:Annotated[
        Optional[HTTPAuthorizationCredentials],
        Depends(bearer_scheme)
    ]
)->AuthenticatedSubject:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate":"Bearer"}
        )
    if credentials.scheme.lower()!="bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer authentication is required.",
            headers={"WWW-Authenticate":"Bearer"}
        )
    authenticated_subject=decode_access_token(
        credentials.credentials
    )

    if is_token_revoked(
        authenticated_subject.token_id
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has been revoked.",
            headers={"WWW-Authenticate":"Bearer"}
        )

    return authenticated_subject
    #return decode_access_token(credentials.credentials)
def require_subject(
    requested_subject_id:str,
    authenticated:AuthenticatedSubject
)->None:
    if requested_subject_id!=authenticated.subject_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authenticated subject does not match requested subject."
        )
def get_ingestion_service()->IngestionService:
    return IngestionService()

@lru_cache(maxsize=1)
def get_session_manager()->SessionManager:
    return SessionManager()

@lru_cache(maxsize=1)
def get_memory_store() -> InMemoryMemoryStore:
    return InMemoryMemoryStore()

@lru_cache(maxsize=1)
def get_evidence_history_store()->InMemoryEvidenceHistoryStore:
    return InMemoryEvidenceHistoryStore()


@lru_cache(maxsize=1)
def get_graph_store() -> InMemoryGraphStore:
    return InMemoryGraphStore()


@lru_cache(maxsize=1)
def get_embedding_store() -> InMemoryEmbeddingStore:
    return InMemoryEmbeddingStore()

@lru_cache(maxsize=1)
def get_neo4j_graph_store()->Neo4jGraphStore:
    uri=os.getenv("NEO4J_URI","bolt://localhost:7687")
    username=os.getenv("NEO4J_USERNAME","neo4j")
    password=os.getenv("NEO4J_PASSWORD","password")
    database=os.getenv("NEO4J_DATABASE","neo4j")
    store=Neo4jGraphStore(
        uri=uri,
        username=username,
        password=password,
        database=database,
    )
    store.verify_connectivity()
    return store

@lru_cache(maxsize=1)
def get_memory_write_orchestrator()->MemoryWriteOrchestrator:
    return MemoryWriteOrchestrator(
        ingestion_service=IngestionService(),
        event_validator=EventValidator(),
        extraction_service=MemoryExtractionService(),
        policy_consent_service=PolicyConsentService(DefaultPolicyEngine()),
        lifecycle_service=MemoryLifecycleService(get_memory_store()),
        #graph_service=GraphMemoryService(get_graph_store()),
        graph_service=GraphMemoryService(get_neo4j_graph_store()),
        embedding_service=EmbeddingService(store=get_embedding_store(),
            provider=SentenceTransformerEmbeddingProvider("all-MiniLM-L6-v2")),
            evidence_history_store=get_evidence_history_store())
@lru_cache(maxsize=1)
def get_memory_control_orchestrator()->MemoryControlOrchestrator:
    write_orchestrator=get_memory_write_orchestrator()
    return MemoryControlOrchestrator(
        policy_consent_service=write_orchestrator.policy_consent,
        lifecycle_service=write_orchestrator.lifecycle,
        extraction_service=write_orchestrator.extractor,
        entity_resolution_service=write_orchestrator.entity_resolver,
        graph_service=write_orchestrator.graph,
        embedding_service=write_orchestrator.embedding
    )
@lru_cache(maxsize=1)
def get_memory_query_orchestrator()->MemoryQueryOrchestrator:
    write_orchestrator = get_memory_write_orchestrator()
    retrieval_store=InMemoryRetrievalStore(get_graph_store(),get_embedding_store())
    return MemoryQueryOrchestrator(
        retrieval_service=RetrievalService(retrieval_store,
        query_provider=SentenceTransformerQueryEmbeddingProvider("all-MiniLM-L6-v2")),
        policy_consent_service=write_orchestrator.policy_consent,
        context_service=ContextCompositionService(),
        response_service=ResponseGenerationService(generator=DeterministicMemoryGroundedGenerator(),
            model_name="deterministic",model_version="deterministic-v1"),
        lifecycle_service=write_orchestrator.lifecycle)
CurrentSubject=Annotated[
    AuthenticatedSubject,
    Depends(get_current_subject)
]
