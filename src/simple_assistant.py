"""Simple scheme assistant.

Goal: reliable, short responses in the selected language.
- Text input: pass through.
- Voice input: STT -> text -> pass through.
- If a scheme is mentioned: look up locally and return benefits + how-to-apply.
- Otherwise: suggest a few relevant schemes and ask at most one short question.

This intentionally avoids the multi-agent planner/executor loop for stability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple, List
import re
import difflib
import unicodedata

from .tools.retrieval import SchemeRetriever, ApplicationHelper


# Deterministic translations for the small local dataset (10 schemes).
TA_DOCS: Dict[str, str] = {
    "आधार कार्ड": "ஆதார் அட்டை",
    "आधार कार्ड किंवा मतदार ओळखपत्र": "ஆதார் அட்டை அல்லது வாக்காளர் அடையாள அட்டை",
    "उत्पन्न प्रमाणपत्र": "வருமானச் சான்றிதழ்",
    "रहिवास प्रमाणपत्र": "வசிப்புச் சான்றிதழ்",
    "वय प्रमाणपत्र": "வயது சான்றிதழ்",
    "जात प्रमाणपत्र": "சாதி சான்றிதழ்",
    "पतीचा मृत्यू प्रमाणपत्र": "கணவரின் இறப்பு சான்றிதழ்",
    "पासपोर्ट आकाराचा फोटो": "பாஸ்போர்ட் அளவு புகைப்படம்",
    "पिवळे/केशरी रेशन कार्ड": "மஞ்சள்/ஆரஞ்சு ரேஷன் அட்டை",
    "बँक खाते": "வங்கி கணக்கு விவரம்",
    "बँक पासबुक": "வங்கி பாஸ்புக்",
    "जमीन मालकी कागदपत्रे": "நில உரிமை ஆவணங்கள்",
    "शाळा/कॉलेज प्रमाणपत्र": "பள்ளி/கல்லூரி சான்றிதழ்",
    "अपंगत्व प्रमाणपत्र (40% पेक्षा जास्त)": "மாற்றுத்திறனாளி சான்றிதழ் (40% மேல்)",
}

TA_STEPS: Dict[str, str] = {
    "नजीकच्या CSC केंद्रात जा": "அருகிலுள்ள சி.எஸ்.சி மையத்திற்கு செல்லுங்கள்",
    "ऑनलाइन नोंदणी करा": "ஆன்லைனில் பதிவு செய்யுங்கள்",
    "कागदपत्रे सादर करा": "தேவையான ஆவணங்களை சமர்ப்பிக்கவும்",
    "ग्रामपंचायत/नगरपालिकेत अर्ज करा": "கிராம பஞ்சாயத்து/நகராட்சியில் விண்ணப்பிக்கவும்",
    "ऑनलाइन अर्ज करता येतो": "ஆன்லைனில் விண்ணப்பிக்கலாம்",
    "ग्रामसेवक/नगरपालिकेत अर्ज करा": "கிராம சேவகர்/நகராட்சியில் விண்ணப்பிக்கவும்",
    "तहसील कार्यालयात अर्ज करा": "தாசில்தார் அலுவலகத்தில் விண்ணப்பிக்கவும்",
    "नजीकच्या सरकारी रुग्णालयात संपर्क करा": "அருகிலுள்ள அரசு மருத்துவமனையை தொடர்புகொள்ளுங்கள்",
    "कोणत्याही बँकेत जा": "எந்தவொரு வங்கிக்கும் செல்லுங்கள்",
    "बँकेत अर्ज करा": "வங்கியில் விண்ணப்பிக்கவும்",
    "अर्ज भरा आणि खाते उघडा": "விண்ணப்பத்தை நிரப்பி கணக்கு திறக்கவும்",
    "शून्य बॅलन्स खाते": "பூஜ்ஜியம் இருப்புத் தொகை கணக்கு",
    "ऑटो-डेबिट मंजूर करा": "ஆட்டோ-டெபிட் அனுமதியை வழங்குங்கள்",
    "ऑनलाइन पोर्टलवर नोंदणी करा": "ஆன்லைன் போர்டலில் பதிவு செய்யுங்கள்",
    "महाDBT पोर्टलवर ऑनलाइन अर्ज करा": "மஹா டிபிடி போர்டலில் ஆன்லைனில் விண்ணப்பிக்கவும்",
    "सेतू केंद्रात अर्ज करा": "சேது மையத்தில் விண்ணப்பிக்கவும்",
}

TA_BENEFITS: Dict[str, str] = {
    "वार्षिक ₹6000 (3 हप्त्यांमध्ये)": "ஆண்டுக்கு ₹6000 (3 தவணைகளில்)",
    "थेट बँक खात्यात जमा": "நேரடியாக வங்கி கணக்கில் செலுத்தப்படும்",
    "थेट बँक खात्यात": "நேரடியாக வங்கி கணக்கில்",
    "₹2.5 लाखांपर्यंत अनुदान": "₹2.5 லட்சம் வரை மானியம்",
    "कमी व्याजदराने कर्ज": "குறைந்த வட்டி கடன்",
    "मासिक ₹1000 पेन्शन": "மாதம் ₹1000 ஓய்வூதியம்",
    "मासिक ₹1000-1500 पेन्शन": "மாதம் ₹1000-₹1500 ஓய்வூதியம்",
    "मासिक ₹1000-2000 पेन्शन": "மாதம் ₹1000-₹2000 ஓய்வூதியம்",
    "मासिक भत्ता": "மாதாந்திர உதவித்தொகை",
    "मासिक ₹1500 आर्थिक सहाय्य": "மாதம் ₹1500 நிதி உதவி",
    "₹1.5 लाखांपर्यंत मोफत उपचार": "₹1.5 லட்சம் வரை இலவச சிகிச்சை",
    "971 रोगांचा समावेश": "971 நோய்கள் உட்பட",
    "फक्त ₹12 वार्षिक प्रीमियम": "ஆண்டுக்கு ₹12 மட்டுமே பிரீமியம்",
    "₹2 लाख अपघात विमा": "₹2 லட்சம் விபத்து காப்பீடு",
    "RuPay डेबिट कार्ड": "ரூபே டெபிட் கார்டு",
    "शिक्षण शुल्क माफी": "கல்வி கட்டணம் தள்ளுபடி/மன்னிப்பு",
    "वैद्यकीय सहाय्य": "மருத்துவ உதவி",
    "शून्य बॅलन्स खाते": "பூஜ்ஜியம் இருப்புத் தொகை கணக்கு",
}


TA_SCHEME_NAMES: Dict[str, str] = {
    "pmksy": "பிரதான் மந்திரி கிசான் சம்மான் நிதி",
    "pmay": "பிரதான் மந்திரி ஆவாஸ் யோஜனா",
    "sby": "மகாத்மா ஜ்யோதிராவ் புலே ஜன ஆரோக்கிய யோஜனா",
    "widow_pension": "விதவை ஓய்வூதிய திட்டம்",
    "disability_pension": "மாற்றுத்திறனாளி ஓய்வூதிய திட்டம்",
    "pmjdy": "பிரதான் மந்திரி ஜன்தன் யோஜனா",
    "pmsby": "பிரதான் மந்திரி சுரக்ஷா பீமா யோஜனா",
    "scholarship_sc": "எஸ்.சி. உதவித்தொகை திட்டம்",
    "ladki_bahin": "முக்யமந்திரி மாஜி லாட்கி பஹின் யோஜனா",
    "old_age_pension": "மூத்த குடிமக்கள் ஓய்வூதிய திட்டம்",
}


def _scheme_display_name(scheme: Dict[str, Any], lang: str) -> str:
    sid = str(scheme.get("id") or "").strip()
    name_en = str(scheme.get("name_en") or scheme.get("name") or "Scheme").strip()
    if lang == "tamil" and sid in TA_SCHEME_NAMES:
        return TA_SCHEME_NAMES[sid]
    return name_en


def _ta_query_canonicalize(text: str) -> str:
    """Lightweight normalization for common Tamil STT/typo variants.

    This is intentionally small and deterministic (no external deps).
    """
    t = _norm(text)
    if not t:
        return t

    # Common spelling variants seen in speech-to-text.
    # "யோஜணா" is a frequent Tamil spelling variant of "யோஜனா".
    t = t.replace("யோஜணா", "யோஜனா")

    # "ஆவாச்" (ச) vs "ஆவாஸ்" (ஸ) for the housing scheme.
    # Normalize a few close variants into the canonical form used in TA_SCHEME_NAMES.
    t = re.sub(r"ஆவாச்?", "ஆவாஸ்", t)
    t = re.sub(r"ஆவாஸ", "ஆவாஸ்", t)

    # Minor variants for kisan phrase.
    t = re.sub(r"கிசன", "கிசான்", t)
    t = re.sub(r"சமான்", "சம்மான்", t)

    t = re.sub(r"\s+", " ", t).strip()
    return t


EN_DOCS: Dict[str, str] = {
    "आधार कार्ड": "Aadhaar card",
    "आधार कार्ड किंवा मतदार ओळखपत्र": "Aadhaar card or Voter ID",
    "उत्पन्न प्रमाणपत्र": "Income certificate",
    "रहिवास प्रमाणपत्र": "Residence certificate",
    "वय प्रमाणपत्र": "Age proof",
    "जात प्रमाणपत्र": "Caste certificate",
    "पतीचा मृत्यू प्रमाणपत्र": "Husband's death certificate",
    "पासपोर्ट आकाराचा फोटो": "Passport size photo",
    "पिवळे/केशरी रेशन कार्ड": "Yellow/Orange ration card",
    "बँक खाते": "Bank account details",
    "बँक पासबुक": "Bank passbook",
    "जमीन मालकी कागदपत्रे": "Land ownership documents",
    "शाळा/कॉलेज प्रमाणपत्र": "School/College certificate",
    "अपंगत्व प्रमाणपत्र (40% पेक्षा जास्त)": "Disability certificate (40%+)",
}

EN_STEPS: Dict[str, str] = {
    "नजीकच्या CSC केंद्रात जा": "Go to the nearest CSC center",
    "ऑनलाइन नोंदणी करा": "Register online",
    "कागदपत्रे सादर करा": "Submit the required documents",
    "ग्रामपंचायत/नगरपालिकेत अर्ज करा": "Apply at the Gram Panchayat/Municipality",
    "ऑनलाइन अर्ज करता येतो": "You can apply online",
    "ग्रामसेवक/नगरपालिकेत अर्ज करा": "Apply at the Gram Sevak/Municipality",
    "तहसील कार्यालयात अर्ज करा": "Apply at the Tehsil office",
    "नजीकच्या सरकारी रुग्णालयात संपर्क करा": "Contact the nearest government hospital",
    "कोणत्याही बँकेत जा": "Go to any bank",
    "बँकेत अर्ज करा": "Apply at the bank",
    "अर्ज भरा आणि खाते उघडा": "Fill the form and open the account",
    "ऑटो-डेबिट मंजूर करा": "Enable auto-debit",
    "ऑनलाइन पोर्टलवर नोंदणी करा": "Register on the online portal",
    "महाDBT पोर्टलवर ऑनलाइन अर्ज करा": "Apply online on the MahaDBT portal",
    "सेतू केंद्रात अर्ज करा": "Apply at the Setu center",
}

EN_BENEFITS: Dict[str, str] = {
    "वार्षिक ₹6000 (3 हप्त्यांमध्ये)": "₹6000 per year (in 3 installments)",
    "थेट बँक खात्यात जमा": "Directly credited to bank account",
    "थेट बँक खात्यात": "Direct bank transfer",
    "₹2.5 लाखांपर्यंत अनुदान": "Grant up to ₹2.5 lakh",
    "कमी व्याजदराने कर्ज": "Loan at lower interest",
    "मासिक ₹1000 पेन्शन": "₹1000 monthly pension",
    "मासिक ₹1000-1500 पेन्शन": "₹1000-₹1500 monthly pension",
    "मासिक ₹1000-2000 पेन्शन": "₹1000-₹2000 monthly pension",
    "मासिक भत्ता": "Monthly allowance",
    "मासिक ₹1500 आर्थिक सहाय्य": "₹1500 monthly financial assistance",
    "₹1.5 लाखांपर्यंत मोफत उपचार": "Free treatment up to ₹1.5 lakh",
    "971 रोगांचा समावेश": "Covers 971 diseases",
    "फक्त ₹12 वार्षिक प्रीमियम": "Only ₹12 annual premium",
    "₹2 लाख अपघात विमा": "₹2 lakh accident insurance",
    "RuPay डेबिट कार्ड": "RuPay debit card",
    "शिक्षण शुल्क माफी": "Education fee waiver",
    "वैद्यकीय सहाय्य": "Medical assistance",
    "शून्य बॅलन्स खाते": "Zero-balance account",
}


def _tr(item: str, lang: str, kind: str) -> str:
    item = (item or "").strip()
    if not item:
        return ""
    if lang == "tamil":
        if kind == "doc":
            return TA_DOCS.get(item, "")
        if kind == "step":
            return TA_STEPS.get(item, "")
        if kind == "benefit":
            return TA_BENEFITS.get(item, "")
    if lang == "english":
        if kind == "doc":
            return EN_DOCS.get(item, "")
        if kind == "step":
            return EN_STEPS.get(item, "")
        if kind == "benefit":
            return EN_BENEFITS.get(item, "")
    return ""


_SUPPORTED_LANGS = {
    "tamil",
    "english",
}


def _contains_tamil(text: str) -> bool:
    return any("\u0b80" <= ch <= "\u0bff" for ch in text)


def _contains_devanagari(text: str) -> bool:
    return any("\u0900" <= ch <= "\u097f" for ch in text)


def _strict_language_ok(text: str, language: str) -> bool:
    if not text.strip():
        return False
    if language == "tamil":
        # Allow Latin/ASCII for URLs/scheme codes, but disallow Devanagari.
        return not _contains_devanagari(text)
    if language == "english":
        # Disallow Tamil when English is selected.
        return not _contains_tamil(text)
    return True


def _norm(text: str) -> str:
    """Normalize text for matching.

    Important: preserve Indic combining marks (Tamil virama/vowel signs),
    otherwise Tamil tokens like "ஆம்"/"இல்லை" get corrupted.
    """
    t = (text or "").strip().lower()
    t = re.sub(r"\s+", " ", t)

    kept: List[str] = []
    for ch in t:
        if ch.isspace() or ch in "-()":
            kept.append(ch)
            continue
        cat = unicodedata.category(ch)
        # Letters/Marks/Numbers only (drops punctuation/symbols).
        if cat and cat[0] in {"L", "M", "N"}:
            kept.append(ch)
            continue
        # Drop everything else

    t = "".join(kept)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _is_greeting(text: str) -> bool:
    t = _norm(text)
    return t in {"hi", "hello", "hey", "hai", "vanakkam", "வணக்கம்", "namaste", "नमस्ते"}


def _is_thanks(text: str) -> bool:
    t = _norm(text)
    # Keep this Tamil-first; allow a few common phonetic spellings from STT.
    return t in {
        "நன்றி",
        "நன்ரி",
        "நன்றி.",
        "நன்றிங்க",
        "நன்றீ",
        "நன்ற",
    }


def _pick_category(text: str) -> Optional[str]:
    raw = (text or "").strip().lower()
    t = _norm(text)
    # Minimal multilingual keyword mapping.
    mapping = {
        "housing": ["housing", "house", "home", "pmay", "ஆவாஸ்", "ஆவாஸ", "आवास", "घर", "வீடு", "வீட்ட", "வீட்டு"],
        "agriculture": ["farm", "farmer", "agriculture", "kisan", "pm kisan", "किसान", "शेतकरी", "விவசாய", "விவசாயி", "விவசாயம்"],
        "health": ["health", "hospital", "medical", "आरोग्य", "चिकित्सा", "மருத்துவ", "மருத்துவமனை", "சுகாத"],
        "education": ["education", "school", "college", "scholar", "शिक्ष", "கல்வி", "பள்ளி", "கல்லூரி"],
        "pension": ["pension", "old age", "पेन्शन", "पेंशन", "ஓய்வூதியம்"],
        "women_welfare": ["women", "mahila", "महिला", "பெண", "மகளிர"],
        "financial": ["loan", "bank", "finance", "आर्थिक", "கடன்", "வங்கி"],
        "insurance": ["insurance", "विमा", "காப்பீடு"],
    }
    for cat, kws in mapping.items():
        if any(kw in t for kw in kws) or any(kw in raw for kw in kws):
            return cat
    return None


def _looks_like_scheme_query(text: str) -> bool:
    t = _norm(text)
    # Short scheme-like inputs ("pm kisan", "pmay", etc.)
    if len(t.split()) <= 4 and any(x in t for x in ["pm", "yojana", "scheme", "kisan", "pmay", "pension"]):
        return True
    # Tamil equivalents
    if "திட்ட" in text or "யோஜ" in t:
        return True
    return False


def _rewrite_phonetic_acronyms(text: str) -> str:
    """Fix common STT outputs where English acronyms are transcribed as Tamil letter names.

    Example: "PMAY" may come back as "பி யம ய வை" (or similar). We rewrite these
    to the English scheme codes so the local lookup can match reliably, while the
    assistant still responds in the selected output language (Tamil/English).
    """
    raw = (text or "").strip()
    if not raw:
        return raw

    # Work on a normalized view for robust matching, but apply replacements to the
    # normalized view (not the raw) since we only use it for lookup.
    t = _norm(raw)

    # Some environments (or STT quirks) may drop Tamil vowel/virama marks.
    # Match both marked and unmarked variants.
    p_tok = r"ப(?:ி|ீ)?"  # P
    m_tok = r"(?:எ(?:ம்|ம)?|ய(?:ம்|ம)?)"  # M (எம்/எம/யம்/யம)
    # Whisper sometimes mis-hears the letter 'A' as Tamil 'ய' in this context.
    a_tok = r"(?:ஏ|எ|அ|ஆ|ய)"  # A
    y_tok = r"(?:வ(?:ை)?|ய்|ஐ)"  # Y

    # PMAY (Pradhan Mantri Awas Yojana)
    pmay_patterns = [
        rf"(?:^|\s){p_tok}\s+{m_tok}\s+{a_tok}\s+{y_tok}(?:\s|$)",
        rf"(?:^|\s){p_tok}{m_tok}{a_tok}{y_tok}(?:\s|$)",
    ]
    for pat in pmay_patterns:
        if re.search(pat, t):
            t = re.sub(pat, " pmay ", t)

    # PM-KISAN (kisan may also lose marks: கிசான் -> கசன)
    kisan_tok = r"க(?:ி)?ச(?:ா)?ன(?:்)?"
    pmkisan_patterns = [
        rf"(?:^|\s){p_tok}\s+{m_tok}\s+{kisan_tok}(?:\s|$)",
        rf"(?:^|\s){p_tok}{m_tok}\s*{kisan_tok}(?:\s|$)",
        rf"(?:^|\s){p_tok}{m_tok}\s*{kisan_tok}\s*(?:திட்டம்|யோஜனா|யோஜன)(?:\s|$)",
    ]
    for pat in pmkisan_patterns:
        if re.search(pat, t):
            t = re.sub(pat, " pm kisan ", t)

    # English letter spelling variants that Whisper may output.
    # "P-M-E-Y", "P M E Y", "PMEY" should be treated as "pmay" for matching.
    if re.search(r"(?:^|\s)p\s*[- ]?\s*m\s*[- ]?\s*(?:a|e)\s*[- ]?\s*y(?:\s|$)", t):
        t = re.sub(r"(?:^|\s)p\s*[- ]?\s*m\s*[- ]?\s*(?:a|e)\s*[- ]?\s*y(?:\s|$)", " pmay ", t)
    if re.search(r"(?:^|\s)pm(?:a|e)y(?:\s|$)", t):
        t = re.sub(r"(?:^|\s)pm(?:a|e)y(?:\s|$)", " pmay ", t)

    # PM-KISAN letter spelling
    if re.search(r"(?:^|\s)p\s*[- ]?\s*m\s*[- ]?\s*k\s*[- ]?\s*i\s*[- ]?\s*s\s*[- ]?\s*a\s*[- ]?\s*n(?:\s|$)", t):
        t = re.sub(r"(?:^|\s)p\s*[- ]?\s*m\s*[- ]?\s*k\s*[- ]?\s*i\s*[- ]?\s*s\s*[- ]?\s*a\s*[- ]?\s*n(?:\s|$)", " pm kisan ", t)
    if re.search(r"(?:^|\s)pmkisan(?:\s|$)", t):
        t = re.sub(r"(?:^|\s)pmkisan(?:\s|$)", " pm kisan ", t)

    # Compact whitespace
    t = re.sub(r"\s+", " ", t).strip()
    return t or raw


@dataclass
class AssistantSession:
    language: str = "tamil"
    last_suggestions: List[Dict[str, Any]] = field(default_factory=list)

    # Requirement checklist flow
    active_scheme: Optional[Dict[str, Any]] = None
    requirement_items: List[str] = field(default_factory=list)
    requirement_index: int = 0
    requirement_answers: Dict[str, bool] = field(default_factory=dict)


class SimpleSchemeAssistant:
    def __init__(self, llm_client: Any, language: str = "tamil"):
        self.llm_client = llm_client
        self.session = AssistantSession(language=language)
        self.retriever = SchemeRetriever(vector_store=None)
        self.application_helper = ApplicationHelper()

    def set_language(self, language: str):
        self.session.language = language if language in _SUPPORTED_LANGS else "english"

    def _reset_requirements_flow(self):
        self.session.active_scheme = None
        self.session.requirement_items = []
        self.session.requirement_index = 0
        self.session.requirement_answers = {}

    def _parse_yes_no(self, text: str) -> Optional[bool]:
        t = _norm(text)
        # Accept both languages for robustness.
        yes = {
            "yes", "y", "yeah", "yep", "ok", "okay", "sure",
            # Tamil yes + common STT variants
            "ஆம்", "ஆம", "ஆமா", "ஆமாம்",
            "அம்", "அம்ம", "அம்ம்",
            "ம்", "ம்ம", "ம்ம்",
            # Whisper occasionally mishears "ஆம்" as "ஓம்"
            "ஓம்",
            "உண்டு", "இருக்கு",
        }
        no = {
            "no", "n", "nope", "not",
            "இல்லை", "இலல", "இல்ல", "இல்லங்க", "இல்லா",
            "இல்லே", "இல்லப்பா", "இல்லங்கா",
        }
        if any(word == t for word in yes) or any(f" {word} " in f" {t} " for word in yes):
            return True
        if any(word == t for word in no) or any(f" {word} " in f" {t} " for word in no):
            return False

        # Conservative fuzzy matching for small spelling mistakes.
        # Only apply to short, single-phrase answers to avoid false positives.
        if t and len(t) <= 6:
            yes_targets = ["ஆம்", "ஆமா", "ஆமாம்", "ஓம்", "அம்"]
            no_targets = ["இல்லை", "இல்ல", "இல்லே"]
            best_yes = max((difflib.SequenceMatcher(None, t, y).ratio() for y in yes_targets), default=0.0)
            best_no = max((difflib.SequenceMatcher(None, t, n).ratio() for n in no_targets), default=0.0)
            if best_yes >= 0.72 and best_yes >= best_no + 0.08:
                return True
            if best_no >= 0.72 and best_no >= best_yes + 0.08:
                return False
        return None

    async def _ask_next_requirement_question(self) -> str:
        if not self.session.active_scheme:
            return self._msg("not_found", raw=True)

        idx = self.session.requirement_index
        items = self.session.requirement_items
        if idx >= len(items):
            return self._format_apply_steps_after_requirements(self.session.active_scheme)

        req = items[idx]
        lang = self.session.language
        if lang == "tamil":
            return f"ஆவணம் சரிபார்ப்பு ({idx+1}/{len(items)}): உங்களிடம் '{req}' உள்ளதா? ஆம் அல்லது இல்லை"
        return f"Requirement check ({idx+1}/{len(items)}): Do you have '{req}'? Yes / No"

    async def handle_text(self, text: str) -> str:
        if not text or not text.strip():
            return self._msg("empty")

        # If the user says thanks, end politely.
        if self.session.language == "tamil" and _is_thanks(text):
            self._reset_requirements_flow()
            return "வணக்கம்"

        # Tamil-only input guardrail (backstop).
        # If the user input is clearly not Tamil, ask them to speak in Tamil.
        if self.session.language == "tamil":
            rewritten_check = _rewrite_phonetic_acronyms(text)
            lowered = (rewritten_check or "").lower()
            has_latin = bool(re.search(r"[a-z]", lowered))
            if _contains_devanagari(rewritten_check) or (has_latin and ("pmay" not in lowered) and ("pm kisan" not in lowered) and ("pmkisan" not in lowered)):
                return (
                    "தமிழில் மட்டும் பேசுங்கள். "
                    "உதாரணம்: 'பிரதான் மந்திரி ஆவாஸ் யோஜனா' அல்லது 'பிரதான் மந்திரி கிசான் சம்மான் நிதி'."
                )

        if _is_greeting(text):
            return self._msg("greet")

        # If we are in the requirements checklist flow, only accept yes/no and proceed.
        if self.session.active_scheme and self.session.requirement_items:
            if self.session.language == "tamil" and _is_thanks(text):
                self._reset_requirements_flow()
                return "வணக்கம்"

            yn = self._parse_yes_no(text)
            if yn is None:
                return "'ஆம்' அல்லது 'இல்லை' என்று மட்டும் பதிலளிக்கவும்." if self.session.language == "tamil" else "Please reply with Yes or No."

            idx = self.session.requirement_index
            if 0 <= idx < len(self.session.requirement_items):
                key = self.session.requirement_items[idx]
                self.session.requirement_answers[key] = yn
                self.session.requirement_index += 1

            # Ask next question or move to apply steps
            if self.session.requirement_index < len(self.session.requirement_items):
                return await self._ask_next_requirement_question()

            # Finished requirements → provide apply steps
            base = self._format_apply_steps_after_requirements(self.session.active_scheme)
            self._reset_requirements_flow()
            return base

        # Whisper may output English acronyms as Tamil letter names (e.g., PMAY).
        # Rewrite those to English scheme codes for reliable lookup.
        lookup_text = _rewrite_phonetic_acronyms(text)

        scheme = await self._lookup_scheme(lookup_text)
        if scheme is not None:
            enriched = await self._enrich_scheme(scheme)

            # Start requirement checklist before showing apply steps.
            documents_raw = list(enriched.get("documents_required") or [])
            documents_raw = [str(d) for d in documents_raw if str(d).strip()]
            documents = []
            for d in documents_raw:
                td = _tr(d, self.session.language, "doc")
                if td:
                    documents.append(td)

            self.session.active_scheme = enriched
            self.session.requirement_items = documents
            self.session.requirement_index = 0
            self.session.requirement_answers = {}

            # Short intro + first requirement question (if any docs exist).
            intro = self._format_scheme_intro(enriched)
            if self.session.requirement_items:
                q = await self._ask_next_requirement_question()
                return intro + "\n\n" + q

            # If no documents listed, fall back to showing apply steps directly.
            base = self._format_apply_steps_after_requirements(enriched)
            self._reset_requirements_flow()
            return base

        # Not a direct scheme match → retrieve suggestions
        category = _pick_category(lookup_text)
        query = lookup_text
        results = await self.retriever.execute(query=query, category=category, limit=5)
        schemes = results.get("schemes", []) if isinstance(results, dict) else []

        self.session.last_suggestions = schemes[:5]

        if schemes:
            base = self._format_suggestions(schemes[:3], category=category)
            return base

        # If we detected a category but retrieval failed (Tamil queries may not keyword-match),
        # suggest from the local dataset directly.
        if category:
            if not self.retriever._schemes_loaded:  # type: ignore[attr-defined]
                self.retriever._load_schemes()  # type: ignore[attr-defined]
            all_schemes: List[Dict[str, Any]] = list(getattr(self.retriever, "_schemes_cache", []) or [])
            cat_schemes = [s for s in all_schemes if s.get("category") == category]
            if cat_schemes:
                base = self._format_suggestions(cat_schemes[:3], category=category)
                return base

        # Nothing found
        return self._msg("not_found", raw=True)

    async def _lookup_scheme(self, text: str) -> Optional[Dict[str, Any]]:
        q = _norm(text)
        if not q:
            return None

        # Load scheme cache
        if not self.retriever._schemes_loaded:  # type: ignore[attr-defined]
            self.retriever._load_schemes()  # type: ignore[attr-defined]

        schemes: List[Dict[str, Any]] = list(getattr(self.retriever, "_schemes_cache", []) or [])
        if not schemes:
            return None

        # Tamil-first matching: the local dataset names are Marathi/English,
        # so we match Tamil user inputs against TA_SCHEME_NAMES and map back to scheme ids.
        if self.session.language == "tamil":
            q_ta = _ta_query_canonicalize(text)
            if q_ta:
                schemes_by_id = {str(s.get("id") or "").strip(): s for s in schemes}

                # Strong substring check against canonical Tamil names.
                for sid, ta_name in TA_SCHEME_NAMES.items():
                    target = _norm(ta_name)
                    if not target:
                        continue
                    if q_ta in target or target in q_ta:
                        picked = schemes_by_id.get(sid)
                        if picked is not None:
                            return picked

                # Fuzzy match against canonical Tamil names.
                ta_candidates: List[Tuple[float, str]] = []
                for sid, ta_name in TA_SCHEME_NAMES.items():
                    target = _norm(ta_name)
                    if not target:
                        continue
                    ratio = difflib.SequenceMatcher(None, q_ta, target).ratio()
                    ta_candidates.append((ratio, sid))

                ta_candidates.sort(key=lambda x: x[0], reverse=True)
                if ta_candidates and ta_candidates[0][0] >= 0.62:
                    best_sid = ta_candidates[0][1]
                    picked = schemes_by_id.get(best_sid)
                    if picked is not None:
                        return picked

        # Try strong substring matches on common name fields
        for s in schemes:
            name = _norm(str(s.get("name", "")))
            name_en = _norm(str(s.get("name_en", "")))
            sid = _norm(str(s.get("id", "")))
            # If the user's query appears inside any identifier/name, treat as a match.
            if name and q in name:
                return s
            if name_en and q in name_en:
                return s
            if sid and q in sid:
                return s

        # If the input looks like a scheme query, do a fuzzy match
        if not _looks_like_scheme_query(text):
            return None

        candidates: List[Tuple[float, Dict[str, Any]]] = []
        for s in schemes:
            hay = " ".join([
                _norm(str(s.get("name", ""))),
                _norm(str(s.get("name_en", ""))),
                _norm(str(s.get("id", ""))),
            ]).strip()
            if not hay:
                continue
            ratio = difflib.SequenceMatcher(None, q, hay).ratio()
            candidates.append((ratio, s))

        candidates.sort(key=lambda x: x[0], reverse=True)
        if candidates and candidates[0][0] >= 0.45:
            return candidates[0][1]

        return None

    async def _enrich_scheme(self, scheme: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure we have docs/process/website even if retriever record is sparse."""
        scheme_id = scheme.get("id")
        if not scheme_id:
            return scheme

        enriched = dict(scheme)

        try:
            if not enriched.get("documents_required"):
                docs = await self.application_helper.execute(scheme_id=scheme_id, action="get_documents")
                if isinstance(docs, dict) and docs.get("documents"):
                    enriched["documents_required"] = docs.get("documents")
                if isinstance(docs, dict) and docs.get("website") and not enriched.get("website"):
                    enriched["website"] = docs.get("website")

            if not enriched.get("application_process"):
                proc = await self.application_helper.execute(scheme_id=scheme_id, action="get_process")
                if isinstance(proc, dict) and proc.get("process"):
                    enriched["application_process"] = proc.get("process")
                if isinstance(proc, dict) and proc.get("website") and not enriched.get("website"):
                    enriched["website"] = proc.get("website")
        except Exception:
            return enriched

        return enriched

    def _format_suggestions(self, schemes: List[Dict[str, Any]], category: Optional[str]) -> str:
        lang = self.session.language
        lines: List[str] = []
        lines.append("தொடர்புடைய திட்டங்கள்:" if lang == "tamil" else "Relevant schemes I found:")
        for s in schemes:
            name = _scheme_display_name(s, lang)
            lines.append(f"- {name}")

        # Ask exactly one short question
        if category:
            lines.append(
                "\nஒரு திட்டத்தின் பெயரை பேசிச் சொல்லுங்கள்; அதன் விவரம் + ஆவண சரிபார்ப்பு + விண்ணப்பிப்பு படிகள் தருகிறேன்."
                if lang == "tamil"
                else "\nSay the scheme name to get details + requirements check + apply steps."
            )
        else:
            lines.append(
                "\nஎந்த வகை திட்டம் வேண்டும்? வீடு / விவசாயம் / சுகாதாரம் / கல்வி / ஓய்வூதியம்"
                if lang == "tamil"
                else "\nWhich category do you need? housing / agriculture / health / education / pension"
            )
        return "\n".join(lines)

    def _format_scheme_intro(self, scheme: Dict[str, Any]) -> str:
        """Intro shown immediately after scheme detection (NO apply steps yet)."""
        lang = self.session.language
        name = _scheme_display_name(scheme, lang)
        benefits_raw = scheme.get("benefits") or []
        website = scheme.get("website")

        lines: List[str] = []
        lines.append(f"திட்டம்: {name}" if lang == "tamil" else f"Scheme: {name}")

        benefits = []
        for b in benefits_raw:
            tb = _tr(str(b), lang, "benefit")
            if tb:
                benefits.append(tb)

        if benefits:
            lines.append("\nபயன்கள்:" if lang == "tamil" else "\nBenefits:")
            for b in benefits[:2]:
                lines.append(f"- {b}")
        if website:
            lines.append(f"\nஅதிகாரப்பூர்வ இணையதளம்: {website}" if lang == "tamil" else f"\nOfficial site: {website}")
        lines.append(
            "\nதேவையான ஆவணங்களை பற்றி சில ஆம்/இல்லை கேள்விகள் கேட்கிறேன். பின்னர் விண்ணப்பிக்கும் படிகள் தருகிறேன்."
            if lang == "tamil"
            else "\nI will ask a few Yes/No questions about required documents. After that, I will give the steps to apply."
        )
        return "\n".join(lines)

    def _format_apply_steps_after_requirements(self, scheme: Dict[str, Any]) -> str:
        lang = self.session.language
        name = _scheme_display_name(scheme, lang)
        process_raw = scheme.get("application_process") or []
        website = scheme.get("website")

        missing = [k for k, v in (self.session.requirement_answers or {}).items() if v is False]

        lines: List[str] = []
        lines.append(f"திட்டம்: {name}" if lang == "tamil" else f"Scheme: {name}")

        if missing:
            lines.append("\nஇல்லை என்று கூறிய ஆவணங்கள்:" if lang == "tamil" else "\nDocuments missing (you answered No):")
            for m in missing[:6]:
                lines.append(f"- {m}")
            lines.append("\nவிண்ணப்பிக்கும் முன் இவ்வாவணங்களை தயார் செய்யுங்கள்." if lang == "tamil" else "\nPlease arrange these documents before applying.")

        process = []
        for st in process_raw:
            ts = _tr(str(st), lang, "step")
            if ts:
                process.append(ts)

        if process:
            lines.append("\nவிண்ணப்பிக்கும் முறை:" if lang == "tamil" else "\nHow to apply:")
            for step in process[:6]:
                lines.append(f"- {step}")
        else:
            lines.append("\nவிண்ணப்பிக்கும் முறை:" if lang == "tamil" else "\nHow to apply:")
            lines.append("- அதிகாரப்பூர்வ இணையதளம் அல்லது அருகிலுள்ள சி.எஸ்.சி/அலுவலகத்தில் விண்ணப்பிக்கவும்." if lang == "tamil" else "- Visit the official website or nearest CSC/office and apply.")

        if website:
            lines.append(f"\nஅதிகாரப்பூர்வ இணையதளம்: {website}" if lang == "tamil" else f"\nOfficial site: {website}")

        return "\n".join(lines)

    def _format_scheme_details(self, scheme: Dict[str, Any]) -> str:
        name = scheme.get("name_en") or scheme.get("name") or "Scheme"
        benefits = scheme.get("benefits") or []
        documents = scheme.get("documents_required") or []
        process = scheme.get("application_process") or []
        website = scheme.get("website")
        eligibility = scheme.get("eligibility_summary") or scheme.get("eligibility_criteria")

        lines: List[str] = []
        lines.append(f"{name}")

        if benefits:
            lines.append("\nBenefits:")
            for b in benefits[:3]:
                lines.append(f"- {b}")

        if eligibility:
            lines.append("\nEligibility (high level):")
            if isinstance(eligibility, str):
                lines.append(f"- {eligibility}")
            elif isinstance(eligibility, dict):
                # Keep it short
                for k in ["min_age", "max_age", "max_income", "states", "is_farmer", "is_bpl", "gender"]:
                    if k in eligibility:
                        lines.append(f"- {k}: {eligibility.get(k)}")

        if documents:
            lines.append("\nDocuments:")
            for d in documents[:4]:
                lines.append(f"- {d}")

        if process:
            lines.append("\nHow to apply:")
            for step in process[:4]:
                lines.append(f"- {step}")

        if website:
            lines.append(f"\nOfficial site: {website}")

        lines.append("\nIf you share your state + age + income, I can quickly check eligibility.")
        return "\n".join(lines)

    def _msg(self, key: str, *, raw: bool = False) -> str:
        lang = self.session.language

        # Keep this minimal; translations handled by LLM where possible.
        if lang == "tamil":
            messages = {
                "empty": "தயவு செய்து பேசுங்கள்.",
                "greet": "திட்டத்தின் பெயரை பேசிச் சொல்லுங்கள் (எ.கா., பிரதான் மந்திரி ஆவாஸ் யோஜனா, பிரதான் மந்திரி கிசான் சம்மான் நிதி) அல்லது வகையை சொல்லுங்கள் (வீடு / விவசாயம் / சுகாதாரம்).",
                "not_found": "உள்ளூர் பட்டியலில் அந்த திட்டத்தை கண்டுபிடிக்க முடியவில்லை. திட்டத்தின் பெயரை தெளிவாக பேசிச் சொல்லுங்கள் (எ.கா., பிரதான் மந்திரி ஆவாஸ் யோஜனா, பிரதான் மந்திரி கிசான் சம்மான் நிதி).",
            }
            return messages.get(key, "")

        # English
        messages_en = {
            "empty": "Please type or speak something.",
            "greet": "Tell me the scheme name (e.g., PM-KISAN / PMAY) or the category you need (housing / agriculture / health).",
            "not_found": "I couldn't find that scheme in the local list. Try typing the exact scheme name or short form (e.g., PM-KISAN, PMAY).",
        }
        return messages_en.get(key, "")
