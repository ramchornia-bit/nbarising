import '../nba_fantasy_app/lib/nba_data.dart';

Future<void> main() async {
  final api = EspnNbaApi();
  final games = await api.gamesForDate(DateTime(2025, 11, 3));
  if (games.isEmpty) throw StateError('Expected a historical NBA game.');
  final players = await api.boxScore(games.first.id);
  if (players.isEmpty) throw StateError('Expected player box score rows.');
  print('${games.length} games; ${players.length} player rows; first: ${players.first.name}');
}
