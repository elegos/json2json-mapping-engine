from __mapping__ import *

__id__ = 'aggregate_by'

# Aggregates over a condition and over a computed value, golden mapping (docs/ARCHITECTURE.md,
# §Built-in functions, Aggregation): `sum(expr for x in list if cond)` and the same with `count`,
# `max`, `min`, `avg`. Every backend must give the same results (tests/golden/aggregate_by).
# `samples` may be empty or missing (count and sum give 0); `readings` always has a passing element
# (the others would give null, which the backends write differently).


def ok_count(root: Any) -> number:
    return count(s for s in root.samples if s.quality == "OK")


out.OkCount = ok_count(root)


def ok_total(root: Any) -> number:
    return sum(s.value for s in root.samples if s.quality == "OK")


out.OkTotal = ok_total(root)


def big_ok_total(root: Any) -> number:
    return sum(s.value for s in root.samples if s.quality == "OK" if s.value > 10)


out.BigOkTotal = big_ok_total(root)


def abs_total(root: Any) -> number:
    return sum(abs(r.quantity) for r in root.readings)


out.AbsTotal = abs_total(root)


def ok_max(root: Any) -> number:
    return max(r.quantity for r in root.readings if r.quality == "OK")


out.OkMax = ok_max(root)


def ok_min(root: Any) -> number:
    return min(r.quantity * 2 for r in root.readings if r.quality == "OK")


out.OkMin = ok_min(root)


def ok_avg(root: Any) -> number:
    return avg(r.quantity for r in root.readings if r.quality == "OK")


out.OkAvg = ok_avg(root)


def plain_total(root: Any) -> number:
    return sum(root.samples, "value")


out.PlainTotal = plain_total(root)


def plain_count(root: Any) -> number:
    return count(root.samples)


out.PlainCount = plain_count(root)
