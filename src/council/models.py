from dataclasses import dataclass

from src.strategy.protocol import ApprovedAction


@dataclass(frozen=True)
class PersonaResponse:
    """Response from an individual council persona."""

    persona: str  # "QuantAnalyst" | "SpecGuardian" | "RiskManager" | "OptionsStrategist"
    model: str
    response: str  # raw text from model
    latency_ms: int
    timed_out: bool = False


@dataclass(frozen=True)
class CouncilOutput:
    """Consolidated output from the RapidCouncil consult."""

    actions: list[ApprovedAction]  # chairman-ranked, rank 1 = top pick
    chairman_rationale: str
    dissenting_notes: str | None
    stage1_responses: list[PersonaResponse]
    latency_ms: int  # total wall-clock time
