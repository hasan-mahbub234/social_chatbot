"""
Multilingual Normalizer — normalizes mixed-language and transliterated queries
into retrieval-ready English form.

DESIGN PRINCIPLE: Entity preservation over noise removal.
  - Intent words (দাম, কত, আছে) → translate to English
  - Product/entity words (বক্সার, কম্বো, মেনস) → transliterate to English script
  - Bengali-script English loanwords (প্রাইস, সাইজ) → recover original English
  - Bengali digits (৩, ২, ১) → convert to ASCII digits
  - Unknown Bengali words → transliterate phonetically, NEVER delete
  - English words already in query → keep unchanged

Examples:
  "মেনস বক্সার কম্বো ৩ পিচ এর দাম কত?"  → "mens boxer combo 3 piece price"
  "মেনস ব্রিপ কম্বো প্রাইস কত?"          → "mens brief combo price how much"
  "ফেরত policy"                            → "return policy"
  "Virant kids sport shoes এর দাম কাত?"   → "Virant kids sport shoes price"
  "size chart ache?"                       → "size chart available"
"""
import re
import unicodedata
from typing import Dict, Optional
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Bengali digit → ASCII ─────────────────────────────────────────────────────
BENGALI_DIGITS: Dict[str, str] = {
    "০": "0", "১": "1", "২": "2", "৩": "3", "৪": "4",
    "৫": "5", "৬": "6", "৭": "7", "৮": "8", "৯": "9",
}

# ── Bengali Unicode → English (intent + function words only) ──────────────────
# RULE: Only translate words that carry INTENT, not product identity.
# Product nouns go in BENGALI_PRODUCT_MAP below.
BENGALI_INTENT_MAP: Dict[str, str] = {
    # Price / cost intent
    "দাম":          "price",
    "মূল্য":        "price",
    "কত":           "how much",
    "কাত":          "how much",    # common misspelling of কত
    "দর":           "rate price",

    # Availability intent
    "আছে":          "available",
    "পাওয়া":       "available",
    "নেই":          "not available",
    "স্টক":         "stock",

    # Policy / service intent
    "ফেরত":         "return",
    "বিনিময়":      "exchange",
    "পলিসি":        "policy",
    "নীতি":         "policy",
    "ডেলিভারি":     "delivery",
    "ওয়ারেন্টি":   "warranty",
    "গ্যারান্টি":   "guarantee",

    # Connectors / question words (safe to translate — carry no product info)
    "এর":           "",            # possessive particle — drop it
    "এটির":         "",            # "of this" pronoun — drop it
    "এটা":          "",            # "this" pronoun — drop it
    "এটি":          "",            # "this" pronoun — drop it
    "ওটার":         "",            # "of that" pronoun — drop it
    "ওটা":          "",            # "that" pronoun — drop it
    "সেটার":        "",            # "of that" pronoun — drop it
    "সেটি":         "",            # "that" pronoun — drop it
    "সেটা":         "",            # "that" pronoun — drop it
    "এগুলোর":       "",            # "of these" pronoun — drop it
    "এগুলো":        "",            # "these" pronoun — drop it
    "কি":           "",            # question particle — drop it
    "কী":           "",
    "কোনটা":        "which",
    "কোথায়":       "where",
    "কখন":          "when",
    "কিভাবে":       "how",
    "কেন":          "why",

    # Attributes
    "রঙ":           "color",
    "সাইজ":         "size",
    "কাপড়":        "fabric",
    "পণ্য":         "product",
}

