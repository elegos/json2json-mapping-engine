from __mapping__ import *

# Text, conversion and timestamp built-ins golden mapping (docs/ARCHITECTURE.md, §Built-in
# functions): each output field is one call, so that a failing function is that field's rule
# alone. Every backend must give the same results (tests/golden/builtins_text), except for what
# is documented as backend-specific: the dialect of regular expressions (the patterns here keep to
# what Python's `re` and Oracle's REGEXP_* share). The conversions are idempotent whatever the
# type of what they are given (a value read from the document, a typed expression, a constant).


@dataclass
class BuiltinsText:
    Replaced: str
    Removed: str
    Prefix: str
    PrefixAbsent: str
    Digits: str
    Swapped: str
    Group: str | None
    Whole: str | None
    NoGroup: str
    Fixed: str
    FixedRounded: str
    FixedWhole: str
    FixedNegative: str
    Rounded: number
    NumberFromText: number | None
    DecimalFromText: number | None
    NumberFromNumber: number | None
    NumberFromExpr: number | None
    TextFromNumber: str | None
    TextFromWhole: str | None
    TextFromSmall: str | None
    TextFromText: str | None
    TextFromBool: str | None
    TextFromList: str | None
    TextFromExpr: str | None
    TextFromConcat: str | None
    Utc: str
    UtcFraction: str
    UtcFromZ: str
    UtcNaive: str
    Rfc: str
    RfcNaive: str
    RfcZero: str


def replaced(root: Any) -> str:
    return replace(root.s, "-", "+")


def removed(root: Any) -> str:
    return replace(root.s, "-")


def prefix(root: Any) -> str:
    return remove_prefix(root.code, "ID-")


def prefix_absent(root: Any) -> str:
    return remove_prefix(root.s, "ID-")


def digits(root: Any) -> str:
    return regexp_replace(root.phone, "[^0-9]", "")


def swapped(root: Any) -> str:
    return regexp_replace(root.ref, "([a-z]+)-([0-9]+)/([0-9]+)", "\\3-\\2")


def group(root: Any) -> str | None:
    return regexp_group(root.ref, "([a-z]+)-([0-9]+)", 2)


def whole(root: Any) -> str | None:
    return regexp_group(root.ref, "[0-9]+", 0)


def no_group(root: Any) -> str:
    return coalesce(regexp_group(root.s, "[0-9]+", 0), "none")


def fixed(root: Any) -> str:
    return format_decimal(root.n, 2)


def fixed_rounded(root: Any) -> str:
    return format_decimal(root.big, 2)


def fixed_whole(root: Any) -> str:
    return format_decimal(root.whole, 0)


def fixed_negative(root: Any) -> str:
    return format_decimal(root.neg, 1)


def rounded(root: Any) -> number:
    return round(root.n)


def number_from_text(root: Any) -> number | None:
    return to_number(root.num_text)


def decimal_from_text(root: Any) -> number | None:
    return to_number(root.dec_text)


def number_from_number(root: Any) -> number | None:
    return to_number(root.n)


def number_from_expr(root: Any) -> number | None:
    return to_number(split_nth(root.pair, ",", 2))


def text_from_number(root: Any) -> str | None:
    return to_string(root.n)


def text_from_whole(root: Any) -> str | None:
    return to_string(root.whole)


def text_from_small(root: Any) -> str | None:
    return to_string(root.small)


def text_from_text(root: Any) -> str | None:
    return to_string(root.s)


def text_from_bool(root: Any) -> str | None:
    return to_string(root.flag)


def text_from_list(root: Any) -> str | None:
    return to_string(root.list)


def text_from_expr(root: Any) -> str | None:
    return to_string(round(root.n, 0))


def text_from_concat(root: Any) -> str | None:
    return to_string(concat("a", "b"))


def utc(root: Any) -> str:
    return to_utc(root.ts)


def utc_fraction(root: Any) -> str:
    return to_utc(root.ts_frac)


def utc_from_z(root: Any) -> str:
    return to_utc(root.ts_z)


def utc_naive(root: Any) -> str:
    return to_utc(root.ts_naive)


def rfc(root: Any) -> str:
    return rfc3339_normalize(root.ts)


def rfc_naive(root: Any) -> str:
    return rfc3339_normalize(root.ts_naive)


def rfc_zero(root: Any) -> str:
    return rfc3339_normalize(root.ts_zero)


out.Replaced = replaced(root)
out.Removed = removed(root)
out.Prefix = prefix(root)
out.PrefixAbsent = prefix_absent(root)
out.Digits = digits(root)
out.Swapped = swapped(root)
out.Group = group(root)
out.Whole = whole(root)
out.NoGroup = no_group(root)
out.Fixed = fixed(root)
out.FixedRounded = fixed_rounded(root)
out.FixedWhole = fixed_whole(root)
out.FixedNegative = fixed_negative(root)
out.Rounded = rounded(root)
out.NumberFromText = number_from_text(root)
out.DecimalFromText = decimal_from_text(root)
out.NumberFromNumber = number_from_number(root)
out.NumberFromExpr = number_from_expr(root)
out.TextFromNumber = text_from_number(root)
out.TextFromWhole = text_from_whole(root)
out.TextFromSmall = text_from_small(root)
out.TextFromText = text_from_text(root)
out.TextFromBool = text_from_bool(root)
out.TextFromList = text_from_list(root)
out.TextFromExpr = text_from_expr(root)
out.TextFromConcat = text_from_concat(root)
out.Utc = utc(root)
out.UtcFraction = utc_fraction(root)
out.UtcFromZ = utc_from_z(root)
out.UtcNaive = utc_naive(root)
out.Rfc = rfc(root)
out.RfcNaive = rfc_naive(root)
out.RfcZero = rfc_zero(root)
