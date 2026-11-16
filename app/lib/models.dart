double _d(dynamic v) => v is num ? v.toDouble() : 0.0;
double? _dn(dynamic v) => v is num ? v.toDouble() : null;

class Flag {
  Flag(this.level, this.text);
  final String level;
  final String text;
  factory Flag.fromJson(Map<String, dynamic> j) =>
      Flag((j['level'] ?? '').toString(), (j['text'] ?? '').toString());
}

class Player {
  Player({
    required this.id,
    required this.name,
    required this.team,
    required this.score,
    required this.label,
    required this.reason,
    required this.minutesRecent,
    required this.minutesBaseline,
    required this.recentValues,
    required this.capped,
    required this.stash,
    required this.seasonRank,
    required this.gamesPlayed,
    required this.flags,
    required this.signals,
  });

  final int id;
  final String name;
  final String team;
  final double score;
  final String? label;
  final String reason;
  final double? minutesRecent;
  final double? minutesBaseline;
  final List<double> recentValues;
  final bool capped;
  final bool stash;
  final int? seasonRank;
  final int? gamesPlayed;
  final List<Flag> flags;
  final Map<String, double> signals;

  factory Player.basic(int id, String name, String team) => Player(
        id: id,
        name: name,
        team: team,
        score: 0,
        label: null,
        reason: '',
        minutesRecent: null,
        minutesBaseline: null,
        recentValues: const [],
        capped: false,
        stash: false,
        seasonRank: null,
        gamesPlayed: null,
        flags: const [],
        signals: const {},
      );

  factory Player.fromJson(Map<String, dynamic> j) {
    final rawSignals = j['signalPercentiles'];
    return Player(
      id: (j['playerId'] as num?)?.toInt() ?? 0,
      name: (j['playerName'] ?? '').toString(),
      team: (j['team'] ?? '').toString(),
      score: _d(j['score']),
      label: j['label']?.toString(),
      reason: (j['reason'] ?? '').toString(),
      minutesRecent: _dn(j['minutesRecent']),
      minutesBaseline: _dn(j['minutesBaseline']),
      recentValues: ((j['recentValues'] as List?) ?? const []).map(_d).toList(),
      capped: j['capped'] == true,
      stash: j['stash'] == true,
      seasonRank: (j['seasonRank'] as num?)?.toInt(),
      gamesPlayed: (j['gamesPlayed'] as num?)?.toInt(),
      flags: ((j['flags'] as List?) ?? const [])
          .whereType<Map>()
          .map((f) => Flag.fromJson(Map<String, dynamic>.from(f)))
          .toList(),
      signals: rawSignals is Map
          ? rawSignals.map((k, v) => MapEntry(k.toString(), _d(v)))
          : <String, double>{},
    );
  }
}

class ListResult {
  ListResult({
    required this.players,
    required this.dataThrough,
    required this.notes,
    required this.recentGames,
    required this.baselineGames,
    required this.populationSize,
    required this.distribution,
  });

  final List<Player> players;
  final String? dataThrough;
  final List<String> notes;
  final int? recentGames;
  final int? baselineGames;
  final int? populationSize;
  final Map<String, int> distribution;

  factory ListResult.fromJson(Map<String, dynamic> j) => ListResult(
        players: ((j['players'] as List?) ?? const [])
            .whereType<Map>()
            .map((p) => Player.fromJson(Map<String, dynamic>.from(p)))
            .toList(),
        dataThrough: j['dataThrough']?.toString(),
        notes: ((j['notes'] as List?) ?? const []).map((n) => n.toString()).toList(),
        recentGames: (j['recentGames'] as num?)?.toInt(),
        baselineGames: (j['baselineGames'] as num?)?.toInt(),
        populationSize: (j['populationSize'] as num?)?.toInt(),
        distribution: j['distribution'] is Map
            ? (j['distribution'] as Map).map((k, v) => MapEntry(k.toString(), (v as num).toInt()))
            : <String, int>{},
      );
}

class GameLine {
  GameLine(this.date, this.opponent, this.value, this.minutes, this.started, this.points,
      this.rebounds, this.assists, this.steals, this.blocks, this.turnovers);
  final String date;
  final String opponent;
  final double value;
  final double minutes;
  final bool started;
  final int points, rebounds, assists, steals, blocks, turnovers;

  factory GameLine.fromJson(Map<String, dynamic> j) => GameLine(
        (j['date'] ?? '').toString(),
        (j['opponent'] ?? '').toString(),
        _d(j['value']),
        _d(j['minutes']),
        j['started'] == true,
        (j['points'] as num?)?.toInt() ?? 0,
        (j['rebounds'] as num?)?.toInt() ?? 0,
        (j['assists'] as num?)?.toInt() ?? 0,
        (j['steals'] as num?)?.toInt() ?? 0,
        (j['blocks'] as num?)?.toInt() ?? 0,
        (j['turnovers'] as num?)?.toInt() ?? 0,
      );
}

class FormResult {
  FormResult(this.name, this.team, this.seasonAverage, this.seasonGames, this.games);
  final String name;
  final String team;
  final double seasonAverage;
  final int seasonGames;
  final List<GameLine> games;

  factory FormResult.fromJson(Map<String, dynamic> j) => FormResult(
        (j['name'] ?? '').toString(),
        (j['team'] ?? '').toString(),
        _d(j['seasonAverage']),
        (j['seasonGames'] as num?)?.toInt() ?? 0,
        ((j['games'] as List?) ?? const [])
            .whereType<Map>()
            .map((g) => GameLine.fromJson(Map<String, dynamic>.from(g)))
            .toList(),
      );
}
