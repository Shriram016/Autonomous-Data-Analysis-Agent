class ADAAException(Exception):
    """Base exception for all ADAA pipeline errors."""
    pass

class EmptyDataFrameError(ADAAException):
    """Raised when the input DataFrame is empty or cannot be processed."""
    pass

class SchemaGenerationError(ADAAException):
    """Raised when the schema generator fails."""
    pass

class PlanExecutionError(ADAAException):
    """Raised when the executor fails to execute a plan step."""
    pass
