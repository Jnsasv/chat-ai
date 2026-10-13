from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from data_chat.data.catalog import AUTHORIZED_QUERIES

QueryId = Literal[
    "tournament_teams",
    "venues",
    "matches_for_team",
    "matches_at_venue",
    "matches_by_stage",
    "group_standings",
    "team_final_placement",
]


class IntentDecision(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    outcome: Literal["query", "clarification_required", "unsupported"]
    query_id: QueryId | None = None
    team_name: str | None = Field(default=None, min_length=1, max_length=128)
    venue_name: str | None = Field(default=None, min_length=1, max_length=200)
    group_code: str | None = Field(default=None, min_length=1, max_length=8)
    stage_name: str | None = Field(default=None, min_length=1, max_length=64)
    clarification_question: str | None = Field(
        default=None,
        min_length=1,
        max_length=300,
    )

    @model_validator(mode="after")
    def validate_decision_fields(self) -> "IntentDecision":
        parameter_values = {
            field_name: getattr(self, field_name)
            for field_name in ("team_name", "venue_name", "group_code", "stage_name")
            if getattr(self, field_name) is not None
        }

        if self.outcome == "query":
            if self.query_id is None:
                raise ValueError("A query decision requires an authorized query ID.")
            if self.clarification_question is not None:
                raise ValueError("A query decision cannot include a clarification.")
            AUTHORIZED_QUERIES[self.query_id].parameters.model_validate(
                parameter_values
            )
            return self

        if self.query_id is not None or parameter_values:
            raise ValueError("Non-query decisions cannot include query parameters.")
        if self.outcome == "clarification_required":
            if self.clarification_question is None:
                raise ValueError("A clarification decision requires a question.")
        elif self.clarification_question is not None:
            raise ValueError("Unsupported decisions cannot include a question.")
        return self

    def validated_query_parameters(self) -> dict[str, object]:
        if self.outcome != "query" or self.query_id is None:
            raise ValueError("Only query decisions have query parameters.")

        parameter_values = {
            field_name: getattr(self, field_name)
            for field_name in ("team_name", "venue_name", "group_code", "stage_name")
            if getattr(self, field_name) is not None
        }
        return AUTHORIZED_QUERIES[self.query_id].parameters.model_validate(
            parameter_values
        ).model_dump()
