from __mapping__ import *

__id__ = 'filtered_index'


@dataclass
class Active:
    Pos: int
    Id: str


@dataclass
class Big:
    Pos: int
    Id: str


def active_rule(i: int, itm: Any) -> Active:
    return Active(Pos=i, Id=itm.id)


def big_rule(j: int, itm: Any) -> Big:
    return Big(Pos=j, Id=itm.id)


for i, itm in enumerate([x for x in sorted(root.items, key="price") if x.status == "A"], start=1):
    out.Actives.append(active_rule(i, itm))

for j, it2 in enumerate([y for y in sorted(root.items, key="price") if y.price > 5]):
    out.Bigs.append(big_rule(j, it2))