# ── Bengali product/category words → English transliteration ─────────────────
# RULE: These are product nouns. Translate to their English commerce equivalent.
# When in doubt, transliterate phonetically rather than delete.
BENGALI_PRODUCT_MAP: Dict[str, str] = {
    # Clothing categories
    "শার্ট":        "shirt",
    "টিশার্ট":      "tshirt",
    "প্যান্ট":      "pant",
    "পাজামা":       "pajama",
    "লুঙ্গি":       "lungi",
    "গেঞ্জি":       "vest undershirt",
    "বক্সার":       "boxer",
    "আন্ডারওয়্যার": "underwear",
    "ব্রিফ":        "brief",
    "জ্যাকেট":      "jacket",
    "হুডি":         "hoodie",
    "সোয়েটার":     "sweater",
    "কোট":          "coat",
    "ব্লেজার":      "blazer",
    "শাড়ি":        "saree",
    "কুর্তা":       "kurta",
    "পাঞ্জাবি":     "panjabi",
    "ফ্রক":         "frock",
    "ড্রেস":        "dress",
    "লেগিংস":       "leggings",
    "জিন্স":        "jeans",
    "শর্টস":        "shorts",
    "ট্রাউজার":     "trouser",
    "স্কার্ট":      "skirt",
    "টপস":          "tops",
    "ব্লাউজ":       "blouse",

    # Footwear
    "জুতা":         "shoes",
    "স্যান্ডেল":    "sandal",
    "স্নিকার":      "sneaker",
    "বুট":          "boot",
    "স্লিপার":      "slipper",
    "হিল":          "heels",

    # Accessories
    "ব্যাগ":        "bag",
    "ব্যাকপ্যাক":   "backpack",
    "পার্স":        "purse",
    "ওয়ালেট":      "wallet",
    "বেল্ট":        "belt",
    "টুপি":         "cap hat",
    "মোজা":         "socks",
    "স্কার্ফ":      "scarf",
    "সানগ্লাস":     "sunglasses",
    "ঘড়ি":         "watch",

    # Bundle / quantity words (critical for combo queries)
    "কম্বো":        "combo",
    "পিচ":          "piece",
    "পিস":          "piece",
    "সেট":          "set",
    "প্যাক":        "pack",
    "জোড়া":        "pair",
    "ডজন":          "dozen",

    # Gender / demographic
    "মেনস":         "mens",
    "মেন":          "men",
    "উইমেন":        "women",
    "লেডিস":        "ladies",
    "কিডস":         "kids",
    "বয়েজ":        "boys",
    "গার্লস":       "girls",
    "বাচ্চা":       "kids children",
    "ছেলে":         "boys mens",
    "মেয়ে":        "girls womens",

    # Colors
    "লাল":          "red",
    "নীল":          "blue",
    "কালো":         "black",
    "সাদা":         "white",
    "হলুদ":         "yellow",
    "সবুজ":         "green",
    "ধূসর":         "grey",
    "বাদামি":       "brown",
    "গোলাপি":       "pink",
    "কমলা":         "orange",
    "বেগুনি":       "purple",
    "নেভি":         "navy",

    # Sizes
    "ছোট":          "small",
    "বড়":          "large big",
    "মাঝারি":       "medium",

    # Materials
    "সুতা":         "cotton thread",
    "পলিয়েস্টার":  "polyester",
    "কটন":          "cotton",
    "লিনেন":        "linen",
    "ডেনিম":        "denim",
    "ফ্লিস":        "fleece",
    "জার্সি":       "jersey",
    "সিল্ক":        "silk",
    "উল":           "wool",

    # Sports / activity
    "স্পোর্টস":     "sports",
    "স্পোর্ট":      "sport",
    "ক্যাজুয়াল":   "casual",
    "ফর্মাল":       "formal",
    "ট্রেনিং":      "training",
    "রানিং":        "running",
    "জিম":          "gym",
    "ফুটবল":        "football",
    "ক্রিকেট":      "cricket",
}

