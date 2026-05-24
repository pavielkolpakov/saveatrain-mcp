class SATError(Exception):
    """Base class for Save a Train API errors."""


class SATAuthError(SATError):
    """401/403 - bad token, expired, or IP not whitelisted."""


class SATNotFoundError(SATError):
    """404 - resource missing."""


class SATValidationError(SATError):
    """422 - reserved for non-tool internal use; tools receive structured data instead."""


class SATUpstreamError(SATError):
    """5xx - SAT or a downstream rail provider is unhealthy."""


class SATTimeoutError(SATError):
    """Network timeout reaching SAT."""
