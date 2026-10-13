-- Removes only the rows added by 003_world_cup_2026_demo_large_seed.sql,
-- leaving the small fixture from 002 untouched.
SET NOCOUNT ON;
SET XACT_ABORT ON;

IF DB_NAME() <> N'WorldCup2026Demo'
    THROW 50001, N'This reset may only be applied to WorldCup2026Demo.', 1;

BEGIN TRANSACTION;

DELETE FROM wc2026.TournamentMatch
WHERE GroupCode IS NULL OR GroupCode <> N'DEMO-A';

DELETE FROM wc2026.OfficialGroupStanding
WHERE GroupCode <> N'DEMO-A';

DELETE FROM wc2026.OfficialFinalPlacement
WHERE TeamId IN (SELECT TeamId FROM wc2026.Team WHERE OfficialName LIKE N'Demo Team _%');

DELETE FROM wc2026.TournamentTeam
WHERE GroupCode <> N'DEMO-A';

DELETE FROM wc2026.TournamentGroup
WHERE GroupCode <> N'DEMO-A';

DELETE FROM wc2026.Team
WHERE OfficialName LIKE N'Demo Team _%';

DELETE FROM wc2026.Venue
WHERE OfficialName LIKE N'DEMO Stadium __';

COMMIT TRANSACTION;
