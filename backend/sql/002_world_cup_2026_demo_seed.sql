SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    DECLARE @sourceReferenceId int;
    DECLARE @tournamentId int;
    DECLARE @auroraTeamId int;
    DECLARE @borealisTeamId int;
    DECLARE @cinderTeamId int;
    DECLARE @driftTeamId int;
    DECLARE @venueId int;
    DECLARE @kickoffUtc datetimeoffset(0) =
        TODATETIMEOFFSET('2026-06-01T16:00:00', '+00:00');

    SELECT @sourceReferenceId = SourceReferenceId
    FROM wc2026.SourceReference
    WHERE Publisher = N'Synthetic demo data'
        AND Title = N'Synthetic World Cup 2026 fixture - not official FIFA data';

    IF @sourceReferenceId IS NULL
    BEGIN
        INSERT INTO wc2026.SourceReference (
            Publisher,
            Title,
            SourceUrl,
            RetrievedAt
        )
        VALUES (
            N'Synthetic demo data',
            N'Synthetic World Cup 2026 fixture - not official FIFA data',
            N'https://example.invalid/world-cup-2026-demo',
            TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')
        );
        SET @sourceReferenceId = CONVERT(int, SCOPE_IDENTITY());
    END;

    SELECT @tournamentId = TournamentId
    FROM wc2026.Tournament
    WHERE OfficialName = N'World Cup 2026 - SYNTHETIC DEMO ONLY'
        AND EditionYear = 2026;

    IF @tournamentId IS NULL
    BEGIN
        INSERT INTO wc2026.Tournament (
            OfficialName,
            EditionYear,
            StartDate,
            EndDate,
            SourceReferenceId
        )
        VALUES (
            N'World Cup 2026 - SYNTHETIC DEMO ONLY',
            2026,
            '2026-06-01',
            '2026-06-30',
            @sourceReferenceId
        );
        SET @tournamentId = CONVERT(int, SCOPE_IDENTITY());
    END;

    IF NOT EXISTS (
        SELECT 1 FROM wc2026.TournamentGroup
        WHERE TournamentId = @tournamentId AND GroupCode = N'DEMO-A'
    )
        INSERT INTO wc2026.TournamentGroup (
            TournamentId, GroupCode, SourceReferenceId
        )
        VALUES (@tournamentId, N'DEMO-A', @sourceReferenceId);

    IF NOT EXISTS (SELECT 1 FROM wc2026.Team WHERE OfficialName = N'Demo Aurora FC')
        INSERT INTO wc2026.Team (OfficialName, SourceReferenceId)
        VALUES (N'Demo Aurora FC', @sourceReferenceId);
    IF NOT EXISTS (SELECT 1 FROM wc2026.Team WHERE OfficialName = N'Demo Borealis FC')
        INSERT INTO wc2026.Team (OfficialName, SourceReferenceId)
        VALUES (N'Demo Borealis FC', @sourceReferenceId);
    IF NOT EXISTS (SELECT 1 FROM wc2026.Team WHERE OfficialName = N'Demo Cinder FC')
        INSERT INTO wc2026.Team (OfficialName, SourceReferenceId)
        VALUES (N'Demo Cinder FC', @sourceReferenceId);
    IF NOT EXISTS (SELECT 1 FROM wc2026.Team WHERE OfficialName = N'Demo Drift FC')
        INSERT INTO wc2026.Team (OfficialName, SourceReferenceId)
        VALUES (N'Demo Drift FC', @sourceReferenceId);

    SELECT @auroraTeamId = TeamId FROM wc2026.Team WHERE OfficialName = N'Demo Aurora FC';
    SELECT @borealisTeamId = TeamId FROM wc2026.Team WHERE OfficialName = N'Demo Borealis FC';
    SELECT @cinderTeamId = TeamId FROM wc2026.Team WHERE OfficialName = N'Demo Cinder FC';
    SELECT @driftTeamId = TeamId FROM wc2026.Team WHERE OfficialName = N'Demo Drift FC';

    IF NOT EXISTS (
        SELECT 1 FROM wc2026.TournamentTeam
        WHERE TournamentId = @tournamentId AND TeamId = @auroraTeamId
    )
        INSERT INTO wc2026.TournamentTeam
            (TournamentId, TeamId, GroupCode, SourceReferenceId)
        VALUES (@tournamentId, @auroraTeamId, N'DEMO-A', @sourceReferenceId);
    IF NOT EXISTS (
        SELECT 1 FROM wc2026.TournamentTeam
        WHERE TournamentId = @tournamentId AND TeamId = @borealisTeamId
    )
        INSERT INTO wc2026.TournamentTeam
            (TournamentId, TeamId, GroupCode, SourceReferenceId)
        VALUES (@tournamentId, @borealisTeamId, N'DEMO-A', @sourceReferenceId);
    IF NOT EXISTS (
        SELECT 1 FROM wc2026.TournamentTeam
        WHERE TournamentId = @tournamentId AND TeamId = @cinderTeamId
    )
        INSERT INTO wc2026.TournamentTeam
            (TournamentId, TeamId, GroupCode, SourceReferenceId)
        VALUES (@tournamentId, @cinderTeamId, N'DEMO-A', @sourceReferenceId);
    IF NOT EXISTS (
        SELECT 1 FROM wc2026.TournamentTeam
        WHERE TournamentId = @tournamentId AND TeamId = @driftTeamId
    )
        INSERT INTO wc2026.TournamentTeam
            (TournamentId, TeamId, GroupCode, SourceReferenceId)
        VALUES (@tournamentId, @driftTeamId, N'DEMO-A', @sourceReferenceId);

    SELECT @venueId = VenueId
    FROM wc2026.Venue
    WHERE OfficialName = N'DEMO Sample Stadium'
        AND City = N'Demo City';

    IF @venueId IS NULL
    BEGIN
        INSERT INTO wc2026.Venue (
            OfficialName, City, Country, TimeZoneId, SourceReferenceId
        )
        VALUES (
            N'DEMO Sample Stadium',
            N'Demo City',
            N'Demo Country',
            N'UTC',
            @sourceReferenceId
        );
        SET @venueId = CONVERT(int, SCOPE_IDENTITY());
    END;

    IF NOT EXISTS (
        SELECT 1 FROM wc2026.TournamentMatch
        WHERE TournamentId = @tournamentId
            AND StageName = N'Demo Group Stage'
            AND HomeTeamId = @auroraTeamId
            AND AwayTeamId = @borealisTeamId
            AND KickoffUtc = @kickoffUtc
    )
        INSERT INTO wc2026.TournamentMatch (
            TournamentId,
            StageName,
            GroupCode,
            VenueId,
            HomeTeamId,
            AwayTeamId,
            KickoffUtc,
            KickoffLocal,
            MatchStatus,
            RegulationHomeScore,
            RegulationAwayScore,
            SourceReferenceId
        )
        VALUES (
            @tournamentId,
            N'Demo Group Stage',
            N'DEMO-A',
            @venueId,
            @auroraTeamId,
            @borealisTeamId,
            @kickoffUtc,
            '2026-06-01T16:00:00',
            N'completed',
            2,
            1,
            @sourceReferenceId
        );

    IF NOT EXISTS (
        SELECT 1 FROM wc2026.OfficialGroupStanding
        WHERE TournamentId = @tournamentId AND GroupCode = N'DEMO-A'
            AND TeamId = @auroraTeamId
    )
        INSERT INTO wc2026.OfficialGroupStanding (
            TournamentId, GroupCode, TeamId, OfficialPosition, Played, Wins,
            Draws, Losses, GoalsFor, GoalsAgainst, GoalDifference, Points,
            QualificationStatus, SourceReferenceId
        )
        VALUES (
            @tournamentId, N'DEMO-A', @auroraTeamId, 1, 1, 1,
            0, 0, 2, 1, 1, 3, N'Demo qualifier', @sourceReferenceId
        );
    IF NOT EXISTS (
        SELECT 1 FROM wc2026.OfficialGroupStanding
        WHERE TournamentId = @tournamentId AND GroupCode = N'DEMO-A'
            AND TeamId = @borealisTeamId
    )
        INSERT INTO wc2026.OfficialGroupStanding (
            TournamentId, GroupCode, TeamId, OfficialPosition, Played, Wins,
            Draws, Losses, GoalsFor, GoalsAgainst, GoalDifference, Points,
            QualificationStatus, SourceReferenceId
        )
        VALUES (
            @tournamentId, N'DEMO-A', @borealisTeamId, 2, 1, 0,
            0, 1, 1, 2, -1, 0, N'Demo participant', @sourceReferenceId
        );
    IF NOT EXISTS (
        SELECT 1 FROM wc2026.OfficialGroupStanding
        WHERE TournamentId = @tournamentId AND GroupCode = N'DEMO-A'
            AND TeamId = @cinderTeamId
    )
        INSERT INTO wc2026.OfficialGroupStanding (
            TournamentId, GroupCode, TeamId, OfficialPosition, Played, Wins,
            Draws, Losses, GoalsFor, GoalsAgainst, GoalDifference, Points,
            QualificationStatus, SourceReferenceId
        )
        VALUES (
            @tournamentId, N'DEMO-A', @cinderTeamId, 3, 0, 0,
            0, 0, 0, 0, 0, 0, N'Demo participant', @sourceReferenceId
        );
    IF NOT EXISTS (
        SELECT 1 FROM wc2026.OfficialGroupStanding
        WHERE TournamentId = @tournamentId AND GroupCode = N'DEMO-A'
            AND TeamId = @driftTeamId
    )
        INSERT INTO wc2026.OfficialGroupStanding (
            TournamentId, GroupCode, TeamId, OfficialPosition, Played, Wins,
            Draws, Losses, GoalsFor, GoalsAgainst, GoalDifference, Points,
            QualificationStatus, SourceReferenceId
        )
        VALUES (
            @tournamentId, N'DEMO-A', @driftTeamId, 4, 0, 0,
            0, 0, 0, 0, 0, 0, N'Demo participant', @sourceReferenceId
        );

    IF NOT EXISTS (
        SELECT 1 FROM wc2026.OfficialFinalPlacement
        WHERE TournamentId = @tournamentId AND TeamId = @auroraTeamId
    )
        INSERT INTO wc2026.OfficialFinalPlacement
            (TournamentId, TeamId, PlacementLabel, PublishedRank, SourceReferenceId)
        VALUES (@tournamentId, @auroraTeamId, N'Demo champion', 1, @sourceReferenceId);
    IF NOT EXISTS (
        SELECT 1 FROM wc2026.OfficialFinalPlacement
        WHERE TournamentId = @tournamentId AND TeamId = @borealisTeamId
    )
        INSERT INTO wc2026.OfficialFinalPlacement
            (TournamentId, TeamId, PlacementLabel, PublishedRank, SourceReferenceId)
        VALUES (@tournamentId, @borealisTeamId, N'Demo finalist', 2, @sourceReferenceId);
    IF NOT EXISTS (
        SELECT 1 FROM wc2026.OfficialFinalPlacement
        WHERE TournamentId = @tournamentId AND TeamId = @cinderTeamId
    )
        INSERT INTO wc2026.OfficialFinalPlacement
            (TournamentId, TeamId, PlacementLabel, PublishedRank, SourceReferenceId)
        VALUES (@tournamentId, @cinderTeamId, N'Demo participant', 3, @sourceReferenceId);
    IF NOT EXISTS (
        SELECT 1 FROM wc2026.OfficialFinalPlacement
        WHERE TournamentId = @tournamentId AND TeamId = @driftTeamId
    )
        INSERT INTO wc2026.OfficialFinalPlacement
            (TournamentId, TeamId, PlacementLabel, PublishedRank, SourceReferenceId)
        VALUES (@tournamentId, @driftTeamId, N'Demo participant', 4, @sourceReferenceId);

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
