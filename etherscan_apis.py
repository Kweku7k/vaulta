import re
from typing import Any, Dict, List

import httpx
from fastapi import HTTPException


ETHERSCAN_BASE_URL = "https://api.etherscan.io/v2/api"
NO_TRANSACTIONS_MESSAGE = "No transactions found"

ETHERSCAN_ACTIONS = {
    "normal": "txlist",
    "internal": "txlistinternal",
    "erc20": "tokentx",
    "erc721": "tokennfttx",
    "erc1155": "token1155tx",
}

EVM_ADDRESS_PATTERN = re.compile(r"^0x[a-fA-F0-9]{40}$")


def validate_evm_address(address: str) -> str:
    if not EVM_ADDRESS_PATTERN.fullmatch(address):
        raise HTTPException(status_code=400, detail="Invalid EVM address")
    return address


async def _fetch_etherscan_action(
    client: httpx.AsyncClient,
    api_key: str,
    action: str,
    address: str,
    chainid: str,
    page: int,
    offset: int,
    startblock: int,
    endblock: int,
    sort: str,
) -> List[Dict[str, Any]]:
    try:
        response = await client.get(
            ETHERSCAN_BASE_URL,
            params={
                "apikey": api_key,
                "chainid": chainid,
                "module": "account",
                "action": action,
                "address": address,
                "startblock": startblock,
                "endblock": endblock,
                "page": page,
                "offset": offset,
                "sort": sort,
            },
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Etherscan request failed") from exc

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Etherscan request failed")

    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Invalid Etherscan response") from exc
    status = str(payload.get("status", ""))
    message = str(payload.get("message", ""))
    result = payload.get("result", [])

    if status == "1" and isinstance(result, list):
        return result

    if status == "0" and message == NO_TRANSACTIONS_MESSAGE:
        return []

    detail = result if isinstance(result, str) and result else message or "Etherscan request failed"
    raise HTTPException(status_code=502, detail=detail)


def _normalize_etherscan_transaction(source_type: str, item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "source_type": source_type,
        "hash": item.get("hash"),
        "block_number": item.get("blockNumber"),
        "timestamp": item.get("timeStamp"),
        "from": item.get("from"),
        "to": item.get("to"),
        "value": item.get("value"),
        "contract_address": item.get("contractAddress"),
        "token_name": item.get("tokenName"),
        "token_symbol": item.get("tokenSymbol"),
        "token_id": item.get("tokenID") or item.get("tokenId"),
        "is_error": item.get("isError"),
        "raw": item,
    }


def _sort_key(item: Dict[str, Any]) -> int:
    try:
        return int(item.get("timestamp") or 0)
    except (TypeError, ValueError):
        return 0


async def get_etherscan_transactions(
    api_key: str,
    address: str,
    chainid: str = "1",
    page: int = 1,
    offset: int = 100,
    startblock: int = 0,
    endblock: int = 999999999,
    sort: str = "desc",
) -> Dict[str, Any]:
    validate_evm_address(address)

    async with httpx.AsyncClient(timeout=30.0) as client:
        grouped = {}
        for source_type, action in ETHERSCAN_ACTIONS.items():
            grouped[source_type] = await _fetch_etherscan_action(
                client=client,
                api_key=api_key,
                action=action,
                address=address,
                chainid=chainid,
                page=page,
                offset=offset,
                startblock=startblock,
                endblock=endblock,
                sort=sort,
            )

    transactions = [
        _normalize_etherscan_transaction(source_type, item)
        for source_type, items in grouped.items()
        for item in items
    ]
    transactions.sort(key=_sort_key, reverse=sort == "desc")

    return {
        "address": address,
        "chainid": chainid,
        "page": page,
        "offset": offset,
        "grouped": grouped,
        "transactions": transactions,
    }
