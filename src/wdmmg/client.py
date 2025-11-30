import requests
from typing import Optional
from datetime import date


class WdmmgClient:
    API_BASE_URL = "https://wdmmg.io/api/v1"

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._headers = {"Authorization": f"Bearer {api_key}"}

    def get_accounts(self):
        url = f"{self.API_BASE_URL}/accounts"
        response = requests.get(url, headers=self._headers)
        response.raise_for_status()
        return response.json()

    def get_transactions(
        self,
        start_date: Optional[str | date] = None,
        end_date: Optional[str | date] = None,
    ):
        url = f"{self.API_BASE_URL}/transactions"
        transactions = []
        offset = 0
        limit = 100
        has_more = True

        while has_more:
            params = {"offset": offset, "limit": limit}
            if start_date is not None:
                params["start_date"] = start_date
            if end_date is not None:
                params["end_date"] = end_date

            response = requests.get(url, params=params, headers=self._headers)
            response.raise_for_status()
            response = response.json()

            transactions.extend(response["transactions"])
            has_more = response["has_more"]

            offset += limit

        return transactions

