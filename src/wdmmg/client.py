"""WDMMG API Client.

This module provides a production-ready client for interacting with the WDMMG API.

Example:
    >>> from wdmmg import WdmmgClient
    >>> with WdmmgClient(api_key="your-api-key") as client:
    ...     accounts = client.get_accounts()
    ...     transactions = client.get_transactions(start_date="2024-01-01")
"""

import logging
import os
from datetime import date
from typing import Any, Iterator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions
# =============================================================================


class WdmmgError(Exception):
    """Base exception for all WDMMG client errors."""


class WdmmgAuthError(WdmmgError):
    """Raised when authentication fails.

    This occurs when:
    - The API key is invalid or expired (HTTP 401)
    - The API key lacks permissions for the requested resource (HTTP 403)
    """


class WdmmgRateLimitError(WdmmgError):
    """Raised when the API rate limit is exceeded (HTTP 429).

    Attributes:
        retry_after: Number of seconds to wait before retrying, if provided
            by the API. May be None if the header was not present.
    """

    def __init__(self, retry_after: int | None = None):
        self.retry_after = retry_after
        message = (
            f"Rate limit exceeded. Retry after {retry_after} seconds."
            if retry_after
            else "Rate limit exceeded."
        )
        super().__init__(message)


class WdmmgAPIError(WdmmgError):
    """Raised when the API returns an error response (4xx/5xx).

    Attributes:
        status_code: The HTTP status code returned by the API.
        response_body: The raw response body from the API.
    """

    def __init__(self, status_code: int, response_body: str):
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(f"API error {status_code}: {response_body}")


# =============================================================================
# Client
# =============================================================================


