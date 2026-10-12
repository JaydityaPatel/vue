class VueException(Exception):
    """Base exception for application-level errors."""


class NotFoundError(VueException):
    pass


class ValidationError(VueException):
    pass
