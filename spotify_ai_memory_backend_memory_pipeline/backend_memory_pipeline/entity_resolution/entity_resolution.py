from enum import Enum
from typing import Any,Optional,Protocol,Sequence
from pydantic import BaseModel,ConfigDict,Field
from backend_memory_pipeline.memory_extraction.memory_extraction import (
    ExtractedEntityMention,
    ExtractedMemoryCandidate
)
from backend_memory_pipeline.integration.musicbrainz.musicbrainz_client import MusicBrainzClientError
from backend_memory_pipeline.spotify.spotify_urls import spotify_link_for_catalog_entity
class EntityResolutionStatus(str,Enum):
    RESOLVED="resolved"
    AMBIGUOUS="ambiguous"
    UNRESOLVED="unresolved"
    REJECTED="rejected"
class EntityType(str,Enum):
    ARTIST="artist"
    TRACK="track"
    ALBUM="album"
    PLAYLIST="playlist"
    SHOW="show"
    EPISODE="episode"
    TOPIC="topic"
    ACTIVITY="activity"
    CONTEXT="context"
    UNKNOWN="unknown"
class EntityResolutionErrorCode(str,Enum):
    INVALID_CANDIDATE="INVALID_CANDIDATE"
    INVALID_ENTITY_MENTION="INVALID_ENTITY_MENTION"
    SUBJECT_MISMATCH="SUBJECT_MISMATCH"
    UNKNOWN_ENTITY_TYPE="UNKNOWN_ENTITY_TYPE"
    NO_MATCH="NO_MATCH"
    AMBIGUOUS_MATCH="AMBIGUOUS_MATCH"
    INVALID_CATALOG_RECORD="INVALID_CATALOG_RECORD"
class EntityResolutionError(Exception):
    def __init__(self,code:EntityResolutionErrorCode,message:str):
        self.code=code
        self.message=message
        super().__init__(message)
class CatalogEntityV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    entity_id:str=Field(min_length=1,max_length=256)
    entity_type:EntityType
    canonical_name:str=Field(min_length=1,max_length=1000)
    aliases:list[str]=Field(default_factory=list)
    normalized_name:Optional[str]=None
    owner_subject_id:Optional[str]=None
    metadata:dict[str,Any]=Field(default_factory=dict)
class ResolvedEntityV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    mention:str=Field(min_length=1,max_length=500)
    entity_type:EntityType
    canonical_id:Optional[str]=None
    canonical_name:Optional[str]=None
    resolution_status:EntityResolutionStatus
    confidence:float=Field(ge=0.0,le=1.0)
    matched_field:Optional[str]=None
    matched_value:Optional[str]=None
    owner_subject_id:Optional[str]=None
    reason:str=Field(min_length=1,max_length=2000)
    candidate_options:list[dict[str,Any]]=Field(default_factory=list)
class EntityResolutionResultV1(BaseModel):
    model_config=ConfigDict(extra="forbid")
    schema_version:str="1.0"
    candidate_id:str=Field(min_length=1,max_length=128)
    subject_id:str=Field(min_length=1,max_length=128)
    resolved_entities:list[ResolvedEntityV1]=Field(default_factory=list)
    resolution_status:EntityResolutionStatus
    unresolved_mentions:list[str]=Field(default_factory=list)
    ambiguous_mentions:list[str]=Field(default_factory=list)
class CatalogRepository(Protocol):
    def search(self,mention:str,entity_type:Optional[EntityType]=None)->Sequence[CatalogEntityV1]:
        ...
