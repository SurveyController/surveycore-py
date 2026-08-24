import re

_MULTI_LIMIT_ATTRIBUTE_NAMES = (
    "max",
    "maxvalue",
    "maxValue",
    "maxcount",
    "maxCount",
    "maxchoice",
    "maxChoice",
    "maxselect",
    "maxSelect",
    "selectmax",
    "selectMax",
    "maxsel",
    "maxSel",
    "maxnum",
    "maxNum",
    "maxlimit",
    "maxLimit",
    "data-max",
    "data-maxvalue",
    "data-maxcount",
    "data-maxchoice",
    "data-maxselect",
    "data-selectmax",
)
_MULTI_LIMIT_VALUE_KEYSET = {
    "max",
    "maxvalue",
    "maxcount",
    "maxchoice",
    "maxselect",
    "selectmax",
}
_MULTI_MIN_LIMIT_ATTRIBUTE_NAMES = (
    "min",
    "minvalue",
    "minValue",
    "mincount",
    "minCount",
    "minchoice",
    "minChoice",
    "minselect",
    "minSelect",
    "selectmin",
    "selectMin",
    "minsel",
    "minSel",
    "minnum",
    "minNum",
    "minlimit",
    "minLimit",
    "data-min",
    "data-minvalue",
    "data-mincount",
    "data-minchoice",
    "data-minselect",
    "data-selectmin",
)
_MULTI_MIN_LIMIT_VALUE_KEYSET = {
    "min",
    "minvalue",
    "mincount",
    "minchoice",
    "minselect",
    "selectmin",
    "minlimit",
}
_SELECTION_KEYWORDS_CN = ("选", "選", "选择", "多选", "复选")
_SELECTION_KEYWORDS_EN = ("option", "options", "choice", "choices", "select", "choose")

_CHINESE_MULTI_LIMIT_PATTERNS = (
    re.compile(r"(?:最多|至多|不超过|不超過)\s*(?:选|選|选择|選擇)?\s*(\d+)\s*[个項项]?"),
    re.compile(r"(?:限选|限選)\s*(\d+)\s*[个項项条]?"),
)
_CHINESE_MULTI_RANGE_PATTERNS = (
    re.compile(
        r"(?:请[选選择擇]?|可选|可選|需选|需選|选择|選擇|勾选|勾選)\s*(\d+)\s*"
        r"(?:-|－|—|–|~|～|至|到)\s*(\d+)(?:\s*[个項项条])?"
    ),
    re.compile(
        r"至少\s*(\d+)\s*[个項项条]?(?:[^0-9]{0,6})"
        r"(?:最多|至多|不超过|不超過)\s*(\d+)\s*[个項项条]?"
    ),
    re.compile(
        r"(?:限选|限選)\s*(\d+)\s*(?:-|－|—|–|~|～|至|到)\s*(\d+)"
        r"(?:\s*[个項项条])?"
    ),
)
_CHINESE_MULTI_EXACT_PATTERNS = (
    re.compile(r"(?:请)?(?:选|選|选择|選擇|勾选|勾選)\s*(\d+)\s*[个項项条]"),
    re.compile(r"(?:必须|需|需要)\s*(?:选|選|选择|選擇|勾选|勾選)\s*(\d+)\s*[个項项条]"),
)
_CHINESE_MULTI_MIN_PATTERNS = (
    re.compile(r"(?:至少|最少|不少于)\s*(?:选|選|选择|選擇)?\s*(\d+)\s*[个項项条]"),
)
_ENGLISH_MULTI_LIMIT_PATTERNS = (
    re.compile(
        r"(?:select|choose|pick)\s+(?:up\s+to|at\s+most|no\s+more\s+than)\s+(\d+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:up\s+to|at\s+most|no\s+more\s+than)\s+(\d+)\s+(?:options?|choices?|items?)",
        re.IGNORECASE,
    ),
)
_ENGLISH_MULTI_RANGE_PATTERNS = (
    re.compile(
        r"(?:select|choose|pick)\s*(\d+)\s*(?:-|–|—|~|～|to)\s*(\d+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:select|choose)\s+between\s+(\d+)\s+and\s+(\d+)",
        re.IGNORECASE,
    ),
)
_ENGLISH_MULTI_EXACT_PATTERNS = (
    re.compile(
        r"(?:select|choose|pick)\s+(\d+)\s+(?:options?|choices?|items?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:must|need\s+to|please)\s+(?:select|choose|pick)\s+(\d+)",
        re.IGNORECASE,
    ),
)
_ENGLISH_MULTI_MIN_PATTERNS = (
    re.compile(r"(?:at\s+least|min(?:imum)?\s*)\s*(\d+)", re.IGNORECASE),
)
