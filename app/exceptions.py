class CanvaError(Exception):
    """Clase base para errores de la API de Canva."""
    def __init__(self, message: str, status_code: int = None, error_code: str = None, details: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.details = details

class CanvaAuthError(CanvaError):
    """Errores relacionados con la autenticación (401, invalid_grant, missing_scope)."""
    pass

class CanvaRateLimitError(CanvaError):
    """Error cuando se alcanza el límite de peticiones (429)."""
    def __init__(self, message: str, status_code: int = None, error_code: str = None, details: dict = None, retry_after: int = None):
        super().__init__(message, status_code, error_code, details)
        self.retry_after = retry_after

class CanvaConfigError(CanvaError):
    """Errores de configuración (Template ID inválido, dataset mismatch)."""
    pass

class CanvaJobFailedError(CanvaError):
    """Errores durante la ejecución de Jobs (Autofill o Exportación fallidos)."""
    pass

class CanvaTransientError(CanvaError):
    """Errores temporales del servidor de Canva (5xx, timeouts)."""
    pass

class CanvaPendingLongError(CanvaError):
    """Error cuando un trabajo tarda demasiado y se marca como pendiente largo."""
    pass
