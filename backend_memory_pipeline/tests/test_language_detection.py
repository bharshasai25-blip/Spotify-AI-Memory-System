from backend_memory_pipeline.language_detection.language_detection import DetectedLanguage,LanguageDetector
def test_language_detection():
    detector=LanguageDetector()
    english_result=detector.detect("I prefer calm acoustic music","en-IN")
    hindi_result=detector.detect("मुझे शांत संगीत पसंद है","hi-IN")
    hinglish_result=detector.detect("Mujhe calm acoustic music pasand hai","en-IN")
    print(english_result)
    print(hindi_result)
    print(hinglish_result)
    assert english_result.language==DetectedLanguage.ENGLISH
    assert hindi_result.language==DetectedLanguage.HINDI
    assert hinglish_result.language==DetectedLanguage.HINGLISH