# ── Bengali-script English loanwords → original English ──────────────────────
# Users often write English product/commerce words in Bengali script.
# These must be recovered BEFORE phonetic transliteration runs.
# Pattern: Bengali phonetic spelling → correct English word
BENGALI_LOANWORD_MAP: Dict[str, str] = {
    # Price / commerce
    "প্রাইস":       "price",
    "প্রাইজ":       "price",
    "কস্ট":         "cost",
    "রেট":          "rate",
    "অফার":         "offer",
    "ডিসকাউন্ট":    "discount",
    "সেল":          "sale",
    "ফ্রি":         "free",
    "চার্জ":        "charge",
    "পেমেন্ট":      "payment",
    "ক্যাশ":        "cash",
    "অনলাইন":       "online",

    # Size / fit
    "সাইজ":         "size",
    "ফিট":          "fit",
    "স্মল":         "small",
    "মিডিয়াম":     "medium",
    "লার্জ":        "large",
    "এক্সএল":       "XL",
    "এক্সএক্সএল":   "XXL",

    # Product terms
    "কালার":        "color",
    "কালার":        "color",
    "ডিজাইন":       "design",
    "কোয়ালিটি":    "quality",
    "অরিজিনাল":     "original",
    "কপি":          "copy",
    "ব্র্যান্ড":    "brand",
    "প্রোডাক্ট":    "product",
    "আইটেম":        "item",
    "স্টক":         "stock",
    "অ্যাভেইলেবল":  "available",
    "ডেলিভারি":     "delivery",
    "শিপিং":        "shipping",
    "রিটার্ন":      "return",
    "এক্সচেঞ্জ":    "exchange",
    "ওয়ারেন্টি":   "warranty",

    # Clothing loanwords
    "টিশার্ট":      "tshirt",
    "শার্ট":        "shirt",       # already in product map but add here too
    "প্যান্ট":      "pant",
    "জ্যাকেট":      "jacket",
    "হুডি":         "hoodie",
    "সোয়েটার":     "sweater",
    "ড্রেস":        "dress",
    "লেগিংস":       "leggings",
    "জিন্স":        "jeans",
    "শর্টস":        "shorts",
    "স্নিকার":      "sneaker",
    "স্যান্ডেল":    "sandal",
    "ব্যাগ":        "bag",
    "ব্যাকপ্যাক":   "backpack",
    "ওয়ালেট":      "wallet",
    "বেল্ট":        "belt",
    "স্কার্ফ":      "scarf",
    "সানগ্লাস":     "sunglasses",
    "কম্বো":        "combo",
    "প্যাক":        "pack",
    "সেট":          "set",

    # Gender / demographic loanwords
    "মেনস":         "mens",
    "উইমেন":        "women",
    "লেডিস":        "ladies",
    "কিডস":         "kids",
    "বয়েজ":        "boys",
    "গার্লস":       "girls",

    # Sports loanwords
    "স্পোর্টস":     "sports",
    "স্পোর্ট":      "sport",
    "ক্যাজুয়াল":   "casual",
    "ফর্মাল":       "formal",
    "ট্রেনিং":      "training",
    "রানিং":        "running",
}

