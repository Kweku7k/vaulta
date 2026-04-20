# Vaulta API — Developer Documentation (v1)

Welcome to the **Vaulta API**. Vaulta provides programmable finance primitives — accounts, payments, quotes, FX rates, and transactions — through a simple REST API.

> **Base URL:** `https://api.vaulta.digital`
> **Dashboard:** `https://dashboard.vaulta.digital`
> **OpenAPI:** `https://api.vaulta.digital/openapi.json`

---

## Quick Start

1. **Obtain a JWT token** from the Vaulta Dashboard → *Developers → API keys*.
2. **Authenticate** all requests with the token as a Bearer header.
3. **Create additional API keys** programmatically via `POST /api/v1/create_api_key`.

```http
Authorization: Bearer <your_jwt_token>
```

---

## Authentication

All `/api/v1/*` endpoints require a valid JWT Bearer token in the `Authorization` header.

```bash
curl -H "Authorization: Bearer <your_jwt_token>" https://api.vaulta.digital/api/v1/accounts
```

Tokens are issued via the Vaulta Dashboard. Rotate or revoke them there at any time.

---

## Errors

Vaulta uses conventional HTTP status codes.

```json
{
  "detail": "Source account not found"
}
```

| Code | Meaning |
|---|---|
| `200 / 201` | Success |
| `400` | Bad request / validation error |
| `401` | Missing or invalid token |
| `403` | Forbidden (e.g. account not verified) |
| `404` | Resource not found |
| `422` | Unprocessable entity |
| `500` | Internal server error |

---

# REST Resources

## 1) API Keys

Manage programmatic access keys. All endpoints require JWT auth.

### Create API key

`POST /api/v1/create_api_key`

Generates a new key scoped to the authenticated user. Expires after **30 days**.

**Response** `200`

```json
{
  "api_key": "aBcD1234...",
  "expires_at": "2026-04-29T12:00:00Z"
}
```

---

### List API keys

`GET /api/v1/api_keys`

**Response** `200`

```json
{
  "api_keys": [
    {
      "api_key": "aBcD1234...",
      "expires_at": "2026-04-29T12:00:00Z",
      "active": true
    }
  ]
}
```

---

### Delete API key

`DELETE /api/v1/delete_api_key/{api_key}`

**Response** `204 No Content`

---

### Enable / disable API key

`POST /api/v1/toggle_api_key`

```json
{
  "api_key": "aBcD1234...",
  "active": false
}
```

**Response** `200`

```json
{
  "api_key": "aBcD1234...",
  "active": false
}
```

---

## 2) Accounts

Vaulta Accounts hold balances in a given currency.

### Create account

`POST /api/v1/create_account`

```json
{
  "name": "Acme Operating USD",
  "currency": "USD"
}
```

**Response** `201`

```json
{
  "id": "1",
  "name": "Acme Operating USD",
  "currency": "USD",
  "status": "ACTIVE",
  "balances": {},
  "metadata": null
}
```

---

### List accounts

`GET /api/v1/accounts`

Returns all **active** accounts for the authenticated user.

**Response** `200`

```json
[
  {
    "id": "1",
    "name": "Acme Operating USD",
    "currency": "USD",
    "status": "ACTIVE",
    "balances": {},
    "metadata": null
  }
]
```

---

### Update account

`PUT /api/v1/accounts/{account_id}`

```json
{
  "name": "Acme Treasury USD",
  "currency": "USD"
}
```

**Response** `200` — returns the updated account object.

---

### Delete account

`DELETE /api/v1/accounts/{account_id}`

Soft-deletes the account (`status → DELETED`). Returns remaining active accounts.

**Response** `204`

---

## 3) Payments

Outgoing transfers (e.g. USDC on-chain). Payments start as `pending` and require admin approval before execution.

### Create payment

`POST /api/v1/payments`

```json
{
  "source_account_id": "1",
  "amount": "2500.00",
  "currency": "USD",
  "destination": {
    "rail": "stablecoin",
    "network": "solana",
    "address": "6oK8...abc"
  },
  "description": "September contractor payout",
  "client_reference": "INV-9283"
}
```

**Response** `201`

```json
{
  "id": "pay_A1B2C3D4",
  "status": "pending",
  "amount": "2500.00",
  "currency": "USD",
  "fx": null,
  "fees": [{"type": "network", "amount": "0.12", "currency": "USD"}],
  "created_at": "2026-03-30T12:40:10Z"
}
```

