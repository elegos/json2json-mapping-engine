from __mapping__ import *

# Timestamps, day arithmetic, the last part of a text and joined lists, golden mapping
# (docs/ARCHITECTURE.md, §Built-in functions): each output field is one call. A missing value gives
# a missing result (the field is not written). Every backend must agree (tests/golden/builtins_dates).


def as_written(root: Any) -> str:
    return rfc3339_normalize(root.ts)


out.AsWritten = as_written(root)

def millis(root: Any) -> str:
    return rfc3339_normalize(root.ts, 3)


out.Millis = millis(root)

def no_fraction(root: Any) -> str:
    return rfc3339_normalize(root.ts, 0)


out.NoFraction = no_fraction(root)

def millis_utc(root: Any) -> str:
    return to_utc(root.ts, 3)


out.MillisUtc = millis_utc(root)

def parsed(root: Any) -> str:
    return parse_timestamp(root.us, 'MON DD, YYYY, HH12:MI:SS AM')


out.Parsed = parsed(root)

def printed(root: Any) -> str:
    return format_date(parse_timestamp(root.us, 'MON DD, YYYY, HH12:MI:SS AM'), 'DD-MM-YYYY HH24:MI:SS')


out.Printed = printed(root)

def days_overdue(root: Any) -> number:
    return days_between(root.due, parse_timestamp(root.us, 'MON DD, YYYY, HH12:MI:SS AM'))


out.DaysOverdue = days_overdue(root)

def later(root: Any) -> str:
    return add_days(root.date, root.n)


out.Later = later(root)

def earlier(root: Any) -> str:
    return add_days(root.date, 0 - 5)


out.Earlier = earlier(root)

def last_part(root: Any) -> str:
    return split_last(root.id, '-')


out.LastPart = last_part(root)

def tags(root: Any) -> str:
    return join(root.tags, ', ')


out.Tags = tags(root)

def glued(root: Any) -> str:
    return join(root.tags)


out.Glued = glued(root)

def ok_ids(root: Any) -> str:
    return join((to_string(i.id) for i in root.items if i.ok), '|')


out.OkIds = ok_ids(root)

def custom(root: Any) -> str:
    return parse_timestamp(root.us, root.fmt)


out.Custom = custom(root)
