from enum import Enum
from typing import Optional
from lingua import Language as LinguaLanguage
from lingua import LanguageDetectorBuilder
from pydantic import BaseModel, ConfigDict, Field
class DetectedLanguage(str, Enum):
    ENGLISH = "English"
    HINDI = "Hindi"
    HINGLISH = "Hinglish"
    UNKNOWN = "Unknown"
class LanguageDetectionErrorCode(str, Enum):
    INVALID_TEXT = "INVALID_TEXT"
    INVALID_LOCALE = "INVALID_LOCALE"
    DETECTION_FAILED = "DETECTION_FAILED"
class LanguageDetectionError(Exception):
    def __init__(self, code: LanguageDetectionErrorCode, message: str):
        self.code = code
        self.message = message
        super().__init__(message)
class LanguageDetectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: DetectedLanguage
    confidence: float = Field(ge=0.0, le=1.0)
    method: str = Field(min_length=1, max_length=100)
    locale: Optional[str] = Field(default=None, max_length=32)
class LanguageDetector:
    """
    Detects English, Hindi, and Hinglish from interaction text.
    Detection strategy:
    1. Validate the input.
    2. Detect Hindi script deterministically.
    3. Use Lingua for English/Hindi language detection.
    4. Detect Hinglish when Latin-script text contains sufficient Hindi-derived transliterated signals.
    5. Use locale only as supporting metadata, not as the authoritative language of the text.
    """
    HINGLISH_MARKERS = {
        "mujhe",
        "mujhko",
        "meri",
        "mera",
        "mere",
        "main",
        "mein",
        "mujhse",
        "tum",
        "tumhe",
        "tumko",
        "aap",
        "aapko",
        "apka",
        "apni",
        "apne",
        "hai",
        "hain",
        "ho",
        "tha",
        "thi",
        "the",
        "nahi",
        "nahin",
        "pasand",
        "chahiye",
        "chahta",
        "chahti",
        "karna",
        "karo",
        "karun",
        "rakho",
        "rakhna",
        "yaad",
        "accha",
        "achha",
        "acha",
        "bahut",
        "thoda",
        "zyada",
        "kyun",
        "kyunki",
        "kaise",
        "kya",
        "kab",
        "kahan",
        "abhi",
        "aage",
        "hamesha",
        "suno",
        "sunna",
        "gaana",
        "gaane",
    }
    def __init__(self):
        self._detector = (
            LanguageDetectorBuilder
            .from_languages(
                LinguaLanguage.ENGLISH,
                LinguaLanguage.HINDI,
            )
            .build()
        )
    def detect(self, text: str, locale: Optional[str] = None) -> LanguageDetectionResult:
        self._validate_text(text)
        normalized_text = " ".join(text.strip().split())
        if self._contains_devanagari(normalized_text):
            return LanguageDetectionResult(
                language=DetectedLanguage.HINDI,
                confidence=0.99,
                method="devanagari_script",
                locale=locale,
            )
        hinglish_score = self._hinglish_marker_score(normalized_text)
        if hinglish_score >= 0.20:
            confidence = min(0.98, 0.70 + hinglish_score)
            return LanguageDetectionResult(
                language=DetectedLanguage.HINGLISH,
                confidence=confidence,
                method="hinglish_marker_detection",
                locale=locale,
            )
        try:
            detected = self._detector.detect_language_of(normalized_text)
        except Exception as exc:
            raise LanguageDetectionError(
                LanguageDetectionErrorCode.DETECTION_FAILED,
                f"Language detection failed: {exc}",
            ) from exc
        if detected == LinguaLanguage.ENGLISH:
            confidence = self._language_confidence(normalized_text)
            return LanguageDetectionResult(
                language=DetectedLanguage.ENGLISH,
                confidence=confidence,
                method="lingua",
                locale=locale,
            )
        if detected == LinguaLanguage.HINDI:
            confidence = self._language_confidence(normalized_text)
            return LanguageDetectionResult(
                language=DetectedLanguage.HINDI,
                confidence=confidence,
                method="lingua",
                locale=locale,
            )
        locale_language = self._language_from_locale(locale)
        if locale_language is not None:
            return LanguageDetectionResult(
                language=locale_language,
                confidence=0.60,
                method="locale_fallback",
                locale=locale,
            )
        return LanguageDetectionResult(
            language=DetectedLanguage.UNKNOWN,
            confidence=0.0,
            method="undetermined",
            locale=locale,
        )
    @staticmethod
    def _validate_text(text: str) -> None:
        if not isinstance(text, str):
            raise LanguageDetectionError(
                LanguageDetectionErrorCode.INVALID_TEXT,
                "Text must be a string.",
            )
        if not text.strip():
            raise LanguageDetectionError(
                LanguageDetectionErrorCode.INVALID_TEXT,
                "Text cannot be empty.",
            )
    @staticmethod
    def _contains_devanagari(text: str) -> bool:
        return any("\u0900" <= character <= "\u097F" for character in text)
    @classmethod
    def _hinglish_marker_score(cls, text: str) -> float:
        words = {
            word.strip(".,!?;:'\"()[]{}").casefold()
            for word in text.split()
        }
        if not words:
            return 0.0
        matches = words.intersection(cls.HINGLISH_MARKERS)
        return len(matches) / len(words)
    def _language_confidence(self, text: str) -> float:
        confidence_values = self._detector.compute_language_confidence_values(text)
        for value in confidence_values:
            if value.language == LinguaLanguage.ENGLISH:
                return min(0.99, max(0.50, float(value.value)))
            if value.language == LinguaLanguage.HINDI:
                return min(0.99, max(0.50, float(value.value)))
        return 0.50
    @staticmethod
    def _language_from_locale(locale: Optional[str]) -> Optional[DetectedLanguage]:
        if not locale:
            return None
        normalized = locale.strip().casefold()
        if normalized.startswith("en"):
            return DetectedLanguage.ENGLISH
        if normalized.startswith("hi"):
            return DetectedLanguage.HINDI
        return None