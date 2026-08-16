"""Internal contract keys must not fail silently.

The root of golden_score being a constant 0.0 for 4.5 months was not the
wrong key name - it was `.get("opportunities", [])`. A safe default turned
"this key does not exist" into "there are no opportunities", and the only
error path was a `logger.debug` that C-20 proved never reaches server.log.
Wrong key + silent default + invisible log = a dead input nobody can see.

Use these when one module reads a dict another module built. Not for
external payloads (Yahoo, Gemini, the bridge) - those are untrusted input
where a missing key is a normal condition to be handled, not a broken
contract between our own components.

    price = require(quote, "price", "price_source.get_price -> risk_engine")
    opps  = expect(result, "all_opportunities", "golden_engine -> scanner", [])
"""
import logging

logger = logging.getLogger("contract")
logger.setLevel(logging.INFO)   # C-20: bare module loggers inherit WARNING


def _describe(d, key, context):
    keys = sorted(d)[:12] if isinstance(d, dict) else type(d).__name__
    return ("contract violation: %s expected key %r - present keys: %s"
            % (context, key, keys))


def require(d, key, context):
    """Hard contract. Raises KeyError when the producer did not deliver.

    Use where continuing on a default would produce a confident number
    from an absent one.
    """
    if not isinstance(d, dict) or key not in d:
        raise KeyError(_describe(d, key, context))
    return d[key]


def expect(d, key, context, default=None):
    """Soft contract. Returns `default` but says so at WARNING.

    Use where the caller genuinely can carry on degraded - and wants the
    degradation on the record instead of in a silent branch.
    """
    if isinstance(d, dict) and key in d:
        return d[key]
    logger.warning("%s - falling back to %r", _describe(d, key, context), default)
    return default
