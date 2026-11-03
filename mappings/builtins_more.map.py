from __mapping__ import *

# Text, number and date built-ins without patterns, golden mapping (docs/ARCHITECTURE.md,
# §Built-in functions): each output field is one call. Every backend must give the same results
# (tests/golden/builtins_more). A missing value gives a missing result, except for the tests
# (`contains`, `starts_with`, `ends_with`), which are false. A field that gives "~" (or -1 for a
# number) is one whose result was null and fell back on `coalesce`, as in the empty_text mapping.


@dataclass
class BuiltinsMore:
    Upper: str
    Lower: str
    Trimmed: str
    Length: number
    Sub: str
    SubRest: str
    SubZero: str
    First3: str
    Last3: str
    LeftLong: str
    RightLong: str
    PadZero: str
    PadLong: str
    PadRight: str
    HasDash: bool
    StartsAb: bool
    EndsAb: bool
    EmptyPart: bool
    Abs: number
    Floor: number
    Ceil: number
    DateEu: str
    DateTime: str
    DateOnlyTime: str
    Custom: str


def upper_name(root: Any) -> str:
    return coalesce(upper(root.name), "~")


def lower_name(root: Any) -> str:
    return coalesce(lower(root.name), "~")


def trimmed(root: Any) -> str:
    return coalesce(trim(root.name), "~")


def code_length(root: Any) -> number:
    return coalesce(length(root.code), 0 - 1)


def sub(root: Any) -> str:
    return coalesce(substring(root.code, 4, 2), "~")


def sub_rest(root: Any) -> str:
    return coalesce(substring(root.code, 4), "~")


def sub_zero(root: Any) -> str:
    return coalesce(substring(root.code, 0, 2), "~")


def first3(root: Any) -> str:
    return coalesce(left(root.code, 3), "~")


def last3(root: Any) -> str:
    return coalesce(right(root.code, 3), "~")


def left_long(root: Any) -> str:
    return coalesce(left(root.code, 20), "~")


def right_long(root: Any) -> str:
    return coalesce(right(root.code, 20), "~")


def pad_zero(root: Any) -> str:
    return coalesce(pad_left(to_string(root.seq), 5, "0"), "~")


def pad_long(root: Any) -> str:
    return coalesce(pad_left(root.code, 3, "0"), "~")


def pad_right_dots(root: Any) -> str:
    return coalesce(pad_right(root.code, 10, "."), "~")


def has_dash(root: Any) -> bool:
    return contains(root.code, "-")


def starts_ab(root: Any) -> bool:
    return starts_with(root.code, "ab")


def ends_ab(root: Any) -> bool:
    return ends_with(root.code, "ab")


def empty_part(root: Any) -> bool:
    return contains(root.code, "")


def absolute(root: Any) -> number:
    return abs(root.n)


def floored(root: Any) -> number:
    return floor(root.n)


def ceiled(root: Any) -> number:
    return ceil(root.n)


def date_eu(root: Any) -> str:
    return coalesce(format_date(root.date, "DD/MM/YYYY"), "~")


def date_time(root: Any) -> str:
    return coalesce(format_date(root.dt, "YYYY-MM-DD HH24:MI:SS"), "~")


def date_only_time(root: Any) -> str:
    return coalesce(format_date(root.date, "HH24:MI"), "~")


def custom(root: Any) -> str:
    return coalesce(format_date(root.date, root.fmt), "~")


out.Upper = upper_name(root)
out.Lower = lower_name(root)
out.Trimmed = trimmed(root)
out.Length = code_length(root)
out.Sub = sub(root)
out.SubRest = sub_rest(root)
out.SubZero = sub_zero(root)
out.First3 = first3(root)
out.Last3 = last3(root)
out.LeftLong = left_long(root)
out.RightLong = right_long(root)
out.PadZero = pad_zero(root)
out.PadLong = pad_long(root)
out.PadRight = pad_right_dots(root)
out.HasDash = has_dash(root)
out.StartsAb = starts_ab(root)
out.EndsAb = ends_ab(root)
out.EmptyPart = empty_part(root)
out.Abs = absolute(root)
out.Floor = floored(root)
out.Ceil = ceiled(root)
out.DateEu = date_eu(root)
out.DateTime = date_time(root)
out.DateOnlyTime = date_only_time(root)
out.Custom = custom(root)