# ── Post-transliteration phonetic correction ──────────────────────────────────
# After phonetic transliteration, some common near-misses need correction.
# These are ASCII words that result from transliteration of misspelled loanwords.
# e.g. ব্রিপ (user misspelled ব্রিফ) → transliterates to "brip" → correct to "brief"
PHONETIC_CORRECTION_MAP: Dict[str, str] = {
    # Underwear category (ফ/ph vs প/p confusion)
    "brip":         "brief",
    "brif":         "brief",
    "briphs":       "briefs",
    "boxer":        "boxer",    # already correct — keep
    "bokshar":      "boxer",
    "boksar":       "boxer",

    # Price variants from transliteration
    "prais":        "price",
    "praiz":        "price",
    "prise":        "price",
    "praice":       "price",

    # Size variants
    "shaiz":        "size",
    "shaize":       "size",
    "sais":         "size",

    # Color variants
    "kalar":        "color",
    "colour":       "color",
    "kolour":       "color",

    # Shirt variants
    "shart":        "shirt",
    "shert":        "shirt",
    "tishirt":      "tshirt",
    "tee-shirt":    "tshirt",

    # Pant variants
    "phyant":       "pant",
    "pyant":        "pant",

    # Jacket variants
    "jyaket":       "jacket",
    "jaket":        "jacket",

    # Hoodie variants
    "hudi":         "hoodie",
    "hoodee":       "hoodie",

    # Combo / pack
    "kombo":        "combo",
    "phyak":        "pack",
    "pyak":         "pack",

    # Delivery / shipping
    "delivari":     "delivery",
    "deliveri":     "delivery",
    "shiping":      "shipping",
    "sheping":      "shipping",

    # Return / exchange
    "ritern":       "return",
    "ritarn":       "return",
    "ekscheinj":    "exchange",
    "excheinj":     "exchange",

    # Discount / offer
    "diskount":     "discount",
    "diskaunt":     "discount",
    "ophaar":       "offer",
    "ophar":        "offer",

    # Quality / original
    "koyaliti":     "quality",
    "kwality":      "quality",
    "orijinal":     "original",
    "orijinaL":     "original",
}
# Only intent/function words. Product words in Banglish are kept as-is
# because they are already English-script and readable by BM25.
BANGLISH_INTENT_MAP: Dict[str, str] = {
    "dam":      "price",
    "daam":     "price",
    "dor":      "rate price",
    "koto":     "how much",
    "kemon":    "how",
    "ache":     "available",
    "nai":      "not available",
    "nei":      "not available",
    "er":       "",         # possessive — drop
    "ke":       "",         # object marker — drop
    "te":       "",         # locative — drop
    "pathano":  "delivery send",
    "ferot":    "return",
    "ferat":    "return",
    "bodol":    "exchange",
    "taka":     "BDT",
    "din":      "days",
    "somoy":    "time",
    "kobe":     "when",
    "kothay":   "where",
    "keno":     "why",
    "kivabe":   "how",
    "asol":     "original authentic",
    "nakol":    "fake duplicate",
}

# ── Banglish (Bengali phonetic in English script) → English ───────────────────
# Maps Bengali Unicode character clusters to their phonetic English equivalent.
# Used as last resort when a word is not in any dictionary above.
_PHONETIC: Dict[str, str] = {
    "ক": "k", "খ": "kh", "গ": "g", "ঘ": "gh", "ঙ": "ng",
    "চ": "ch", "ছ": "chh", "জ": "j", "ঝ": "jh",
    "ট": "t", "ঠ": "th", "ড": "d", "ঢ": "dh", "ণ": "n",
    "ত": "t", "থ": "th", "দ": "d", "ধ": "dh", "ন": "n",
    "প": "p", "ফ": "ph", "ব": "b", "ভ": "bh", "ম": "m",
    "য": "y", "র": "r", "ল": "l", "শ": "sh", "ষ": "sh",
    "স": "s", "হ": "h", "ড়": "r", "ঢ়": "rh", "য়": "y",
    "ৎ": "t", "ং": "ng", "ঃ": "h", "ঁ": "",
    # Vowels
    "অ": "o", "আ": "a", "ই": "i", "ঈ": "i", "উ": "u", "ঊ": "u",
    "ঋ": "ri", "এ": "e", "ঐ": "oi", "ও": "o", "ঔ": "ou",
    # Vowel diacritics (matras)
    "া": "a", "ি": "i", "ী": "i", "ু": "u", "ূ": "u",
    "ৃ": "ri", "ে": "e", "ৈ": "oi", "ো": "o", "ৌ": "ou",
    "্": "",   # hasanta — suppress inherent vowel
}

_BENGALI_RE = re.compile(r'[\u0980-\u09FF]+')


def _transliterate_word(word: str) -> str:
    """Phonetically transliterate a Bengali Unicode word to English script."""
    result = []
    i = 0
    while i < len(word):
        # Try 2-char cluster first (conjuncts like ক্ষ)
        two = word[i:i+2]
        if two in _PHONETIC:
            result.append(_PHONETIC[two])
            i += 2
            continue
        ch = word[i]
        result.append(_PHONETIC.get(ch, ch))
        i += 1
    return "".join(result).strip()


