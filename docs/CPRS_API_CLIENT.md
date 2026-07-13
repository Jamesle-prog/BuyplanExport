# CPRS API client (`po_extractor/cprs`)

A **complete, typed Python client** for the CPRS API, generated from
`po_extractor/cprs/CPRS_API.openapi.json` (currently **v1.6.8** — 98 endpoints,
29 schemas). It covers every endpoint, grouped by tag, with a dataclass for
every request/response model.

This is the *raw API surface*. The best-effort, buy-plan-specific helper
(`CprsClient` in `po_extractor/utils/cprs_client.py`) is unchanged and still
powers the GIII buy plan — it returns `None`/`[]` on failure so an export never
breaks. Use **this** client when you want the full API and explicit errors.

## Usage

```python
from po_extractor.cprs import CprsApiClient, CprsError, models

api = CprsApiClient("http://localhost:3100", api_key="…")   # x-api-key auth

# tag groups → methods
run = api.evaluation.evaluate(models.CreateOrderContextDto(
    clientId="…", channel="WHOLESALE", warehouseCode="UC"))
print(run.summary.confirmed, len(run.results))     # typed response

whs   = api.clients.get_warehouses("client-id")     # path param
runs  = api.evaluation.list(clientId="…", limit=20) # query params (None dropped)
xlsx  = api.export.download_excel("run-id")          # binary → bytes

# bearer auth
token = api.auth.login({"email": "…", "password": "…"})   # dict body is fine
api.set_token(token["access_token"])
me = api.auth.me()
```

### Request bodies: model **or** dict

Several DTOs are undocumented in the spec (empty server-side annotations), so
every body-taking method accepts a typed model **or** a plain dict. Models carry
undocumented fields via `extra=`:

```python
models.CreateOrderContextDto(clientId="c1", extra={"customField": 1}).to_dict()
# -> {"clientId": "c1", "customField": 1}
```

### Errors

Non-2xx responses and transport failures raise `CprsError(status, message,
body)`. `status == 0` means the server was unreachable.

## Tag groups

`auth · documents · clients · extraction · fragments · mapping · review ·
evaluation · warehouse_lookup · export · admin · search · audit · ai_assist ·
manual_images · washing_label · production_submission · health · version`

Access as `api.<group>.<method>(...)`; method names come from the spec's
`operationId` (e.g. `getWarehouses` → `get_warehouses`).

## Regenerating

`models.py` and `client.py` are **generated — do not edit by hand**. After
dropping in a newer spec:

```bash
cp <new-spec> po_extractor/cprs/CPRS_API.openapi.json
python scripts/gen_cprs_client.py
python -m pytest tests/test_cprs_api_client.py -q
```

The generator (`scripts/gen_cprs_client.py`) maps each schema → a dataclass and
each operation → a tag-grouped method (path/query params, JSON body, binary
responses, typed responses where the spec references a schema).
