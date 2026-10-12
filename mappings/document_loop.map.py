from __mapping__ import *

# A loop over the document itself (`source: $` in a functional): the whole message is the one
# element of an output list, and a second loop adding to the same list after it. Every backend
# must agree (tests/golden/document_loop).


@dataclass
class EntriesItem:
    Key: str
    Label: str | None


def entry(root: Any, src: Any) -> EntriesItem:
    return EntriesItem(Key=src.id, Label=concat(src.id, "/", src.name))


for src in root:
    out.Entries.append(entry(root, src))


def fine(root: Any, f: Any) -> EntriesItem:
    return EntriesItem(Key="fine", Label=to_string(f.amount))


for f in root.fines:
    out.Entries.append(fine(root, f))
