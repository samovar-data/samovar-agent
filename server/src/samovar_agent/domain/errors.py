"""Domain exceptions. They do not subclass built-ins that dependencies raise (repository rule)."""


class SamovarError(Exception):
    """Base of every error the agent reports to the user; its message is safe to show after redaction."""


class ConfigurationError(SamovarError):
    """Settings are missing or invalid."""


class QueryRejected(SamovarError):
    """The SQL guard refused a statement; the message says why and how to fix it."""


class QueryFailed(SamovarError):
    """DuckDB failed to execute an accepted statement."""


class QueryTimeout(SamovarError):
    """A statement ran longer than the time limit and was interrupted."""


class LockdownError(SamovarError):
    """A resolved DuckDB setting differs from the required lockdown (phone-home and isolation rule)."""


class NoDataYet(SamovarError):
    """The tenant has no published mapping yet."""


class AccessDenied(SamovarError):
    """The object storage refused the client's S3 key."""


class UpstreamError(SamovarError):
    """The platform API (the catalog) or the object storage answered with an error or unreadable content."""


class UnknownResult(SamovarError):
    """A query id is unknown or has expired from the result store."""


class ExtensionError(SamovarError):
    """An extension is missing, unknown for this platform, or failed its checksum."""
