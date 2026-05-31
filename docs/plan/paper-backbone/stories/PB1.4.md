# PB1.4 — `src/council/rapid.py`: RapidCouncil + tests

**Files to change:**
- `src/council/__init__.py` — new package, single comment line only
- `src/council/models.py` — `CouncilOutput` + `PersonaResponse` dataclasses
- `src/council/rapid.py` — `RapidCouncil`
- `tests/unit/council/__init__.py` — new test package, single comment line only
- `tests/unit/council/test_rapid_council.py` — new test file

**What to implement (`src/council/models.py`):**

```python
@dataclass(frozen=True)
class PersonaResponse:
    persona: str            # "QuantAnalyst" | "SpecGuardian" | "RiskManager" | "OptionsStrategist"
    model: str
    response: str           # raw text from model
    latency_ms: int
    timed_out: bool = False


@dataclass(frozen=True)
class CouncilOutput:
    actions: list[ApprovedAction]       # chairman-ranked, rank 1 = top pick
    chairman_rationale: str
    dissenting_notes: str | None
    stage1_responses: list[PersonaResponse]
    latency_ms: int                     # total wall-clock time
```

**What to implement (`src/council/rapid.py`):**

Council composition:

| Persona | Model | API endpoint |
|---|---|---|
| QuantAnalyst | `deepseek/deepseek-r1-0528` | OpenRouter |
| SpecGuardian | `claude-haiku-4-5-20251001` | Anthropic direct |
| RiskManager | `openai/o3-mini` | OpenRouter |
| OptionsStrategist | `x-ai/grok-4-fast` | xAI direct (`https://api.x.ai/v1`) |
| Chairman | `claude-sonnet-4-6` | Anthropic direct |

```python
class RapidCouncil:
    def __init__(
        self,
        spec_doc: str,          # strategy spec text passed to SpecGuardian
        openrouter_api_key: str,
        anthropic_api_key: str,
        xai_api_key: str,
    ) -> None: ...

    async def consult(
        self,
        event: SignalEvent,
        context: str,           # strategy.describe_context() output
    ) -> CouncilOutput:
        """
        Stage 1: fire all four persona calls in parallel via asyncio.gather.
                 Each call: asyncio.wait_for(..., timeout=25.0).
                 Timed-out persona → PersonaResponse(timed_out=True, response="").
        Stage 2: pass all Stage 1 responses to Chairman with timeout=15.0.
                 Chairman produces ranked ApprovedAction list.
        Full timeout: if Chairman times out → raise CouncilTimeoutError.
        """
```

**Prompt construction** — inline in `rapid.py`, not a separate module at this stage:
- Each Stage 1 persona receives: the strategy context string + their persona framing.
- SpecGuardian additionally receives `spec_doc` and must output "COMPLIANT / NON-COMPLIANT"
  for each proposed action with the cited clause.
- Chairman receives all Stage 1 responses and produces a JSON array of `ApprovedAction`
  objects ranked by quality.

**API calls** — use `aiohttp.ClientSession` with `asyncio.wait_for`. All calls must have
explicit `Content-Type: application/json` headers and bearer token auth.

**Error handling** — `CouncilTimeoutError(BrokerError)` for full chairman timeout.
Individual Stage 1 timeouts do not raise — chairman proceeds with partial responses.

**Tests (`tests/unit/council/test_rapid_council.py`):**

All API calls must be mocked (no network). Use `unittest.mock.AsyncMock`.

- Happy path: all four Stage 1 calls resolve → chairman called with four responses.
- Stage 1 partial timeout: one persona times out → chairman called with 3 responses + 1
  `timed_out=True`; no exception raised.
- All Stage 1 calls return → chairman produces 2 `ApprovedAction` items → `CouncilOutput`
  has `len(actions) == 2`.
- SpecGuardian NON-COMPLIANT response → chairman still called; result in `dissenting_notes`.
- Chairman timeout → `CouncilTimeoutError` raised.
- `latency_ms` field is positive integer.

**Commit:** `feat(council): add RapidCouncil with parallel Stage 1 + chairman synthesis`

---

## Pre-baked Context

> Graph queries pre-run 2026-05-31. Skip "Before any code" graph calls — use these directly.

**`RapidCouncil`** — does NOT yet exist (zero results from graph). ✅ Safe to create.

**`ApprovedAction`** — defined in `src/strategy/protocol.py` (PB1.1).
Fields: `action_type: str`, `legs_to_close: list[str]`, `legs_to_open: list[LegSpec]`,
`rationale: str`, `council_rank: int`.

**`SignalEvent`** — `src/strategy/protocol.py`. Fields: `event_type: str`,
`severity: Literal["INFO","WARN","ACTION"]`, `description: str`, `payload: dict[str, Any]`.

**aiohttp pattern** — used in `src/client/upstox_market.py`. Pattern:
```python
async with aiohttp.ClientSession() as session:
    async with session.post(url, json=payload, headers=headers) as resp:
        resp.raise_for_status()
        data = await resp.json()
```

**`OPENROUTER_API_KEY`** — env var name confirmed in `.env.example`. Add to `src/config.py`
`Settings` as `openrouter_api_key: str | None = None` before implementing `RapidCouncil.__init__`.

**`BrokerError`** — `src/client/exceptions.py`. `CouncilTimeoutError` should inherit from it.
