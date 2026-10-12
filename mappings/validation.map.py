from __mapping__ import *

# Validation of the input and the output (docs/IMPLEMENTATION_PLAN.md): the JSON Schema check of both
# sides and the extra checks, a `reject` (no output) or a `warn` (reported only). Shape as generated
# from the functional file's `validations:` section. Every backend must agree (tests/golden/validation).

__id__ = 'validation'
__validation__ = "{\"input\":{\"schema\":true,\"checks\":[{\"fn\":\"check_vat\",\"code\":\"VAT_FORMAT\",\"message\":\"vatId must be 11 digits\",\"action\":\"reject\"},{\"fn\":\"check_amount\",\"code\":\"AMOUNT_HIGH\",\"message\":\"amount above 10000\",\"action\":\"warn\"}]},\"output\":{\"schema\":true,\"checks\":[{\"fn\":\"check_positive\",\"code\":\"OUT_POSITIVE\",\"message\":\"the amount must be positive\",\"action\":\"reject\"}]}}"


def check_vat(root: Any) -> bool:
    return not root.vatId or (is_digits(root.vatId) and length(root.vatId) == 11)


def check_amount(root: Any) -> bool:
    return root.amount <= 10000


def check_positive(root: Any) -> bool:
    return root.amount > 0


def the_id(root: Any) -> str:
    return root.id


def the_amount(root: Any) -> number:
    return root.amount


def the_vat(root: Any) -> str | None:
    return root.vatId


out.id = the_id(root)
out.amount = the_amount(root)
out.vat = the_vat(root)
