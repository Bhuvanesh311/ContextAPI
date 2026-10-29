
class EngineException(Exception):
    pass

class ExecutionTimeoutError(EngineException):
    pass

class OperatorExecutionError(EngineException):
    pass

class ScopeViolationError(EngineException):
    pass

class ContentResolutionError(EngineException):
    pass

class ConfigurationError(EngineException):
    pass
