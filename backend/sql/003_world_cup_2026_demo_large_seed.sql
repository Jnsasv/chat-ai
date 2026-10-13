-- Large SYNTHETIC dataset for load and UI testing. Every value here is fictional
-- and generated deterministically; none of it is official FIFA information.
-- Requires 001 (schema) and 002 (demo seed) to have been applied first.
-- Adds: 11 groups (DEMO-B..DEMO-L) x 4 teams, 15 venues, 66 group matches,
-- 32 knockout matches (with extra time and penalty shootouts), standings for
-- the new groups, and final placements for every new team.
-- Group DEMO-A (from 002) is placed in the bracket as seeds 1-4 so that the
-- existing placements (champion, finalist, third, fourth) remain consistent.
SET NOCOUNT ON;
SET XACT_ABORT ON;

IF DB_NAME() <> N'WorldCup2026Demo'
    THROW 50001, N'This synthetic seed may only be applied to WorldCup2026Demo.', 1;

BEGIN TRY
    BEGIN TRANSACTION;

    DECLARE @sourceReferenceId int;
    DECLARE @tournamentId int;

    SELECT @sourceReferenceId = SourceReferenceId
    FROM wc2026.SourceReference
    WHERE Publisher = N'Synthetic demo data'
        AND Title = N'Synthetic World Cup 2026 fixture - not official FIFA data';

    SELECT @tournamentId = TournamentId
    FROM wc2026.Tournament
    WHERE OfficialName = N'World Cup 2026 - SYNTHETIC DEMO ONLY'
        AND EditionYear = 2026;

    IF @sourceReferenceId IS NULL OR @tournamentId IS NULL
        THROW 50002, N'Apply 002_world_cup_2026_demo_seed.sql before this script.', 1;

    IF (
        SELECT COUNT(*)
        FROM wc2026.Team
        WHERE OfficialName IN (
            N'Demo Aurora FC', N'Demo Borealis FC',
            N'Demo Cinder FC', N'Demo Drift FC'
        )
    ) <> 4
        THROW 50003, N'The four DEMO-A teams from 002 are required.', 1;

    IF EXISTS (SELECT 1 FROM wc2026.Team WHERE OfficialName = N'Demo Team B1')
    BEGIN
        PRINT N'The large synthetic dataset is already loaded; nothing changed.';
    END
    ELSE
    BEGIN
        -- Groups DEMO-B..DEMO-L, four teams each.
        CREATE TABLE #Slots (
            GroupNo int NOT NULL,
            Slot int NOT NULL,
            GroupCode nvarchar(8) NOT NULL,
            TeamName nvarchar(128) NOT NULL,
            TeamId int NULL,
            PRIMARY KEY (GroupNo, Slot)
        );

        ;WITH GroupNumbers AS (
            SELECT TOP (11)
                CONVERT(int, ROW_NUMBER() OVER (ORDER BY (SELECT NULL))) AS GroupNo
            FROM sys.all_objects
        ), SlotNumbers AS (
            SELECT TOP (4)
                CONVERT(int, ROW_NUMBER() OVER (ORDER BY (SELECT NULL))) AS Slot
            FROM sys.all_objects
        )
        INSERT INTO #Slots (GroupNo, Slot, GroupCode, TeamName)
        SELECT
            g.GroupNo,
            s.Slot,
            N'DEMO-' + CHAR(65 + g.GroupNo),
            N'Demo Team ' + CHAR(65 + g.GroupNo) + CONVERT(nvarchar(1), s.Slot)
        FROM GroupNumbers AS g
        CROSS JOIN SlotNumbers AS s;

        INSERT INTO wc2026.TournamentGroup (TournamentId, GroupCode, SourceReferenceId)
        SELECT DISTINCT @tournamentId, GroupCode, @sourceReferenceId
        FROM #Slots;

        INSERT INTO wc2026.Team (OfficialName, SourceReferenceId)
        SELECT TeamName, @sourceReferenceId
        FROM #Slots
        ORDER BY GroupNo, Slot;

        UPDATE s
        SET TeamId = t.TeamId
        FROM #Slots AS s
        JOIN wc2026.Team AS t ON t.OfficialName = s.TeamName;

        INSERT INTO wc2026.TournamentTeam (
            TournamentId, TeamId, GroupCode, SourceReferenceId
        )
        SELECT @tournamentId, TeamId, GroupCode, @sourceReferenceId
        FROM #Slots;

        -- Fifteen fictional venues across three fixed UTC offsets.
        CREATE TABLE #Venues (
            VenueIdx int NOT NULL PRIMARY KEY,
            VenueName nvarchar(200) NOT NULL,
            City nvarchar(128) NOT NULL,
            Country nvarchar(128) NOT NULL,
            TimeZoneId nvarchar(128) NOT NULL,
            OffsetHours int NOT NULL,
            VenueId int NULL
        );

        ;WITH VenueNumbers AS (
            SELECT TOP (15)
                CONVERT(int, ROW_NUMBER() OVER (ORDER BY (SELECT NULL))) AS VenueIdx
            FROM sys.all_objects
        )
        INSERT INTO #Venues (
            VenueIdx, VenueName, City, Country, TimeZoneId, OffsetHours
        )
        SELECT
            VenueIdx,
            N'DEMO Stadium ' + RIGHT(N'0' + CONVERT(nvarchar(2), VenueIdx), 2),
            N'Demo City ' + RIGHT(N'0' + CONVERT(nvarchar(2), VenueIdx), 2),
            CASE VenueIdx % 3
                WHEN 0 THEN N'Demo Country North'
                WHEN 1 THEN N'Demo Country South'
                ELSE N'Demo Country East'
            END,
            CASE VenueIdx % 3
                WHEN 0 THEN N'UTC'
                WHEN 1 THEN N'America/Mexico_City'
                ELSE N'America/New_York'
            END,
            CASE VenueIdx % 3 WHEN 0 THEN 0 WHEN 1 THEN -6 ELSE -4 END
        FROM VenueNumbers;

        INSERT INTO wc2026.Venue (
            OfficialName, City, Country, TimeZoneId, SourceReferenceId
        )
        SELECT VenueName, City, Country, TimeZoneId, @sourceReferenceId
        FROM #Venues
        ORDER BY VenueIdx;

        UPDATE v
        SET VenueId = venue.VenueId
        FROM #Venues AS v
        JOIN wc2026.Venue AS venue ON venue.OfficialName = v.VenueName;

        CREATE TABLE #Matches (
            MatchKey int NOT NULL PRIMARY KEY,
            StageName nvarchar(64) NOT NULL,
            GroupCode nvarchar(8) NULL,
            HomeTeamId int NOT NULL,
            AwayTeamId int NOT NULL,
            DayOffset int NOT NULL,
            HourUtc int NOT NULL,
            HomeWins bit NULL,
            RegH int NULL,
            RegA int NULL,
            EtH int NULL,
            EtA int NULL,
            PenH int NULL,
            PenA int NULL
        );

        -- Group stage: each group plays a six-match round robin.
        CREATE TABLE #Pairings (
            PairNo int NOT NULL,
            Matchday int NOT NULL,
            HomeSlot int NOT NULL,
            AwaySlot int NOT NULL
        );
        INSERT INTO #Pairings (PairNo, Matchday, HomeSlot, AwaySlot)
        VALUES (1, 1, 1, 2), (2, 1, 3, 4), (3, 2, 1, 3),
               (4, 2, 2, 4), (5, 3, 1, 4), (6, 3, 2, 3);

        INSERT INTO #Matches (
            MatchKey, StageName, GroupCode, HomeTeamId, AwayTeamId,
            DayOffset, HourUtc
        )
        SELECT
            (home.GroupNo - 1) * 6 + p.PairNo,
            N'Demo Group Stage',
            home.GroupCode,
            home.TeamId,
            away.TeamId,
            (p.Matchday - 1) * 4 + (home.GroupNo % 4),
            13 + 3 * ((p.PairNo - 1) % 4)
        FROM #Pairings AS p
        JOIN #Slots AS home ON home.Slot = p.HomeSlot
        JOIN #Slots AS away
            ON away.GroupNo = home.GroupNo AND away.Slot = p.AwaySlot;

        UPDATE #Matches
        SET RegH = CONVERT(int, SUBSTRING(HASHBYTES('MD5', CONCAT(MatchKey, ':home')), 1, 3)) % 4,
            RegA = CONVERT(int, SUBSTRING(HASHBYTES('MD5', CONCAT(MatchKey, ':away')), 1, 3)) % 4
        WHERE StageName = N'Demo Group Stage';

        -- Standings for the new groups, calculated from the matches above.
        CREATE TABLE #Standing (
            GroupCode nvarchar(8) NOT NULL,
            TeamId int NOT NULL,
            Pos int NOT NULL,
            Played int NOT NULL,
            Wins int NOT NULL,
            Draws int NOT NULL,
            Losses int NOT NULL,
            GoalsFor int NOT NULL,
            GoalsAgainst int NOT NULL,
            Points int NOT NULL,
            PRIMARY KEY (GroupCode, TeamId)
        );

        ;WITH Results AS (
            SELECT GroupCode, HomeTeamId AS TeamId, RegH AS GoalsFor, RegA AS GoalsAgainst
            FROM #Matches
            WHERE StageName = N'Demo Group Stage'
            UNION ALL
            SELECT GroupCode, AwayTeamId, RegA, RegH
            FROM #Matches
            WHERE StageName = N'Demo Group Stage'
        ), Totals AS (
            SELECT
                GroupCode,
                TeamId,
                COUNT(*) AS Played,
                SUM(CASE WHEN GoalsFor > GoalsAgainst THEN 1 ELSE 0 END) AS Wins,
                SUM(CASE WHEN GoalsFor = GoalsAgainst THEN 1 ELSE 0 END) AS Draws,
                SUM(CASE WHEN GoalsFor < GoalsAgainst THEN 1 ELSE 0 END) AS Losses,
                SUM(GoalsFor) AS GoalsFor,
                SUM(GoalsAgainst) AS GoalsAgainst
            FROM Results
            GROUP BY GroupCode, TeamId
        )
        INSERT INTO #Standing (
            GroupCode, TeamId, Pos, Played, Wins, Draws, Losses,
            GoalsFor, GoalsAgainst, Points
        )
        SELECT
            t.GroupCode,
            t.TeamId,
            ROW_NUMBER() OVER (
                PARTITION BY t.GroupCode
                ORDER BY t.Wins * 3 + t.Draws DESC,
                    t.GoalsFor - t.GoalsAgainst DESC,
                    t.GoalsFor DESC,
                    team.OfficialName
            ),
            t.Played, t.Wins, t.Draws, t.Losses,
            t.GoalsFor, t.GoalsAgainst,
            t.Wins * 3 + t.Draws
        FROM Totals AS t
        JOIN wc2026.Team AS team ON team.TeamId = t.TeamId;

        -- Qualification: top two per group plus the six best third-placed teams.
        CREATE TABLE #Qualified (
            TeamId int NOT NULL PRIMARY KEY,
            Pos int NOT NULL,
            Points int NOT NULL,
            GoalDiff int NOT NULL,
            GoalsFor int NOT NULL,
            TeamName nvarchar(128) NOT NULL
        );

        INSERT INTO #Qualified (TeamId, Pos, Points, GoalDiff, GoalsFor, TeamName)
        SELECT
            s.TeamId, s.Pos, s.Points, s.GoalsFor - s.GoalsAgainst,
            s.GoalsFor, t.OfficialName
        FROM #Standing AS s
        JOIN wc2026.Team AS t ON t.TeamId = s.TeamId
        WHERE s.Pos <= 2;

        ;WITH Thirds AS (
            SELECT
                s.TeamId, s.Pos, s.Points,
                s.GoalsFor - s.GoalsAgainst AS GoalDiff,
                s.GoalsFor, t.OfficialName,
                ROW_NUMBER() OVER (
                    ORDER BY s.Points DESC,
                        s.GoalsFor - s.GoalsAgainst DESC,
                        s.GoalsFor DESC,
                        t.OfficialName
                ) AS ThirdRank
            FROM #Standing AS s
            JOIN wc2026.Team AS t ON t.TeamId = s.TeamId
            WHERE s.Pos = 3
        )
        INSERT INTO #Qualified (TeamId, Pos, Points, GoalDiff, GoalsFor, TeamName)
        SELECT TeamId, Pos, Points, GoalDiff, GoalsFor, OfficialName
        FROM Thirds
        WHERE ThirdRank <= 6;

        INSERT INTO wc2026.OfficialGroupStanding (
            TournamentId, GroupCode, TeamId, OfficialPosition, Played, Wins,
            Draws, Losses, GoalsFor, GoalsAgainst, GoalDifference, Points,
            QualificationStatus, SourceReferenceId
        )
        SELECT
            @tournamentId, s.GroupCode, s.TeamId, s.Pos, s.Played, s.Wins,
            s.Draws, s.Losses, s.GoalsFor, s.GoalsAgainst,
            s.GoalsFor - s.GoalsAgainst, s.Points,
            CASE
                WHEN s.Pos <= 2 THEN N'Demo qualifier'
                WHEN q.TeamId IS NOT NULL THEN N'Demo qualifier (best third place)'
                ELSE N'Demo eliminated'
            END,
            @sourceReferenceId
        FROM #Standing AS s
        LEFT JOIN #Qualified AS q ON q.TeamId = s.TeamId;

        -- Seeds 1-4 are the DEMO-A teams; seeds 5-32 follow group performance.
        CREATE TABLE #Seeds (
            Seed int NOT NULL PRIMARY KEY,
            TeamId int NOT NULL
        );

        INSERT INTO #Seeds (Seed, TeamId)
        SELECT x.Seed, t.TeamId
        FROM (VALUES
            (1, N'Demo Aurora FC'), (2, N'Demo Borealis FC'),
            (3, N'Demo Cinder FC'), (4, N'Demo Drift FC')
        ) AS x (Seed, TeamName)
        JOIN wc2026.Team AS t ON t.OfficialName = x.TeamName;

        INSERT INTO #Seeds (Seed, TeamId)
        SELECT
            4 + ROW_NUMBER() OVER (
                ORDER BY q.Pos, q.Points DESC, q.GoalDiff DESC,
                    q.GoalsFor DESC, q.TeamName
            ),
            q.TeamId
        FROM #Qualified AS q;

        IF (SELECT COUNT(*) FROM #Seeds) <> 32
            THROW 50004, N'The knockout bracket requires exactly 32 teams.', 1;

        -- Standard 32-team seeding; the better seed always advances.
        CREATE TABLE #Bracket (
            Pos int NOT NULL PRIMARY KEY,
            Seed int NOT NULL
        );
        INSERT INTO #Bracket (Pos, Seed)
        VALUES (1, 1), (2, 32), (3, 16), (4, 17), (5, 8), (6, 25), (7, 9), (8, 24),
               (9, 4), (10, 29), (11, 13), (12, 20), (13, 5), (14, 28), (15, 12),
               (16, 21), (17, 2), (18, 31), (19, 15), (20, 18), (21, 7), (22, 26),
               (23, 10), (24, 23), (25, 3), (26, 30), (27, 14), (28, 19), (29, 6),
               (30, 27), (31, 11), (32, 22);

        CREATE TABLE #KO (
            StageName nvarchar(64) NOT NULL,
            Idx int NOT NULL,
            HiSeed int NOT NULL,
            LoSeed int NOT NULL,
            PRIMARY KEY (StageName, Idx)
        );

        INSERT INTO #KO (StageName, Idx, HiSeed, LoSeed)
        SELECT N'Round of 32', (Pos + 1) / 2, MIN(Seed), MAX(Seed)
        FROM #Bracket
        GROUP BY (Pos + 1) / 2;

        INSERT INTO #KO (StageName, Idx, HiSeed, LoSeed)
        SELECT N'Round of 16', (Idx + 1) / 2, MIN(HiSeed), MAX(HiSeed)
        FROM #KO WHERE StageName = N'Round of 32'
        GROUP BY (Idx + 1) / 2;

        INSERT INTO #KO (StageName, Idx, HiSeed, LoSeed)
        SELECT N'Quarter-final', (Idx + 1) / 2, MIN(HiSeed), MAX(HiSeed)
        FROM #KO WHERE StageName = N'Round of 16'
        GROUP BY (Idx + 1) / 2;

        INSERT INTO #KO (StageName, Idx, HiSeed, LoSeed)
        SELECT N'Semi-final', (Idx + 1) / 2, MIN(HiSeed), MAX(HiSeed)
        FROM #KO WHERE StageName = N'Quarter-final'
        GROUP BY (Idx + 1) / 2;

        INSERT INTO #KO (StageName, Idx, HiSeed, LoSeed)
        SELECT N'Final', 1, MIN(HiSeed), MAX(HiSeed)
        FROM #KO WHERE StageName = N'Semi-final';

        INSERT INTO #KO (StageName, Idx, HiSeed, LoSeed)
        SELECT N'Third place', 1, MIN(LoSeed), MAX(LoSeed)
        FROM #KO WHERE StageName = N'Semi-final';

        INSERT INTO #Matches (
            MatchKey, StageName, GroupCode, HomeTeamId, AwayTeamId,
            DayOffset, HourUtc, HomeWins
        )
        SELECT
            CASE k.StageName
                WHEN N'Round of 32' THEN 100
                WHEN N'Round of 16' THEN 200
                WHEN N'Quarter-final' THEN 300
                WHEN N'Semi-final' THEN 400
                WHEN N'Third place' THEN 500
                ELSE 600
            END + k.Idx,
            k.StageName,
            NULL,
            CASE WHEN k.Idx % 2 = 1 THEN hi.TeamId ELSE lo.TeamId END,
            CASE WHEN k.Idx % 2 = 1 THEN lo.TeamId ELSE hi.TeamId END,
            CASE k.StageName
                WHEN N'Round of 32' THEN 15 + (k.Idx - 1) / 4
                WHEN N'Round of 16' THEN 20 + (k.Idx - 1) / 4
                WHEN N'Quarter-final' THEN 23 + (k.Idx - 1) / 2
                WHEN N'Semi-final' THEN 26 + (k.Idx - 1)
                WHEN N'Third place' THEN 28
                ELSE 29
            END,
            13 + 3 * ((k.Idx - 1) % 4),
            CASE WHEN k.Idx % 2 = 1 THEN 1 ELSE 0 END
        FROM #KO AS k
        JOIN #Seeds AS hi ON hi.Seed = k.HiSeed
        JOIN #Seeds AS lo ON lo.Seed = k.LoSeed;

        -- Knockout scores: the better seed wins, in regulation, extra time,
        -- or on penalties (about a quarter of matches are level after 90').
        UPDATE m
        SET
            RegH = CASE
                WHEN c.IsDraw = 1 THEN c.DrawGoals
                WHEN m.HomeWins = 1 THEN c.LoserGoals + 1 + c.Margin
                ELSE c.LoserGoals
            END,
            RegA = CASE
                WHEN c.IsDraw = 1 THEN c.DrawGoals
                WHEN m.HomeWins = 1 THEN c.LoserGoals
                ELSE c.LoserGoals + 1 + c.Margin
            END,
            EtH = CASE
                WHEN c.IsDraw = 0 THEN NULL
                WHEN c.ExtraTimeWin = 1 AND m.HomeWins = 1 THEN c.DrawGoals + 1
                ELSE c.DrawGoals
            END,
            EtA = CASE
                WHEN c.IsDraw = 0 THEN NULL
                WHEN c.ExtraTimeWin = 1 AND m.HomeWins = 0 THEN c.DrawGoals + 1
                ELSE c.DrawGoals
            END,
            PenH = CASE
                WHEN c.IsDraw = 1 AND c.ExtraTimeWin = 0
                    THEN CASE WHEN m.HomeWins = 1 THEN c.WinPens ELSE c.WinPens - c.PenGap END
            END,
            PenA = CASE
                WHEN c.IsDraw = 1 AND c.ExtraTimeWin = 0
                    THEN CASE WHEN m.HomeWins = 1 THEN c.WinPens - c.PenGap ELSE c.WinPens END
            END
        FROM #Matches AS m
        CROSS APPLY (
            SELECT CONVERT(int, SUBSTRING(HASHBYTES('MD5', CONCAT(m.MatchKey, ':ko')), 1, 3)) AS HashValue
        ) AS h
        CROSS APPLY (
            SELECT
                CASE WHEN h.HashValue % 4 = 0 THEN 1 ELSE 0 END AS IsDraw,
                (h.HashValue / 16) % 3 AS DrawGoals,
                (h.HashValue / 4) % 3 AS LoserGoals,
                (h.HashValue / 16) % 2 AS Margin,
                CASE WHEN (h.HashValue / 64) % 2 = 0 THEN 1 ELSE 0 END AS ExtraTimeWin,
                4 + (h.HashValue / 128) % 2 AS WinPens,
                1 + (h.HashValue / 256) % 2 AS PenGap
        ) AS c
        WHERE m.StageName <> N'Demo Group Stage';

        INSERT INTO wc2026.TournamentMatch (
            TournamentId, StageName, GroupCode, VenueId, HomeTeamId, AwayTeamId,
            KickoffUtc, KickoffLocal, MatchStatus,
            RegulationHomeScore, RegulationAwayScore,
            ScoreAfterExtraTimeHome, ScoreAfterExtraTimeAway,
            PenaltyHomeScore, PenaltyAwayScore, SourceReferenceId
        )
        SELECT
            @tournamentId, m.StageName, m.GroupCode, v.VenueId,
            m.HomeTeamId, m.AwayTeamId,
            TODATETIMEOFFSET(u.UtcDateTime, '+00:00'),
            DATEADD(hour, v.OffsetHours, u.UtcDateTime),
            N'completed',
            m.RegH, m.RegA, m.EtH, m.EtA, m.PenH, m.PenA,
            @sourceReferenceId
        FROM #Matches AS m
        JOIN #Venues AS v ON v.VenueIdx = (m.MatchKey % 15) + 1
        CROSS APPLY (
            SELECT DATEADD(
                hour,
                m.HourUtc,
                CONVERT(datetime2(0), DATEADD(day, m.DayOffset, CONVERT(date, '2026-06-01')))
            ) AS UtcDateTime
        ) AS u
        ORDER BY m.MatchKey;

        -- Final placements: derived from the seed each team reached.
        INSERT INTO wc2026.OfficialFinalPlacement (
            TournamentId, TeamId, PlacementLabel, PublishedRank, SourceReferenceId
        )
        SELECT @tournamentId, p.TeamId, p.PlacementLabel, p.PlacementRank, @sourceReferenceId
        FROM (
            SELECT
                sd.TeamId,
                CASE
                    WHEN sd.Seed = 1 THEN N'Demo champion'
                    WHEN sd.Seed = 2 THEN N'Demo finalist'
                    WHEN sd.Seed = 3 THEN N'Demo third place'
                    WHEN sd.Seed = 4 THEN N'Demo fourth place'
                    WHEN sd.Seed <= 8 THEN N'Demo quarter-finalist'
                    WHEN sd.Seed <= 16 THEN N'Demo round of 16 exit'
                    ELSE N'Demo round of 32 exit'
                END AS PlacementLabel,
                CASE
                    WHEN sd.Seed <= 4 THEN sd.Seed
                    WHEN sd.Seed <= 8 THEN 5
                    WHEN sd.Seed <= 16 THEN 9
                    ELSE 17
                END AS PlacementRank
            FROM #Seeds AS sd
            UNION ALL
            SELECT s.TeamId, N'Demo group-stage exit', 33
            FROM #Slots AS s
            WHERE NOT EXISTS (SELECT 1 FROM #Seeds AS sd WHERE sd.TeamId = s.TeamId)
        ) AS p
        WHERE NOT EXISTS (
            SELECT 1
            FROM wc2026.OfficialFinalPlacement AS existing
            WHERE existing.TournamentId = @tournamentId
                AND existing.TeamId = p.TeamId
        );
    END;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;
    THROW;
END CATCH;
