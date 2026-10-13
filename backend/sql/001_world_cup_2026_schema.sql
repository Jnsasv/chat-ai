IF SCHEMA_ID(N'wc2026') IS NULL
    EXEC(N'CREATE SCHEMA wc2026');

CREATE TABLE wc2026.SourceReference (
    SourceReferenceId int IDENTITY(1, 1) NOT NULL
        CONSTRAINT PK_SourceReference PRIMARY KEY,
    Publisher nvarchar(100) NOT NULL,
    Title nvarchar(200) NOT NULL,
    SourceUrl nvarchar(2048) NOT NULL,
    RetrievedAt datetimeoffset(0) NOT NULL,
    CONSTRAINT CK_SourceReference_HttpsUrl
        CHECK (SourceUrl LIKE N'https://%')
);

CREATE TABLE wc2026.Tournament (
    TournamentId int IDENTITY(1, 1) NOT NULL
        CONSTRAINT PK_Tournament PRIMARY KEY,
    OfficialName nvarchar(200) NOT NULL,
    EditionYear smallint NOT NULL,
    StartDate date NOT NULL,
    EndDate date NOT NULL,
    SourceReferenceId int NOT NULL,
    CONSTRAINT UQ_Tournament_Name_Edition
        UNIQUE (OfficialName, EditionYear),
    CONSTRAINT FK_Tournament_SourceReference
        FOREIGN KEY (SourceReferenceId)
        REFERENCES wc2026.SourceReference (SourceReferenceId),
    CONSTRAINT CK_Tournament_DateRange
        CHECK (EndDate >= StartDate)
);

CREATE TABLE wc2026.Team (
    TeamId int IDENTITY(1, 1) NOT NULL
        CONSTRAINT PK_Team PRIMARY KEY,
    OfficialName nvarchar(128) NOT NULL
        CONSTRAINT UQ_Team_OfficialName UNIQUE,
    SourceReferenceId int NOT NULL,
    CONSTRAINT FK_Team_SourceReference
        FOREIGN KEY (SourceReferenceId)
        REFERENCES wc2026.SourceReference (SourceReferenceId)
);

CREATE TABLE wc2026.TournamentGroup (
    TournamentId int NOT NULL,
    GroupCode nvarchar(8) NOT NULL,
    SourceReferenceId int NOT NULL,
    CONSTRAINT PK_TournamentGroup
        PRIMARY KEY (TournamentId, GroupCode),
    CONSTRAINT FK_TournamentGroup_Tournament
        FOREIGN KEY (TournamentId)
        REFERENCES wc2026.Tournament (TournamentId),
    CONSTRAINT FK_TournamentGroup_SourceReference
        FOREIGN KEY (SourceReferenceId)
        REFERENCES wc2026.SourceReference (SourceReferenceId)
);

CREATE TABLE wc2026.TournamentTeam (
    TournamentId int NOT NULL,
    TeamId int NOT NULL,
    GroupCode nvarchar(8) NOT NULL,
    SourceReferenceId int NOT NULL,
    CONSTRAINT PK_TournamentTeam
        PRIMARY KEY (TournamentId, TeamId),
    CONSTRAINT FK_TournamentTeam_Tournament
        FOREIGN KEY (TournamentId)
        REFERENCES wc2026.Tournament (TournamentId),
    CONSTRAINT FK_TournamentTeam_Team
        FOREIGN KEY (TeamId)
        REFERENCES wc2026.Team (TeamId),
    CONSTRAINT FK_TournamentTeam_Group
        FOREIGN KEY (TournamentId, GroupCode)
        REFERENCES wc2026.TournamentGroup (TournamentId, GroupCode),
    CONSTRAINT FK_TournamentTeam_SourceReference
        FOREIGN KEY (SourceReferenceId)
        REFERENCES wc2026.SourceReference (SourceReferenceId)
);

CREATE TABLE wc2026.Venue (
    VenueId int IDENTITY(1, 1) NOT NULL
        CONSTRAINT PK_Venue PRIMARY KEY,
    OfficialName nvarchar(200) NOT NULL,
    City nvarchar(128) NOT NULL,
    Country nvarchar(128) NOT NULL,
    TimeZoneId nvarchar(128) NOT NULL,
    SourceReferenceId int NOT NULL,
    CONSTRAINT FK_Venue_SourceReference
        FOREIGN KEY (SourceReferenceId)
        REFERENCES wc2026.SourceReference (SourceReferenceId)
);

