# wdmmg-python

The official Python library for WDMMG API

## Installation

Install using uv:

```bash
uv pip install wdmmg
```

Or using pip:

```bash
pip install wdmmg
```

## Usage

First, initialize the client with your API key:

```python
from wdmmg import WdmmgClient

client = WdmmgClient(api_key="your-api-key-here")
```

### Get Accounts

Retrieve all accounts:

```python
accounts = client.get_accounts()
print(accounts)
```

### Get Transactions

Get all transactions:

```python
transactions = client.get_transactions()
```

Get transactions within a date range:

```python
from datetime import date

transactions = client.get_transactions(
    start_date="2024-01-01",
    end_date="2024-12-31"
)

# Or using date objects
transactions = client.get_transactions(
    start_date=date(2024, 1, 1),
    end_date=date(2024, 12, 31)
)
```

The `get_transactions` method automatically handles pagination and returns all matching transactions.

## Development

### Setup

This project uses `uv` for dependency management. To set up the development environment:

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create a virtual environment and install dependencies
uv venv
source .venv/bin/activate
uv pip install -e .
```

## Requirements

- Python 3.10 or higher

## License

See LICENSE file for details.
