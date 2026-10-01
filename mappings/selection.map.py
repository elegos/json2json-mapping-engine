from __mapping__ import *

# Element selection golden mapping (docs/ARCHITECTURE.md, §Selecting one element): an object
# built from the first list element that satisfies a condition, omitted when none does. Every
# backend must agree (tests/golden/selection). Shape as generated from
#   source: $.myList[discriminator = 'MY D' and other = $.rootElement]


@dataclass
class MyObject:
    Id: str
    Name: str


@dataclass
class Selection:
    A: str
    MyObject: MyObject | None


def a(root: Any) -> str:
    return root.id


def my_object(root: Any, src: Any) -> MyObject:
    return MyObject(Id=split_first(src.remarks, "|"), Name=src.name)


def my_object_first(root: Any) -> MyObject | None:
    matches = []
    for item in root.myList:
        if not (item.discriminator == "MY D" and item.other == root.rootElement):
            continue
        matches.append(my_object(root, item))
    if matches:
        return matches[0]
    return


out.A = a(root)
out.MyObject = my_object_first(root)