class InMemoryCatalogRepository:
    def __init__(self,entities:Sequence[CatalogEntityV1]):
        self.entities=list(entities)
        self._validate_catalog()
    def search(self,mention:str,entity_type:Optional[EntityType]=None)->Sequence[CatalogEntityV1]:
        normalized=normalize_entity_text(mention)
        results=[]
        for entity in self.entities:
            if entity_type is not None and entity.entity_type!=entity_type:
                continue
            values=[entity.canonical_name,*entity.aliases]
            if entity.normalized_name:
                values.append(entity.normalized_name)
            if any(normalized==normalize_entity_text(value) for value in values):
                results.append(entity)
        return results
    def _validate_catalog(self)->None:
        seen=set()
        for entity in self.entities:
            if entity.entity_id in seen:
                raise EntityResolutionError(
                    EntityResolutionErrorCode.INVALID_CATALOG_RECORD,
                    f"Duplicate catalog entity_id: {entity.entity_id}"
                )
            seen.add(entity.entity_id)

class EntityResolver(Protocol):
    def resolve_candidate(
        self,
        candidate:ExtractedMemoryCandidate
    )->EntityResolutionResultV1:
        ...

class CatalogEnrichmentService(Protocol):
    def enrich(
        self,
        entity_type: str,
        query: str,
    ) -> CatalogEntityV1:
        ...

