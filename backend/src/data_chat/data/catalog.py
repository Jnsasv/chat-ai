from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Connection, text
from sqlalchemy.sql.elements import TextClause

MAX_QUERY_RESULT_ROWS = 1000


class NoParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TeamNameParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    team_name: str = Field(min_length=1, max_length=128)


class VenueNameParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    venue_name: str = Field(min_length=1, max_length=200)


class GroupCodeParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    group_code: str = Field(min_length=1, max_length=8)


class StageNameParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    stage_name: str = Field(min_length=1, max_length=64)


@dataclass(frozen=True)
class AuthorizedQuery:
    statement: TextClause
    parameters: type[BaseModel]


class UnsupportedQueryError(ValueError):
    def __init__(self) -> None:
        super().__init__("Query is not in the authorized catalog.")


AUTHORIZED_QUERIES: Mapping[str, AuthorizedQuery] = MappingProxyType(
    {
        "tournament_teams": AuthorizedQuery(
            statement=text(
                """
                SELECT TOP (:result_limit)
                    team.OfficialName AS team_name,
                    tournament_group.GroupCode AS group_code,
                    source.SourceUrl AS source_url,
                    source.Publisher AS source_publisher
                FROM wc2026.TournamentTeam AS tournament_team
                JOIN wc2026.Tournament AS tournament
                    ON tournament.TournamentId = tournament_team.TournamentId
                JOIN wc2026.Team AS team
                    ON team.TeamId = tournament_team.TeamId
                JOIN wc2026.TournamentGroup AS tournament_group
                    ON tournament_group.TournamentId = tournament_team.TournamentId
                    AND tournament_group.GroupCode = tournament_team.GroupCode
                JOIN wc2026.SourceReference AS source
                    ON source.SourceReferenceId = tournament_team.SourceReferenceId
                WHERE tournament.EditionYear = 2026
                ORDER BY tournament_group.GroupCode, team.OfficialName
                """
            ),
            parameters=NoParameters,
        ),
        "venues": AuthorizedQuery(
            statement=text(
                """
                SELECT TOP (:result_limit)
                    venue.OfficialName AS venue_name,
                    venue.City AS city,
                    venue.Country AS country,
                    venue.TimeZoneId AS time_zone_id,
                    source.SourceUrl AS source_url,
                    source.Publisher AS source_publisher
                FROM wc2026.Venue AS venue
                JOIN wc2026.SourceReference AS source
                    ON source.SourceReferenceId = venue.SourceReferenceId
                ORDER BY venue.Country, venue.City, venue.OfficialName
                """
            ),
            parameters=NoParameters,
        ),
        "matches_for_team": AuthorizedQuery(
            statement=text(
                """
                SELECT TOP (:result_limit)
                    tm.StageName AS stage_name,
                    tm.GroupCode AS group_code,
                    tm.KickoffUtc AS kickoff_utc,
                    tm.KickoffLocal AS kickoff_local,
                    venue.TimeZoneId AS time_zone_id,
                    venue.OfficialName AS venue_name,
                    venue.City AS venue_city,
                    venue.Country AS venue_country,
                    home_team.OfficialName AS home_team,
                    away_team.OfficialName AS away_team,
                    tm.MatchStatus AS match_status,
                    tm.RegulationHomeScore AS regulation_home_score,
                    tm.RegulationAwayScore AS regulation_away_score,
                    tm.ScoreAfterExtraTimeHome AS extra_time_home_score,
                    tm.ScoreAfterExtraTimeAway AS extra_time_away_score,
                    tm.PenaltyHomeScore AS penalty_home_score,
                    tm.PenaltyAwayScore AS penalty_away_score,
                    source.SourceUrl AS source_url,
                    source.Publisher AS source_publisher
                FROM wc2026.TournamentMatch AS tm
                JOIN wc2026.Tournament AS tournament
                    ON tournament.TournamentId = tm.TournamentId
                JOIN wc2026.Team AS home_team
                    ON home_team.TeamId = tm.HomeTeamId
                JOIN wc2026.Team AS away_team
                    ON away_team.TeamId = tm.AwayTeamId
                JOIN wc2026.Venue AS venue
                    ON venue.VenueId = tm.VenueId
                JOIN wc2026.SourceReference AS source
                    ON source.SourceReferenceId = tm.SourceReferenceId
                WHERE tournament.EditionYear = 2026
                    AND (
                        home_team.OfficialName = :team_name
                        OR away_team.OfficialName = :team_name
                    )
                ORDER BY tm.KickoffUtc
                """
            ),
            parameters=TeamNameParameters,
        ),
        "matches_at_venue": AuthorizedQuery(
            statement=text(
                """
                SELECT TOP (:result_limit)
                    tm.StageName AS stage_name,
                    tm.KickoffUtc AS kickoff_utc,
                    tm.KickoffLocal AS kickoff_local,
                    venue.TimeZoneId AS time_zone_id,
                    venue.OfficialName AS venue_name,
                    home_team.OfficialName AS home_team,
                    away_team.OfficialName AS away_team,
                    tm.MatchStatus AS match_status,
                    tm.RegulationHomeScore AS regulation_home_score,
                    tm.RegulationAwayScore AS regulation_away_score,
                    tm.ScoreAfterExtraTimeHome AS extra_time_home_score,
                    tm.ScoreAfterExtraTimeAway AS extra_time_away_score,
                    tm.PenaltyHomeScore AS penalty_home_score,
                    tm.PenaltyAwayScore AS penalty_away_score,
                    source.SourceUrl AS source_url,
                    source.Publisher AS source_publisher
                FROM wc2026.TournamentMatch AS tm
                JOIN wc2026.Tournament AS tournament
                    ON tournament.TournamentId = tm.TournamentId
                JOIN wc2026.Venue AS venue
                    ON venue.VenueId = tm.VenueId
                JOIN wc2026.Team AS home_team
                    ON home_team.TeamId = tm.HomeTeamId
                JOIN wc2026.Team AS away_team
                    ON away_team.TeamId = tm.AwayTeamId
                JOIN wc2026.SourceReference AS source
                    ON source.SourceReferenceId = tm.SourceReferenceId
                WHERE tournament.EditionYear = 2026
                    AND venue.OfficialName = :venue_name
                ORDER BY tm.KickoffUtc
                """
            ),
            parameters=VenueNameParameters,
        ),
        "matches_by_stage": AuthorizedQuery(
            statement=text(
                """
                SELECT TOP (:result_limit)
                    tm.StageName AS stage_name,
                    tm.GroupCode AS group_code,
                    tm.KickoffUtc AS kickoff_utc,
                    tm.KickoffLocal AS kickoff_local,
                    venue.TimeZoneId AS time_zone_id,
                    venue.OfficialName AS venue_name,
                    home_team.OfficialName AS home_team,
                    away_team.OfficialName AS away_team,
                    tm.MatchStatus AS match_status,
                    tm.RegulationHomeScore AS regulation_home_score,
                    tm.RegulationAwayScore AS regulation_away_score,
                    source.SourceUrl AS source_url,
                    source.Publisher AS source_publisher
                FROM wc2026.TournamentMatch AS tm
                JOIN wc2026.Tournament AS tournament
                    ON tournament.TournamentId = tm.TournamentId
                JOIN wc2026.Venue AS venue
                    ON venue.VenueId = tm.VenueId
                JOIN wc2026.Team AS home_team
                    ON home_team.TeamId = tm.HomeTeamId
                JOIN wc2026.Team AS away_team
                    ON away_team.TeamId = tm.AwayTeamId
                JOIN wc2026.SourceReference AS source
                    ON source.SourceReferenceId = tm.SourceReferenceId
                WHERE tournament.EditionYear = 2026
                    AND tm.StageName = :stage_name
                ORDER BY tm.KickoffUtc
                """
            ),
            parameters=StageNameParameters,
        ),
        "group_standings": AuthorizedQuery(
            statement=text(
                """
                SELECT TOP (:result_limit)
                    standings.GroupCode AS group_code,
                    standings.OfficialPosition AS official_position,
                    team.OfficialName AS team_name,
                    standings.Played AS played,
                    standings.Wins AS wins,
                    standings.Draws AS draws,
                    standings.Losses AS losses,
                    standings.GoalsFor AS goals_for,
                    standings.GoalsAgainst AS goals_against,
                    standings.GoalDifference AS goal_difference,
                    standings.Points AS points,
                    standings.QualificationStatus AS qualification_status,
                    source.SourceUrl AS source_url,
                    source.Publisher AS source_publisher
                FROM wc2026.OfficialGroupStanding AS standings
                JOIN wc2026.Tournament AS tournament
                    ON tournament.TournamentId = standings.TournamentId
                JOIN wc2026.Team AS team
                    ON team.TeamId = standings.TeamId
                JOIN wc2026.SourceReference AS source
                    ON source.SourceReferenceId = standings.SourceReferenceId
                WHERE tournament.EditionYear = 2026
                    AND standings.GroupCode = :group_code
                ORDER BY standings.OfficialPosition
                """
            ),
            parameters=GroupCodeParameters,
        ),
        "team_final_placement": AuthorizedQuery(
            statement=text(
                """
                SELECT TOP (:result_limit)
                    team.OfficialName AS team_name,
                    placement.PlacementLabel AS placement_label,
                    placement.PublishedRank AS published_rank,
                    source.SourceUrl AS source_url,
                    source.Publisher AS source_publisher
                FROM wc2026.OfficialFinalPlacement AS placement
                JOIN wc2026.Tournament AS tournament
                    ON tournament.TournamentId = placement.TournamentId
                JOIN wc2026.Team AS team
                    ON team.TeamId = placement.TeamId
                JOIN wc2026.SourceReference AS source
                    ON source.SourceReferenceId = placement.SourceReferenceId
                WHERE tournament.EditionYear = 2026
                    AND team.OfficialName = :team_name
                """
            ),
            parameters=TeamNameParameters,
        ),
    }
)


def execute_authorized_query(
    connection: Connection,
    query_id: str,
    raw_parameters: Mapping[str, object],
    *,
    max_rows: int,
) -> list[dict[str, object]]:
    if not 1 <= max_rows <= MAX_QUERY_RESULT_ROWS:
        raise ValueError(
            f"max_rows must be between 1 and {MAX_QUERY_RESULT_ROWS}."
        )

    try:
        query = AUTHORIZED_QUERIES[query_id]
    except KeyError as exc:
        raise UnsupportedQueryError() from exc

    validated_parameters = query.parameters.model_validate(raw_parameters)
    bound_parameters = validated_parameters.model_dump()
    bound_parameters["result_limit"] = max_rows
    result = connection.execute(query.statement, bound_parameters)
    return [dict(row) for row in result.mappings().all()]