CREATE TABLE wc2026.TournamentMatch (
    MatchId int IDENTITY(1, 1) NOT NULL
        CONSTRAINT PK_TournamentMatch PRIMARY KEY,
    TournamentId int NOT NULL,
    StageName nvarchar(64) NOT NULL,
    GroupCode nvarchar(8) NULL,
    VenueId int NOT NULL,
    HomeTeamId int NOT NULL,
    AwayTeamId int NOT NULL,
    KickoffUtc datetimeoffset(0) NOT NULL,
    KickoffLocal datetime2(0) NOT NULL,
    MatchStatus nvarchar(32) NOT NULL,
    RegulationHomeScore smallint NULL,
    RegulationAwayScore smallint NULL,
    ScoreAfterExtraTimeHome smallint NULL,
    ScoreAfterExtraTimeAway smallint NULL,
    PenaltyHomeScore smallint NULL,
    PenaltyAwayScore smallint NULL,
    SourceReferenceId int NOT NULL,
    CONSTRAINT FK_TournamentMatch_Tournament
        FOREIGN KEY (TournamentId)
        REFERENCES wc2026.Tournament (TournamentId),
    CONSTRAINT FK_TournamentMatch_Group
        FOREIGN KEY (TournamentId, GroupCode)
        REFERENCES wc2026.TournamentGroup (TournamentId, GroupCode),
    CONSTRAINT FK_TournamentMatch_Venue
        FOREIGN KEY (VenueId)
        REFERENCES wc2026.Venue (VenueId),
    CONSTRAINT FK_TournamentMatch_HomeTeam
        FOREIGN KEY (TournamentId, HomeTeamId)
        REFERENCES wc2026.TournamentTeam (TournamentId, TeamId),
    CONSTRAINT FK_TournamentMatch_AwayTeam
        FOREIGN KEY (TournamentId, AwayTeamId)
        REFERENCES wc2026.TournamentTeam (TournamentId, TeamId),
    CONSTRAINT FK_TournamentMatch_SourceReference
        FOREIGN KEY (SourceReferenceId)
        REFERENCES wc2026.SourceReference (SourceReferenceId),
    CONSTRAINT CK_TournamentMatch_DifferentTeams
        CHECK (HomeTeamId <> AwayTeamId),
    CONSTRAINT CK_TournamentMatch_UtcOffset
        CHECK (DATEPART(TZOFFSET, KickoffUtc) = 0),
    CONSTRAINT CK_TournamentMatch_RegulationScorePair
        CHECK (
            (RegulationHomeScore IS NULL AND RegulationAwayScore IS NULL)
            OR (RegulationHomeScore IS NOT NULL AND RegulationAwayScore IS NOT NULL)
        ),
    CONSTRAINT CK_TournamentMatch_NonnegativeScores
        CHECK (
            (RegulationHomeScore IS NULL OR RegulationHomeScore >= 0)
            AND (RegulationAwayScore IS NULL OR RegulationAwayScore >= 0)
            AND (ScoreAfterExtraTimeHome IS NULL OR ScoreAfterExtraTimeHome >= 0)
            AND (ScoreAfterExtraTimeAway IS NULL OR ScoreAfterExtraTimeAway >= 0)
            AND (PenaltyHomeScore IS NULL OR PenaltyHomeScore >= 0)
            AND (PenaltyAwayScore IS NULL OR PenaltyAwayScore >= 0)
        ),
    CONSTRAINT CK_TournamentMatch_ExtraTimeScorePair
        CHECK (
            (ScoreAfterExtraTimeHome IS NULL AND ScoreAfterExtraTimeAway IS NULL)
            OR (ScoreAfterExtraTimeHome IS NOT NULL AND ScoreAfterExtraTimeAway IS NOT NULL)
        ),
    CONSTRAINT CK_TournamentMatch_PenaltyScorePair
        CHECK (
            (PenaltyHomeScore IS NULL AND PenaltyAwayScore IS NULL)
            OR (PenaltyHomeScore IS NOT NULL AND PenaltyAwayScore IS NOT NULL)
        )
);

CREATE TABLE wc2026.OfficialGroupStanding (
    TournamentId int NOT NULL,
    GroupCode nvarchar(8) NOT NULL,
    TeamId int NOT NULL,
    OfficialPosition smallint NOT NULL,
    Played smallint NULL,
    Wins smallint NULL,
    Draws smallint NULL,
    Losses smallint NULL,
    GoalsFor smallint NULL,
    GoalsAgainst smallint NULL,
    GoalDifference smallint NULL,
    Points smallint NULL,
    QualificationStatus nvarchar(64) NULL,
    SourceReferenceId int NOT NULL,
    CONSTRAINT PK_OfficialGroupStanding
        PRIMARY KEY (TournamentId, GroupCode, TeamId),
    CONSTRAINT FK_OfficialGroupStanding_TournamentTeam
        FOREIGN KEY (TournamentId, TeamId)
        REFERENCES wc2026.TournamentTeam (TournamentId, TeamId),
    CONSTRAINT FK_OfficialGroupStanding_Group
        FOREIGN KEY (TournamentId, GroupCode)
        REFERENCES wc2026.TournamentGroup (TournamentId, GroupCode),
    CONSTRAINT FK_OfficialGroupStanding_SourceReference
        FOREIGN KEY (SourceReferenceId)
        REFERENCES wc2026.SourceReference (SourceReferenceId),
    CONSTRAINT CK_OfficialGroupStanding_NonnegativeValues
        CHECK (
            OfficialPosition > 0
            AND (Played IS NULL OR Played >= 0)
            AND (Wins IS NULL OR Wins >= 0)
            AND (Draws IS NULL OR Draws >= 0)
            AND (Losses IS NULL OR Losses >= 0)
            AND (GoalsFor IS NULL OR GoalsFor >= 0)
            AND (GoalsAgainst IS NULL OR GoalsAgainst >= 0)
            AND (Points IS NULL OR Points >= 0)
        )
);

CREATE TABLE wc2026.OfficialFinalPlacement (
    TournamentId int NOT NULL,
    TeamId int NOT NULL,
    PlacementLabel nvarchar(64) NOT NULL,
    PublishedRank smallint NULL,
    SourceReferenceId int NOT NULL,
    CONSTRAINT PK_OfficialFinalPlacement
        PRIMARY KEY (TournamentId, TeamId),
    CONSTRAINT FK_OfficialFinalPlacement_TournamentTeam
        FOREIGN KEY (TournamentId, TeamId)
        REFERENCES wc2026.TournamentTeam (TournamentId, TeamId),
    CONSTRAINT FK_OfficialFinalPlacement_SourceReference
        FOREIGN KEY (SourceReferenceId)
        REFERENCES wc2026.SourceReference (SourceReferenceId),
    CONSTRAINT CK_OfficialFinalPlacement_PositiveRank
        CHECK (PublishedRank IS NULL OR PublishedRank > 0)
);