class WdmmgClient:
    """Client for the WDMMG API.

    Args:
        api_key: Your WDMMG API key. If not provided, reads from the
            WDMMG_API_KEY environment variable.
        base_url: Override the default API base URL. Useful for testing
            or connecting to staging environments. Can also be set via
            WDMMG_BASE_URL environment variable.
        timeout: Request timeout in seconds. Can be a single float (used for
            both connect and read) or a tuple of (connect_timeout, read_timeout).
            Defaults to (5, 30) meaning 5s to connect, 30s to read.
        max_retries: Maximum number of retries for failed requests. Retries
            use exponential backoff and only apply to idempotent methods
            and specific status codes (429, 500, 502, 503, 504).

    Raises:
        ValueError: If no API key is provided and WDMMG_API_KEY is not set.

    Example:
        Using as a context manager (recommended)::

            with WdmmgClient(api_key="your-key") as client:
                accounts = client.get_accounts()

        Using environment variables::

            # Set WDMMG_API_KEY in your environment
            client = WdmmgClient()
            try:
                transactions = client.get_transactions()
            finally:
                client.close()

        Iterating over large result sets efficiently::

            with WdmmgClient() as client:
                for txn in client.iter_transactions(start_date="2024-01-01"):
                    process(txn)
    """

    DEFAULT_BASE_URL = "https://wdmmg.io/api/v1"
    DEFAULT_TIMEOUT: tuple[float, float] = (5.0, 30.0)
    DEFAULT_MAX_RETRIES = 3

    def __init__(
            self,
            api_key: str | None = None,
            *,
            base_url: str | None = None,
            timeout: tuple[float, float] | float = DEFAULT_TIMEOUT,
            max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        # Resolve API key from argument or environment
        self._api_key = api_key or os.environ.get("WDMMG_API_KEY")
        if not self._api_key:
            raise ValueError(
                "API key is required. Pass api_key argument or set WDMMG_API_KEY environment variable."
            )

        # Resolve base URL from argument or environment
        resolved_base_url = (
                base_url
                or os.environ.get("WDMMG_BASE_URL")
                or self.DEFAULT_BASE_URL
        )
        self._base_url = resolved_base_url.rstrip("/")
        self._timeout = timeout

        # Set up session with connection pooling
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        })

        # Configure retry strategy with exponential backoff
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=0.5,  # 0.5, 1.0, 2.0 seconds between retries
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
            raise_on_status=False,  # We handle status codes ourselves
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

        logger.debug(
            "Initialized WdmmgClient with base_url=%s, timeout=%s, max_retries=%d",
            self._base_url,
            self._timeout,
            max_retries,
        )

    def close(self) -> None:
        """Close the underlying HTTP session and release resources.

        This method should be called when you're done using the client
        to ensure connections are properly closed. Using the client as
        a context manager handles this automatically.
        """
        self._session.close()
        logger.debug("Closed WdmmgClient session")

    def __enter__(self) -> "WdmmgClient":
        """Enter the context manager."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the context manager and close the session."""
        self.close()

    def get_accounts(self) -> list[dict[str, Any]]:
        """Fetch all accounts associated with the API key.

        Returns:
            A list of account dictionaries
        Raises:
            WdmmgAuthError: If the API key is invalid or expired.
            WdmmgAPIError: If the API returns an error.
            WdmmgError: If the request fails due to network issues.

        Example:
            >>> accounts = client.get_accounts()
            >>> for account in accounts:
            ...     print(f"{account['name']}: {account['id']}")
        """
        logger.info("Fetching accounts")
        data = self._request("GET", "accounts")
        accounts = data if isinstance(data, list) else data.get("accounts", [])
        logger.info("Fetched %d accounts", len(accounts))
        return accounts

    def get_transactions(
            self,
            start_date: str | date | None = None,
            end_date: str | date | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all transactions, handling pagination automatically.

        This method loads all matching transactions into memory. For large
        result sets, consider using iter_transactions() instead.

        Args:
            start_date: Start of date range (inclusive). Accepts an ISO format
                string (YYYY-MM-DD) or a datetime.date object. If None, no
                lower bound is applied.
            end_date: End of date range (inclusive). Accepts an ISO format
                string (YYYY-MM-DD) or a datetime.date object. If None, no
                upper bound is applied.

        Returns:
            A list of transaction dictionaries.

        Raises:
            WdmmgAuthError: If the API key is invalid or expired.
            WdmmgAPIError: If the API returns an error.
            WdmmgError: If the request fails due to network issues.
            ValueError: If date format is invalid.

        Example:
            >>> from datetime import date
            >>> transactions = client.get_transactions(
            ...     start_date=date(2024, 1, 1),
            ...     end_date="2024-12-31"
            ... )
            >>> print(f"Found {len(transactions)} transactions")
        """
        return list(self.iter_transactions(start_date, end_date))

    def iter_transactions(
            self,
            start_date: str | date | None = None,
            end_date: str | date | None = None,
            page_size: int = 100,
    ) -> Iterator[dict[str, Any]]:
        """Iterate over transactions, yielding one at a time.

        This is more memory-efficient than get_transactions() for large
        result sets, as it only keeps one page in memory at a time.

        Args:
            start_date: Start of date range (inclusive). Accepts an ISO format
                string (YYYY-MM-DD) or a datetime.date object. If None, no
                lower bound is applied.
            end_date: End of date range (inclusive). Accepts an ISO format
                string (YYYY-MM-DD) or a datetime.date object. If None, no
                upper bound is applied.
            page_size: Number of transactions to fetch per API call.
                Defaults to 100. Larger values mean fewer API calls but
                more memory usage per page.

        Yields:
            Transaction dictionaries one at a time.

        Raises:
            WdmmgAuthError: If the API key is invalid or expired.
            WdmmgAPIError: If the API returns an error.
            WdmmgError: If the request fails due to network issues.
            ValueError: If date format is invalid.

        Example:
            >>> for txn in client.iter_transactions(start_date="2024-01-01"):
            ...     if txn["amount"] > 1000:
            ...         print(f"Large transaction: {txn['description']}")
        """
        logger.info(
            "Fetching transactions (start_date=%s, end_date=%s)",
            start_date,
            end_date,
        )

        # Validate and normalize dates upfront
        normalized_start = self._normalize_date(start_date)
        normalized_end = self._normalize_date(end_date)

        offset = 0
        has_more = True
        total_fetched = 0

        while has_more:
            params: dict[str, Any] = {"offset": offset, "limit": page_size}
            if normalized_start is not None:
                params["start_date"] = normalized_start
            if normalized_end is not None:
                params["end_date"] = normalized_end

            data = self._request("GET", "transactions", params=params)

            transactions = data.get("transactions", [])
            for txn in transactions:
                yield txn
                total_fetched += 1

            has_more = data.get("has_more", False)
            offset += page_size

            logger.debug(
                "Fetched page: offset=%d, count=%d, has_more=%s",
                offset - page_size,
                len(transactions),
                has_more,
            )

        logger.info("Fetched %d total transactions", total_fetched)

    @staticmethod
    def _normalize_date(value: str | date | None) -> str | None:
        """Normalize a date value to ISO format string.

        Args:
            value: A date object, ISO format string (YYYY-MM-DD), or None.

        Returns:
            ISO format date string, or None if input is None.

        Raises:
            ValueError: If the string is not in valid ISO format.
            TypeError: If the value is not a string, date, or None.
        """
        if value is None:
            return None
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, str):
            # Validate the string format by parsing it
            try:
                date.fromisoformat(value)
            except ValueError as e:
                raise ValueError(
                    f"Invalid date format: '{value}'. Expected ISO format (YYYY-MM-DD)."
                ) from e
            return value
        raise TypeError(
            f"Expected str, date, or None, got {type(value).__name__}"
        )

    def _request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """Make an HTTP request to the API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            endpoint: API endpoint path (without base URL)
            **kwargs: Additional arguments passed to requests.Session.request()

        Returns:
            Parsed JSON response as a dictionary.

        Raises:
            WdmmgAuthError: If authentication fails (401/403)
            WdmmgRateLimitError: If rate limit is exceeded (429)
            WdmmgAPIError: If the API returns any other error (4xx/5xx)
            WdmmgError: If the request fails due to network issues
        """
        url = f"{self._base_url}/{endpoint.lstrip('/')}"
        kwargs.setdefault("timeout", self._timeout)

        logger.debug("Request: %s %s params=%s", method, url, kwargs.get("params"))

        try:
            response = self._session.request(method, url, **kwargs)
        except requests.exceptions.Timeout as e:
            logger.error("Request timed out: %s %s", method, url)
            raise WdmmgError(f"Request timed out: {e}") from e
        except requests.exceptions.ConnectionError as e:
            logger.error("Connection error: %s %s - %s", method, url, e)
            raise WdmmgError(f"Connection failed: {e}") from e
        except requests.exceptions.RequestException as e:
            logger.error("Request failed: %s %s - %s", method, url, e)
            raise WdmmgError(f"Request failed: {e}") from e

        logger.debug("Response: %d (%d bytes)", response.status_code, len(response.content))

        # Handle error responses
        if response.status_code == 401:
            logger.warning("Authentication failed: invalid API key")
            raise WdmmgAuthError("Invalid API key")
        if response.status_code == 403:
            logger.warning("Authentication failed: access forbidden")
            raise WdmmgAuthError("Access forbidden")
        if response.status_code == 429:
            retry_after_header = response.headers.get("Retry-After")
            retry_after = int(retry_after_header) if retry_after_header else None
            logger.warning("Rate limit exceeded. Retry-After: %s", retry_after)
            raise WdmmgRateLimitError(retry_after)
        if response.status_code >= 400:
            logger.error("API error %d: %s", response.status_code, response.text[:500])
            raise WdmmgAPIError(response.status_code, response.text)

        return response.json()
