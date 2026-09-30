from __mapping__ import *

# Truthiness golden mapping (docs/ARCHITECTURE.md, §Truthiness): each output field says whether the
# input field of the same name is true ("T") or false ("F") as a condition. Every backend must
# agree with Python on every probe (tests/golden/truthiness).


@dataclass
class Truthiness:
    Missing: str
    JsonNull: str
    BoolFalse: str
    Zero: str
    ZeroFloat: str
    EmptyString: str
    EmptyArray: str
    EmptyObject: str
    BoolTrue: str
    One: str
    Text: str
    ZeroString: str
    Array: str
    Object: str


def missing(root: Any) -> str:
    return if_else(root.missing, "T", "F")


def json_null(root: Any) -> str:
    return if_else(root.json_null, "T", "F")


def bool_false(root: Any) -> str:
    return if_else(root.bool_false, "T", "F")


def zero(root: Any) -> str:
    return if_else(root.zero, "T", "F")


def zero_float(root: Any) -> str:
    return if_else(root.zero_float, "T", "F")


def empty_string(root: Any) -> str:
    return if_else(root.empty_string, "T", "F")


def empty_array(root: Any) -> str:
    return if_else(root.empty_array, "T", "F")


def empty_object(root: Any) -> str:
    return if_else(root.empty_object, "T", "F")


def bool_true(root: Any) -> str:
    return if_else(root.bool_true, "T", "F")


def one(root: Any) -> str:
    return if_else(root.one, "T", "F")


def text(root: Any) -> str:
    return if_else(root.text, "T", "F")


def zero_string(root: Any) -> str:
    return if_else(root.zero_string, "T", "F")


def array(root: Any) -> str:
    return if_else(root.array, "T", "F")


def object(root: Any) -> str:
    return if_else(root.object, "T", "F")


out.Missing = missing(root)
out.JsonNull = json_null(root)
out.BoolFalse = bool_false(root)
out.Zero = zero(root)
out.ZeroFloat = zero_float(root)
out.EmptyString = empty_string(root)
out.EmptyArray = empty_array(root)
out.EmptyObject = empty_object(root)
out.BoolTrue = bool_true(root)
out.One = one(root)
out.Text = text(root)
out.ZeroString = zero_string(root)
out.Array = array(root)
out.Object = object(root)
