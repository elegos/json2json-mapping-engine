from __mapping__ import *

# Empty-text golden mapping (docs/ARCHITECTURE.md, §Empty text): an empty text is null, as in Oracle,
# whatever backend runs the mapping. A field that gives "~" is one whose value was null (an empty
# text included) and fell back on `coalesce`; `IsEmpty...` fields say "T" / "F" for `is_empty`;
# the others carry the value.
# Every backend must agree (tests/golden/empty_text).


@dataclass
class EmptyText:
    Nth0: str
    Nth1: str | None
    Nth2: str | None
    Nth3: str
    Nth5: str
    Nth6: str | None
    Nth7: str
    Nth8: str
    First: str | None
    FirstLeadingEmpty: str
    FirstOfBlank: str
    Blank: str
    ConcatBlanks: str
    ReplaceToEmpty: str
    IsEmptyBlank: str
    IsEmptyMissing: str
    IsEmptyNull: str
    IsEmptyText: str
    IsEmptyZero: str
    IsEmptyZeroOption: str
    IsEmptyNumberOption: str
    IsEmptyFalse: str
    IsEmptyList: str
    IsEmptyPart: str
    IsEmptyRoundedZero: str


def nth_0(root: Any) -> str:
    return coalesce(split_nth(root.s, "|", 0), "~")


def nth_1(root: Any) -> str | None:
    return split_nth(root.s, "|", 1)


def nth_2(root: Any) -> str | None:
    return split_nth(root.s, "|", 2)


def nth_3(root: Any) -> str:
    return coalesce(split_nth(root.s, "|", 3), "~")


def nth_5(root: Any) -> str:
    return coalesce(split_nth(root.s, "|", 5), "~")


def nth_6(root: Any) -> str | None:
    return split_nth(root.s, "|", 6)


def nth_7(root: Any) -> str:
    return coalesce(split_nth(root.s, "|", 7), "~")


def nth_8(root: Any) -> str:
    return coalesce(split_nth(root.s, "|", 8), "~")


def first(root: Any) -> str | None:
    return split_first(root.s, "|")


def first_leading_empty(root: Any) -> str:
    return coalesce(split_first(root.s2, "|"), "~")


def first_of_blank(root: Any) -> str:
    return coalesce(split_first(root.blank, "|"), "~")


def blank(root: Any) -> str:
    return coalesce(root.blank, "~")


def concat_blanks(root: Any) -> str:
    return coalesce(concat(root.blank, root.blank), "~")


def replace_to_empty(root: Any) -> str:
    return coalesce(replace(root.word, "x", ""), "~")


def is_empty_blank(root: Any) -> str:
    return if_else(is_empty(root.blank), "T", "F")


def is_empty_missing(root: Any) -> str:
    return if_else(is_empty(root.missing), "T", "F")


def is_empty_null(root: Any) -> str:
    return if_else(is_empty(root.json_null), "T", "F")


def is_empty_text(root: Any) -> str:
    return if_else(is_empty(root.word), "T", "F")


def is_empty_zero(root: Any) -> str:
    return if_else(is_empty(root.zero), "T", "F")


def is_empty_zero_option(root: Any) -> str:
    return if_else(is_empty(root.zero, True), "T", "F")


def is_empty_number_option(root: Any) -> str:
    return if_else(is_empty(root.num, True), "T", "F")


def is_empty_false(root: Any) -> str:
    return if_else(is_empty(root.flag, True), "T", "F")


def is_empty_list(root: Any) -> str:
    return if_else(is_empty(root.list), "T", "F")


def is_empty_part(root: Any) -> str:
    return if_else(is_empty(split_nth(root.s, "|", 3)), "T", "F")


def is_empty_rounded_zero(root: Any) -> str:
    return if_else(is_empty(round(root.small), True), "T", "F")


out.Nth0 = nth_0(root)
out.Nth1 = nth_1(root)
out.Nth2 = nth_2(root)
out.Nth3 = nth_3(root)
out.Nth5 = nth_5(root)
out.Nth6 = nth_6(root)
out.Nth7 = nth_7(root)
out.Nth8 = nth_8(root)
out.First = first(root)
out.FirstLeadingEmpty = first_leading_empty(root)
out.FirstOfBlank = first_of_blank(root)
out.Blank = blank(root)
out.ConcatBlanks = concat_blanks(root)
out.ReplaceToEmpty = replace_to_empty(root)
out.IsEmptyBlank = is_empty_blank(root)
out.IsEmptyMissing = is_empty_missing(root)
out.IsEmptyNull = is_empty_null(root)
out.IsEmptyText = is_empty_text(root)
out.IsEmptyZero = is_empty_zero(root)
out.IsEmptyZeroOption = is_empty_zero_option(root)
out.IsEmptyNumberOption = is_empty_number_option(root)
out.IsEmptyFalse = is_empty_false(root)
out.IsEmptyList = is_empty_list(root)
out.IsEmptyPart = is_empty_part(root)
out.IsEmptyRoundedZero = is_empty_rounded_zero(root)
