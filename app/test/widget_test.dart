import 'package:flutter_test/flutter_test.dart';
import 'package:court_signal/models.dart';

void main() {
  test('parses a player from the API', () {
    final p = Player.fromJson({
      'playerId': 1,
      'playerName': 'Test Player',
      'team': 'BOS',
      'score': 91.2,
      'label': 'Good catch',
      'recentValues': [20, 25.5],
      'flags': [
        {'level': 'day_to_day', 'text': 'Day-to-day: knee'}
      ],
    });
    expect(p.score, 91.2);
    expect(p.recentValues.length, 2);
    expect(p.flags.first.level, 'day_to_day');
  });
}