class MultilingualNormalizer:
    """
    Normalize mixed-language queries to English for retrieval.

    Pipeline:
      1. Convert Bengali digits → ASCII digits
      2. Translate known Bengali product words → English
      3. Translate known Bengali intent words → English
      4. Translate Banglish intent words → English
      5. Transliterate remaining unknown Bengali words (NEVER delete)
      6. Clean up whitespace
    """

    def normalize(self, query: str) -> str:
        """Return English-normalized version of the query."""
        if not query or not query.strip():
            return query

        original = query.strip()
        has_bengali = bool(_BENGALI_RE.search(original))

        # Fast path: pure English with no Banglish intent words
        if not has_bengali:
            return self._normalize_banglish_only(original)

        normalized = original

        # Step 1: Bengali digits → ASCII
        for bn_digit, ascii_digit in BENGALI_DIGITS.items():
            normalized = normalized.replace(bn_digit, ascii_digit)

        # Step 2: Bengali-script English loanwords → original English
        # Run BEFORE product map so প্রাইস → price before phonetic transliteration
        for bengali, english in sorted(BENGALI_LOANWORD_MAP.items(), key=lambda x: -len(x[0])):
            if bengali in normalized:
                normalized = normalized.replace(bengali, f" {english} " if english else " ")

        # Step 3: Product words
        for bengali, english in sorted(BENGALI_PRODUCT_MAP.items(), key=lambda x: -len(x[0])):
            if bengali in normalized:
                normalized = normalized.replace(bengali, f" {english} " if english else " ")

        # Step 4: Intent words
        for bengali, english in sorted(BENGALI_INTENT_MAP.items(), key=lambda x: -len(x[0])):
            if bengali in normalized:
                normalized = normalized.replace(bengali, f" {english} " if english else " ")

        # Step 5: Banglish intent words
        normalized = self._normalize_banglish_only(normalized)

        # Step 6: Transliterate remaining Bengali Unicode (NEVER delete)
        def _transliterate_match(m: re.Match) -> str:
            word = m.group(0)
            transliterated = _transliterate_word(word)
            return transliterated if transliterated.strip() else ""

        normalized = _BENGALI_RE.sub(_transliterate_match, normalized)

        # Step 7: Post-transliteration phonetic correction
        # Fix near-misses like "brip" → "brief", "prais" → "price"
        words = normalized.split()
        corrected = []
        for word in words:
            clean = re.sub(r'[^a-z]', '', word.lower())
            corrected.append(PHONETIC_CORRECTION_MAP.get(clean, word))
        normalized = " ".join(corrected)

        # Step 8: Clean up
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        normalized = re.sub(r'[?!.]+$', '', normalized).strip()
        normalized = " ".join(w for w in normalized.split() if w)

        if normalized.lower() != original.lower():
            logger.info(
                "query_multilingual_normalized",
                original=original[:80],
                normalized=normalized[:80],
            )

        return normalized

    def _normalize_banglish_only(self, text: str) -> str:
        """Apply Banglish intent word normalization to ASCII text."""
        words = text.split()
        result = []
        for word in words:
            # Strip punctuation for lookup, preserve original if no match
            clean = re.sub(r'[^a-zA-Z0-9]', '', word.lower())
            if clean and clean in BANGLISH_INTENT_MAP:
                replacement = BANGLISH_INTENT_MAP[clean]
                if replacement:
                    result.append(replacement)
                # else: drop (particle)
            else:
                result.append(word)
        return " ".join(result)

    def is_multilingual(self, query: str) -> bool:
        """Check if query contains Bengali Unicode characters."""
        return bool(_BENGALI_RE.search(query))

    def detect_language(self, query: str) -> str:
        """Detect primary language of query."""
        bengali_chars = len(re.findall(r'[\u0980-\u09FF]', query))
        english_chars = len(re.findall(r'[a-zA-Z]', query))
        if bengali_chars > english_chars:
            return "bengali"
        if bengali_chars > 0:
            return "mixed"
        return "english"


multilingual_normalizer = MultilingualNormalizer()
