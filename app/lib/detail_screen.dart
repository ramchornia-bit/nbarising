import 'package:flutter/material.dart';

import 'models.dart';
import 'state.dart';
import 'ui.dart';

class DetailScreen extends StatefulWidget {
  const DetailScreen({super.key, required this.state, required this.player});
  final AppState state;
  final Player player;

  @override
  State<DetailScreen> createState() => _DetailScreenState();
}

class _DetailScreenState extends State<DetailScreen> {
  late Future<FormResult> _future;

  @override
  void initState() {
    super.initState();
    _future = _fetch();
  }

  Future<FormResult> _fetch() async {
    final json = await widget.state.api.get(
        '/players/${widget.player.id}/form', {'games': '12', 'format': widget.state.format});
    return FormResult.fromJson(json);
  }

  @override
  Widget build(BuildContext context) {
    final p = widget.player;
    final theme = Theme.of(context);
    final color = labelColor(p.label);
    return Scaffold(
      appBar: AppBar(title: Text(p.name)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Row(children: [
            ScoreBadge(score: p.score, color: color, size: 64),
            const SizedBox(width: 14),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(p.label ?? '', style: TextStyle(color: color, fontWeight: FontWeight.w700, fontSize: 16)),
                Text([p.team, if (p.seasonRank != null) 'Season rank #${p.seasonRank}'].join(' · '),
                    style: theme.textTheme.bodyMedium?.copyWith(color: theme.hintColor)),
              ]),
            ),
          ]),
          if (p.flags.isNotEmpty) ...[
            const SizedBox(height: 12),
            Wrap(spacing: 6, runSpacing: 6, children: [for (final f in p.flags) FlagChip(f)]),
          ],
          if (p.reason.isNotEmpty) ...[
            const SizedBox(height: 12),
            Text(p.reason, style: theme.textTheme.bodyLarge),
          ],
          if (p.signals.isNotEmpty) ...[
            const SizedBox(height: 20),
            Text('Why this score', style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            for (final entry in const [
              ['role', 'Role (minutes, starting)'],
              ['production', 'Production'],
              ['volume', 'Shot volume'],
              ['trend', 'Trend'],
              ['stability', 'Stability'],
            ])
              if (p.signals.containsKey(entry[0])) _SignalBar(entry[1], p.signals[entry[0]]!, color),
          ],
          const SizedBox(height: 20),
          Text('Recent games', style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          FutureBuilder<FormResult>(
            future: _future,
            builder: (context, snapshot) {
              if (snapshot.connectionState != ConnectionState.done) {
                return const Padding(padding: EdgeInsets.all(24), child: Center(child: CircularProgressIndicator()));
              }
              if (snapshot.hasError) {
                return Text(snapshot.error.toString());
              }
              return _Games(result: snapshot.data!, color: color, format: widget.state.format);
            },
          ),
        ],
      ),
    );
  }
}

class _SignalBar extends StatelessWidget {
  const _SignalBar(this.label, this.value, this.color);
  final String label;
  final double value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(children: [
        SizedBox(width: 150, child: Text(label, style: Theme.of(context).textTheme.bodySmall)),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: (value / 100).clamp(0.0, 1.0),
              minHeight: 8,
              color: color,
              backgroundColor: color.withAlpha(32),
            ),
          ),
        ),
        SizedBox(width: 36, child: Text(value.round().toString(), textAlign: TextAlign.right)),
      ]),
    );
  }
}

class _Games extends StatelessWidget {
  const _Games({required this.result, required this.color, required this.format});
  final FormResult result;
  final Color color;
  final String format;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final games = result.games;
    if (games.isEmpty) return const Text('No games found.');
    final unit = format == 'points' ? 'fantasy points' : 'category score';
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('Game value ($unit), dashed line = season average ${result.seasonAverage.toStringAsFixed(1)}',
          style: theme.textTheme.bodySmall?.copyWith(color: theme.hintColor)),
      const SizedBox(height: 8),
      Sparkline(
        values: games.map((g) => g.value).toList(),
        color: color,
        reference: result.seasonAverage,
        height: 140,
        dots: true,
      ),
      const SizedBox(height: 12),
      SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: DataTable(
          columnSpacing: 14,
          headingRowHeight: 36,
          dataRowMinHeight: 32,
          dataRowMaxHeight: 36,
          columns: const [
            DataColumn(label: Text('Date')),
            DataColumn(label: Text('Opp')),
            DataColumn(label: Text('Min'), numeric: true),
            DataColumn(label: Text('Val'), numeric: true),
            DataColumn(label: Text('PTS'), numeric: true),
            DataColumn(label: Text('REB'), numeric: true),
            DataColumn(label: Text('AST'), numeric: true),
            DataColumn(label: Text('STL'), numeric: true),
            DataColumn(label: Text('BLK'), numeric: true),
            DataColumn(label: Text('TO'), numeric: true),
          ],
          rows: [
            for (final g in games.reversed)
              DataRow(cells: [
                DataCell(Text(g.date.length >= 10 ? g.date.substring(5) : g.date)),
                DataCell(Text(g.opponent)),
                DataCell(Text('${g.minutes.round()}${g.started ? '*' : ''}')),
                DataCell(Text(g.value.toStringAsFixed(1))),
                DataCell(Text('${g.points}')),
                DataCell(Text('${g.rebounds}')),
                DataCell(Text('${g.assists}')),
                DataCell(Text('${g.steals}')),
                DataCell(Text('${g.blocks}')),
                DataCell(Text('${g.turnovers}')),
              ]),
          ],
        ),
      ),
      const SizedBox(height: 4),
      Text('* = started', style: theme.textTheme.bodySmall?.copyWith(color: theme.hintColor)),
    ]);
  }
}