class RuleBasedEntityResolver:
    EXACT_MATCH_CONFIDENCE=0.99
    ALIAS_MATCH_CONFIDENCE=0.95
    AMBIGUOUS_CONFIDENCE_THRESHOLD=0.75
    def __init__(self,catalog:CatalogRepository,enrichment_service:Optional[CatalogEnrichmentService]=None):
        self.catalog=catalog
        self.enrichment_service=enrichment_service
    def resolve_candidate(self,candidate:ExtractedMemoryCandidate)->EntityResolutionResultV1:
        self._validate_candidate(candidate)
        if not candidate.entities:
            return EntityResolutionResultV1(
                candidate_id=candidate.candidate_id,
                subject_id=candidate.subject_id,
                resolved_entities=[],
                resolution_status=EntityResolutionStatus.UNRESOLVED,
                unresolved_mentions=[],
                ambiguous_mentions=[]
            )
        resolved=[]
        unresolved=[]
        ambiguous=[]
        artist_context = next(
            (item.mention for item in candidate.entities
             if self._parse_entity_type(item.entity_type) == EntityType.ARTIST),
            None,
        )
        # Resolve tracks before context artists so an ambiguous recording can be
        # surfaced without persisting any unconfirmed contextual entity first.
        ordered_mentions=sorted(
            candidate.entities,
            key=lambda item: 0 if self._parse_entity_type(item.entity_type)==EntityType.TRACK else 1,
        )
        has_track_mentions=any(self._parse_entity_type(item.entity_type)==EntityType.TRACK for item in ordered_mentions)
        for index,mention in enumerate(ordered_mentions):
            # An artist extracted solely as track context disambiguates recordings;
            # it should not automatically become a separate preference selection.
            if has_track_mentions and self._parse_entity_type(mention.entity_type)==EntityType.ARTIST:
                continue
            context_artist = (
                artist_context
                if self._parse_entity_type(mention.entity_type) == EntityType.TRACK
                else None
            )
            result=self.resolve_mention(
                mention=mention,
                subject_id=candidate.subject_id,
                context_artist=context_artist
            )
            resolved.append(result)
            if result.resolution_status==EntityResolutionStatus.UNRESOLVED:
                unresolved.append(mention.mention)
            elif result.resolution_status==EntityResolutionStatus.AMBIGUOUS:
                ambiguous.append(mention.mention)
        status=self._aggregate_status(resolved)
        return EntityResolutionResultV1(
            candidate_id=candidate.candidate_id,
            subject_id=candidate.subject_id,
            resolved_entities=resolved,
            resolution_status=status,
            unresolved_mentions=unresolved,
            ambiguous_mentions=ambiguous
        )
    def resolve_mention(
        self,
        mention:ExtractedEntityMention,
        subject_id:str,
        context_artist:Optional[str]=None
    )->ResolvedEntityV1:
        entity_type=self._parse_entity_type(mention.entity_type)
        # A confirmed selection carries a canonical ID. Resolve that exact record
        # instead of searching by title again (several recordings can share a title).
        if mention.canonical_id:
            getter = getattr(type(self.catalog), "get", None)
            selected = self.catalog.get(mention.canonical_id) if callable(getter) else None
            if selected is not None and selected.entity_type == entity_type:
                if selected.owner_subject_id not in (None, subject_id):
                    return ResolvedEntityV1(mention=mention.mention, entity_type=entity_type, resolution_status=EntityResolutionStatus.REJECTED, confidence=0.0, reason="Selected entity is outside the authorized subject scope.")
                return ResolvedEntityV1(mention=mention.mention, entity_type=entity_type, canonical_id=selected.entity_id, canonical_name=selected.canonical_name, resolution_status=EntityResolutionStatus.RESOLVED, confidence=self.EXACT_MATCH_CONFIDENCE, matched_field="canonical_id", matched_value=selected.entity_id, owner_subject_id=selected.owner_subject_id, reason="Previously confirmed canonical entity ID.")
        matches=list(self.catalog.search(mention.mention,entity_type))
        if entity_type == EntityType.TRACK and context_artist and self.enrichment_service is not None:
            matches=[item for item in matches if self._artist_context_matches(item,context_artist)]
        # Search local canonical entities first, then ask MusicBrainz for additional
        # candidates. Merge by MBID so already-cataloged entities remain selectable
        # without creating duplicate catalog records during discovery.
        if self.enrichment_service is not None and entity_type != EntityType.UNKNOWN:
            search_candidates = getattr(type(self.enrichment_service), "search_candidates", None)
            if callable(search_candidates):
                try:
                    mb_options = self.enrichment_service.search_candidates(entity_type=entity_type.value, query=mention.mention, context_artist=context_artist) if entity_type == EntityType.TRACK and context_artist else self.enrichment_service.search_candidates(entity_type=entity_type.value, query=mention.mention)
                except (ValueError, LookupError, MusicBrainzClientError):
                    mb_options = []
                if not isinstance(mb_options, list):
                    mb_options = []
                options_by_mbid = {}
                for local in matches:
                    local_mbid = (local.metadata or {}).get("musicbrainz_id")
                    if not local_mbid and local.entity_id.startswith(f"musicbrainz:{entity_type.value}:"):
                        local_mbid = local.entity_id.rsplit(":", 1)[-1]
                    if isinstance(local_mbid, str) and local_mbid:
                        local_metadata = dict(local.metadata or {})
                        artist_names = local_metadata.get("artist_names", [])
                        artist_text = ", ".join(artist_names) if isinstance(artist_names, list) else ""
                        direct_url = None
                        list_mappings = getattr(self.catalog, "list_external_mappings", None)
                        if callable(list_mappings):
                            try:
                                mappings = list_mappings(local.entity_id)
                                direct_url = next((mapping.get("external_url") for mapping in mappings if isinstance(mapping, dict) and str(mapping.get("provider", "")).casefold() == "spotify" and mapping.get("external_url")), None)
                            except Exception:
                                direct_url = None
                        #from backend_memory_pipeline.spotify.spotify_urls import spotify_link_for_catalog_entity
                        option = {"mbid":local_mbid,"entity_type":entity_type.value,"name":local.canonical_name,"artist_names":artist_names if isinstance(artist_names, list) else [],"release_names":local_metadata.get("release_names", []),"disambiguation":local_metadata.get("disambiguation", ""),"already_cataloged":True,"canonical_id":local.entity_id}
                        option.update(spotify_link_for_catalog_entity(local.canonical_name, entity_type.value, artist_text, direct_url))
                        options_by_mbid[local_mbid] = option
                for option in mb_options:
                    if isinstance(option, dict) and isinstance(option.get("mbid"), str):
                        options_by_mbid.setdefault(option["mbid"], option)
                if options_by_mbid:
                    return ResolvedEntityV1(mention=mention.mention,entity_type=entity_type,resolution_status=EntityResolutionStatus.AMBIGUOUS,confidence=self.AMBIGUOUS_CONFIDENCE_THRESHOLD,reason="Confirm the matching catalog entity before saving this preference.",candidate_options=list(options_by_mbid.values()))
                if not matches and len(mb_options) > 0:
                    return ResolvedEntityV1(mention=mention.mention,entity_type=entity_type,resolution_status=EntityResolutionStatus.AMBIGUOUS,confidence=self.AMBIGUOUS_CONFIDENCE_THRESHOLD,reason="Confirm the MusicBrainz entity before saving this preference.",candidate_options=mb_options)
        if not matches and self.enrichment_service is not None and entity_type != EntityType.UNKNOWN:
            # Production MusicBrainz discovery is read-only. If it returned no
            # candidate, do not silently catalog a new entity before confirmation.
            search_candidates = getattr(type(self.enrichment_service), "search_candidates", None)
            if not callable(search_candidates):
                try:
                    contextual_enrich = getattr(self.enrichment_service, "enrich_with_context", None)
                    if entity_type == EntityType.TRACK and context_artist and callable(contextual_enrich):
                        contextual_enrich(entity_type=entity_type.value, query=mention.mention, context_artist=context_artist)
                    else:
                        self.enrichment_service.enrich(entity_type=entity_type.value, query=mention.mention)
                except (ValueError, LookupError, MusicBrainzClientError):
                    pass
                matches=list(self.catalog.search(mention.mention,entity_type))
                if entity_type == EntityType.TRACK and context_artist:
                    matches=[item for item in matches if self._artist_context_matches(item,context_artist)]
        if not matches:
            return ResolvedEntityV1(
                mention=mention.mention,
                entity_type=entity_type,
                resolution_status=EntityResolutionStatus.UNRESOLVED,
                confidence=0.0,
                reason="No canonical catalog match was found."
            )
        scoped_matches=[
            entity for entity in matches
            if entity.owner_subject_id is None
            or entity.owner_subject_id==subject_id
        ]
        if not scoped_matches:
            return ResolvedEntityV1(
                mention=mention.mention,
                entity_type=entity_type,
                resolution_status=EntityResolutionStatus.REJECTED,
                confidence=0.0,
                reason="Matching entity exists but is outside the authorized subject scope."
            )
        if len(scoped_matches)>1:
            return ResolvedEntityV1(
                mention=mention.mention,
                entity_type=entity_type,
                resolution_status=EntityResolutionStatus.AMBIGUOUS,
                confidence=self.AMBIGUOUS_CONFIDENCE_THRESHOLD,
                reason="Multiple canonical entities match the mention."
            )
        entity=scoped_matches[0]
        normalized_mention=normalize_entity_text(mention.mention)
        normalized_name=normalize_entity_text(entity.canonical_name)
        if normalized_mention==normalized_name:
            return ResolvedEntityV1(
                mention=mention.mention,
                entity_type=entity.entity_type,
                canonical_id=entity.entity_id,
                canonical_name=entity.canonical_name,
                resolution_status=EntityResolutionStatus.RESOLVED,
                confidence=self.EXACT_MATCH_CONFIDENCE,
                matched_field="canonical_name",
                matched_value=entity.canonical_name,
                owner_subject_id=entity.owner_subject_id,
                reason="Exact canonical-name match."
            )
        alias_match=any(
            normalized_mention==normalize_entity_text(alias)
            for alias in entity.aliases
        )
        if alias_match:
            alias_value=next(
                alias for alias in entity.aliases
                if normalized_mention==normalize_entity_text(alias)
            )
            return ResolvedEntityV1(
                mention=mention.mention,
                entity_type=entity.entity_type,
                canonical_id=entity.entity_id,
                canonical_name=entity.canonical_name,
                resolution_status=EntityResolutionStatus.RESOLVED,
                confidence=self.ALIAS_MATCH_CONFIDENCE,
                matched_field="alias",
                matched_value=alias_value,
                owner_subject_id=entity.owner_subject_id,
                reason="Canonical alias match."
            )
        return ResolvedEntityV1(
            mention=mention.mention,
            entity_type=entity.entity_type,
            canonical_id=entity.entity_id,
            canonical_name=entity.canonical_name,
            resolution_status=EntityResolutionStatus.RESOLVED,
            confidence=0.80,
            matched_field="catalog_match",
            matched_value=entity.canonical_name,
            owner_subject_id=entity.owner_subject_id,
            reason="Catalog match resolved with non-exact deterministic evidence."
        )
    @staticmethod
    def _artist_context_matches(entity:CatalogEntityV1, artist_name:str)->bool:
        """Return false only when stored artist-credit metadata contradicts context."""
        credit = entity.metadata.get("artist_credit") if isinstance(entity.metadata, dict) else None
        if not credit:
            # With artist context available, a track without stored artist-credit
            # metadata cannot be verified and must not be treated as a match.
            return False
        expected = normalize_entity_text(artist_name)
        names=[]
        if isinstance(credit, str):
            names=[credit]
        elif isinstance(credit, list):
            for item in credit:
                if isinstance(item, str):
                    names.append(item)
                elif isinstance(item, dict):
                    artist=item.get("artist")
                    names.extend(value for value in (item.get("name"), artist.get("name") if isinstance(artist,dict) else None) if isinstance(value,str))
        return any(normalize_entity_text(name)==expected for name in names)

    @staticmethod
    def _parse_entity_type(value:Optional[str])->EntityType:
        if value is None:
            return EntityType.UNKNOWN
        normalized=value.strip().lower()
        try:
            return EntityType(normalized)
        except ValueError:
            return EntityType.UNKNOWN
    @staticmethod
    def _validate_candidate(candidate:ExtractedMemoryCandidate)->None:
        if not isinstance(candidate,ExtractedMemoryCandidate):
            raise EntityResolutionError(
                EntityResolutionErrorCode.INVALID_CANDIDATE,
                "Input must be an ExtractedMemoryCandidate."
            )
        if not candidate.subject_id.strip():
            raise EntityResolutionError(
                EntityResolutionErrorCode.SUBJECT_MISMATCH,
                "Candidate subject_id is required."
            )
        for mention in candidate.entities:
            if not isinstance(mention,ExtractedEntityMention):
                raise EntityResolutionError(
                    EntityResolutionErrorCode.INVALID_ENTITY_MENTION,
                    "Candidate contains an invalid entity mention."
                )
    @staticmethod
    def _aggregate_status(
        resolved_entities:list[ResolvedEntityV1]
    )->EntityResolutionStatus:
        if not resolved_entities:
            return EntityResolutionStatus.UNRESOLVED
        if any(
            entity.resolution_status==EntityResolutionStatus.REJECTED
            for entity in resolved_entities
        ):
            return EntityResolutionStatus.REJECTED
        if any(
            entity.resolution_status==EntityResolutionStatus.AMBIGUOUS
            for entity in resolved_entities
        ):
            return EntityResolutionStatus.AMBIGUOUS
        if any(
            entity.resolution_status==EntityResolutionStatus.UNRESOLVED
            for entity in resolved_entities
        ):
            return EntityResolutionStatus.UNRESOLVED
        return EntityResolutionStatus.RESOLVED
class EntityResolutionService:
    def __init__(self,resolver:Optional[EntityResolver]=None):
        self.resolver=resolver
    def resolve(
        self,
        candidate:ExtractedMemoryCandidate
    )->EntityResolutionResultV1:
        if self.resolver is None:
            raise EntityResolutionError(
                EntityResolutionErrorCode.INVALID_CANDIDATE,
                "Entity resolver is not configured."
            )
        return self.resolver.resolve_candidate(candidate)
def normalize_entity_text(value:str)->str:
    return " ".join(value.strip().casefold().split())