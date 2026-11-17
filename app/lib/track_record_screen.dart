import 'package:flutter/material.dart';

import 'charts.dart';
import 'state.dart';
import 'ui.dart';

class TrackRecordScreen extends StatefulWidget {
  const TrackRecordScreen({super.key, required this.state});
  final AppState state;

  @override
  State<TrackRecordScreen> createState() => _TrackRecordScreenState();
}

class _TrackRecordScreenState extends State<TrackRecordScreen> {
  late Future<Map<String, dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = _fetch();
  }

  Future<Map<String, dynamic>> _fetch() =>
      widget.state.api.post('/backtest', {...widget.state.scoringBody, 'forward': 5, 'step': 3});

  static const _titles = {
    'sustained': 'Rising (sustained)',
    'hot': 'Hot (last 3 games)',
    'drop': 'Drop candidates',
  };

  double? _n(dynamic v) => v is num ? v.toDouble() : null;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Track record')),
      body: FutureBuilder<Map<String, dynamic>>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return Center(child: Padding(padding: const EdgeInsets.all(24), child: Text(snapshot.error.toString())));
          }
          final data = snapshot.data!;
          final lists = Map<String, dynamic>.from(data['lists'] as Map? ?? {});
          final dates = (data['asOfDates'] as List?) ?? const [];
          final forward = data['forwardGames'] ?? 5;
          return ListView(padding: const EdgeInsets.all(16), children: [
            Text('How did past picks do afterwards?', style: theme.textTheme.titleMedium),
            const SizedBox(height: 6),
            Text(
              'Each past day was replayed using only the games played up to then. For every listed player we '
              'compare his next $forward games with his own season average at that time. '
              'Bars to the right mean he did better than his own average; to the left, worse. '
              '"Not listed" players from the same pool are the yardstick.',
              style: theme.textTheme.bodySmall?.copyWith(color: theme.hintColor),
            ),
            const SizedBox(height: 6),
            Text('${dates.length} past days tested · data through ${data['dataThrough'] ?? '?'}',
                style: theme.textTheme.bodySmall?.copyWith(color: theme.hintColor)),
            if (lists.isEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 24),
                child: Text(((data['notes'] as List?) ?? const []).join(' ')),
              ),
            for (final entry in lists.entries) _section(context, entry.key, Map<String, dynamic>.from(entry.value as Map)),
            const SizedBox(height: 12),
            Text(
              'Injury information is not part of this test (only today\'s injury list is available), '
              'so it can only understate the add lists. Early in a season the number of picks is small: '
              'read these as a first look, not proof.',
              style: theme.textTheme.bodySmall?.copyWith(color: theme.hintColor),
            ),
          ]);
        },
      ),
    );
  }

  Widget _section(BuildContext context, String key, Map<String, dynamic> block) {
    final theme = Theme.of(context);
    final tiers = Map<String, dynamic>.from(block['tiers'] as Map? ?? {});
    var maxAbs = 1.0;
    for (final v in tiers.values) {
      final c = _n((v as Map)['avgChange']);
      if (c != null && c.abs() > maxAbs) maxAbs = c.abs();
    }
    return Padding(
      padding: const EdgeInsets.only(top: 22),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(_titles[key] ?? key, style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
        const SizedBox(height: 4),
        Text((block['summary'] ?? '').toString(), style: theme.textTheme.bodyMedium),
        const SizedBox(height: 10),
        for (final e in tiers.entries) _row(context, e.key, Map<String, dynamic>.from(e.value as Map), maxAbs, block['direction'] == 'down'),
      ]),
    );
  }

  Widget _row(BuildContext context, String tier, Map<String, dynamic> v, double maxAbs, bool down) {
    final theme = Theme.of(context);
    final picks = (v['picks'] as num?)?.toInt() ?? 0;
    final control = tier.startsWith('Not listed');
    final color = control ? theme.hintColor : labelColor(tier);
    if (picks == 0) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Text('$tier: no picks in this period', style: theme.textTheme.bodySmall?.copyWith(color: theme.hintColor)),
      );
    }
    final change = _n(v['avgChange']) ?? 0;
    final lift = _n(v['lift']);
    final enough = v['enough'] == true;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(child: Text(tier, style: TextStyle(color: color, fontWeight: FontWeight.w700))),
          Text('${change >= 0 ? '+' : ''}${change.toStringAsFixed(1)}',
              style: TextStyle(
                  fontWeight: FontWeight.w700,
                  color: change < 0 ? const Color(0xFFC62828) : const Color(0xFF1B8A3E))),
        ]),
        const SizedBox(height: 4),
        DeltaBar(value: change, maxAbs: maxAbs, color: color),
        const SizedBox(height: 4),
        Text(
          '$picks picks (${v['players']} players) · '
          '${(_n(v['hitRate']) ?? 0).toStringAsFixed(0)}% ${down ? 'fell' : 'rose'}'
          '${lift == null ? '' : ' · vs not listed ${lift >= 0 ? '+' : ''}${lift.toStringAsFixed(1)}'}'
          '${enough || control ? '' : ' · few picks'}',
          style: theme.textTheme.bodySmall?.copyWith(color: theme.hintColor),
        ),
      ]),
    );
  }
}