**Payment statuses:** `pending` → `approved` / `rejected`

---

### Get payment

`GET /api/v1/payments/{payment_id}`

**Response** `200` — returns the payment object above.

---

### Get payment's linked transaction

`GET /api/v1/payments/{payment_id}/transaction`

Returns the transaction record created when the payment is approved.

**Response** `200`

```json
{
  "id": 42,
  "amount": 250000,
  "currency": "USD",
  "transaction_type": "payment",
  "provider": "stablecoin",
  "status": "completed",
  "reference": "INV-9283",
  "description": "September contractor payout",
  "created_at": "2026-03-30T12:45:00Z"
}
```

---

## 4) Transactions

### List transactions

`GET /api/v1/transactions`

Returns all transactions and pending payments for the authenticated user.

**Response** `200`

```json
{
  "transactions": [ "..." ],
  "payments": [ "..." ]
}
```

---

### Get transaction

`GET /api/v1/transactions/{transaction_id}`

**Response** `200`

```json
{
  "id": "42",
  "amount": 250000,
  "currency": "USD",
  "type": "payment",
  "provider": "stablecoin",
  "status": "completed",
  "reference": "INV-9283",
  "description": "September contractor payout",
  "created_at": "2026-03-30T12:45:00Z"
}
```

---

## 5) Quotes & FX

### Get a quote

`POST /api/v1/get_quote`

```json
{
  "pair": "USDC-GHS",
  "side": "sell",
  "amount_crypto": 1000.0

}
```

> Supported pairs: `USDC-GHS`, `GHS-USDC`, `USDC-USDT`. Provide either `amount_crypto` or `amount_fiat`.

**Response** `200`

```json
{
  "quote_id": "qt_...",
  "pair": "USDC-GHS",
  "side": "sell",
  "amount_crypto": "1000.00",
  "amount_fiat": "15500.00",
  "price": "15.50",
  "expires_at": "2026-03-30T12:45:00Z"
}
```

---

### List supported pairs

`GET /api/v1/pairs`

**Response** `200`

```json
{
  "markets": ["USDC-GHS", "GHS-USDC", "USDC-USDT"]
}
```

---

### List FX rates

`GET /api/v1/fx_rates`

**Response** `200`

```json
{
  "data": [
    {
      "id": "fx_A1B2C3D4",
      "pair": "USDC-GHS",
      "buy": "buy",
      "sell": "sell",
      "buy_price": "15.40",
      "sell_price": "15.60"
    }
  ],
  "count": 1
}
```

---

## 6) Onboarding (KYC)

New businesses go through a KYC onboarding flow before their account is activated. **No authentication is required** for these endpoints.

### Start onboarding session

`GET /api/v1/onboarding/start`

Creates a new KYC session. Returns a `reference_id` used for all subsequent steps.

**Response** `200`

```json
{
  "reference_id": "kyc_abc123def456"
}
```

---

### Start UBO verification

`POST /api/v1/onboarding/ubo/start`

Register a UBO (Ultimate Beneficial Owner) and initiate their Persona identity check.

```json
{
  "reference_id": "kyc_abc123def456",
  "full_name": "Jane Doe",
  "email": "jane@company.com",
  "phone": "+233201234567",
  "ownership_percentage": 51.0
}
```

**Response** `200` — returns a Persona inquiry URL to redirect the UBO to.

---

### Confirm UBO Persona verification

`POST /api/v1/onboarding/ubo/verify`

Call this after the UBO completes their Persona flow.

```json
{
  "ubo_reference_id": "ubo_xyz789",
  "inquiry_id": "inq_abc123"
}
```

---

### Get UBO verification status

`GET /api/v1/onboarding/ubo/status/{reference_id}`

Returns all UBOs and their verification statuses for a KYC session.

---

### Get onboarding status

`GET /api/v1/onboarding/status/{reference_id}`

Returns the current status of the KYC session.

---

### Submit onboarding documents

`POST /api/v1/onboarding/complete`

Final step. All UBOs must be verified before submitting. Accepts `multipart/form-data`.

