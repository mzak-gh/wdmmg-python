"""WDMMG API Python Client.

A production-ready client for interacting with the WDMMG API.

Example:
    >>> from wdmmg import WdmmgClient
    >>> with WdmmgClient(api_key="your-api-key") as client:
    ...     accounts = client.get_accounts()
    ...     for txn in client.iter_transactions(start_date="2024-01-01"):
    ...         print(txn)

Exceptions:
    All exceptions inherit from WdmmgError for easy catching::

        >>> from wdmmg import WdmmgClient, WdmmgError, WdmmgAuthError
        >>> try:
        ...     client = WdmmgClient(api_key="invalid")
        ...     client.get_accounts()
        ... except WdmmgAuthError:
        ...     print("Bad API key!")
        ... except WdmmgError as e:
        ...     print(f"API error: {e}")
"""

from .client import (
    WdmmgAPIError,
    WdmmgAuthError,
    WdmmgClient,
    WdmmgError,
    WdmmgRateLimitError,
)

__all__ = [
    "WdmmgClient",
    "WdmmgError",
    "WdmmgAuthError",
    "WdmmgRateLimitError",
    "WdmmgAPIError",
]
__version__ = "0.1.0"
