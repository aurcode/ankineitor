"""Security-related exceptions for Ankineitor."""


class AnkineitorSecurityError(Exception):
    """Base exception for security-related errors."""
    pass


class InvalidFileError(AnkineitorSecurityError):
    """Raised when a file fails validation checks."""
    
    def __init__(self, message: str, file_name: str = None):
        self.file_name = file_name
        super().__init__(message)


class ValidationError(AnkineitorSecurityError):
    """Raised when input validation fails."""
    
    def __init__(self, message: str, field_name: str = None):
        self.field_name = field_name
        super().__init__(message)


class PathTraversalError(AnkineitorSecurityError):
    """Raised when a path traversal attempt is detected."""
    pass


class SQLInjectionError(AnkineitorSecurityError):
    """Raised when potential SQL injection is detected."""
    pass