| Field | Type | Required |
|---|---|---|
| `email` | string | ✅ |
| `phone` | string | ✅ |
| `reference_id` | string | ✅ if no `inquiry_id` |
| `inquiry_id` | string | ✅ if no `reference_id` |
| `full_name` | string | No |
| `company_name` | string | No |
| `certificate_of_incorporation` | file | No |
| `memorandum_and_articles` | file | No |
| `ubos_schedule` | file | No |
| `company_profile` | file | No |
| `id_documents` | file | No |
| `company_address_proof` | file | No |
| `regulatory_information` | file | No |
| `source_of_funds` | file | No |

**Response** `200`

```json
{
  "message": "Documents submitted successfully — pending review",
  "reference_id": "kyc_abc123def456"
}
```

---

## 7) Onboarding (v2 Staged Flow)

The v2 onboarding flow is additive and does not replace v1. Use this flow for staged saves and resume-by-KYC-ID.

### Get frontend Firebase config

`GET /api/v2/onboarding/firebase-config`

Returns only public Firebase web config fields for frontend initialization.

### Resume onboarding (returning users)

`GET /api/v2/onboarding/resume/{reference_id}`

Returns full current state of an onboarding session so the frontend can pre-fill all form stages.

**Response** `200`

```json
{
  "reference_id": "kyc_abc123def456",
  "status": "pending",
  "basic_info": {
    "full_name": "Jane Doe",
    "email": "jane@company.com",
    "company_name": "Acme Ltd",
    "phone": "+233201234567"
  },
  "ubos": [
    {
      "ubo_reference_id": "ubo_xyz789",
      "full_name": "John Owner",
      "email": "john@company.com",
      "phone": "+233200000000",
      "ownership_percentage": 60,
      "status": "pending",
      "verified_at": null
    }
  ],
  "ubo_count": 1,
  "ubo_verified_count": 0,
  "documents": {
    "certificate_of_incorporation": "https://storage.googleapis.com/.../coi.pdf"
  },
  "documents_uploaded": 1,
  "verified_at": null
}
```

### Save basic info (stage 1)

`POST /api/v2/onboarding/basic-info`

If `reference_id` is omitted, backend auto-generates a new KYC ID and emails it to the user.

```json
{
  "full_name": "Jane Doe",
  "email": "jane@company.com",
  "company_name": "Acme Ltd",
  "phone": "+233201234567"
}
```

### Save UBO details (stage 2A)

`POST /api/v2/onboarding/ubo`

```json
{
  "reference_id": "kyc_abc123def456",
  "full_name": "John Owner",
  "email": "john@company.com",
  "phone": "+233200000000",
  "ownership_percentage": 60
}
```

### Verify UBO (stage 2B)

`POST /api/v2/onboarding/ubo/verify`

```json
{
  "ubo_reference_id": "ubo_xyz789",
  "inquiry_id": "inq_abc123"
}
```

### Save document URLs (stage 3)

`POST /api/v2/onboarding/documents`

Save one document URL per call. Upload the file to Firebase first, then send the resulting URL. Call this endpoint once for each document.

```json
{
  "reference_id": "kyc_abc123def456",
  "field": "certificate_of_incorporation",
  "url": "https://storage.googleapis.com/.../coi.pdf"
}
```

Allowed `field` values:
- `certificate_of_incorporation`
- `memorandum_and_articles`
- `ubos_schedule`
- `company_profile`
- `id_documents`
- `company_address_proof`
- `regulatory_information`
- `source_of_funds`

**Response:**
```json
{
  "message": "Document saved",
  "reference_id": "kyc_abc123def456",
  "saved_field": "certificate_of_incorporation",
  "documents_uploaded": 1,
  "documents": {
    "certificate_of_incorporation": "https://storage.googleapis.com/.../coi.pdf"
  }
}
```

### Submit final onboarding

`POST /api/v2/onboarding/submit`

```json
{
  "reference_id": "kyc_abc123def456"
}
```

On submit:
- User receives confirmation email containing KYC ID.
- Compliance recipient receives form summary plus binary file attachments (downloaded server-side from stored URLs).
- Temporary compliance recipient for v2: `mr.adumatta@gmail.com`.

---

## Changelog

| Date | Notes |
|---|---|
| 2026-03-30 | Rewrote docs to match live implementation — OTP auth flow, correct endpoint paths, onboarding, FX rates, API key management |
| 2025-09-19 | Initial public draft |
