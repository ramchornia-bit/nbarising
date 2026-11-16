import 'package:flutter/material.dart';

import 'detail_screen.dart';
import 'models.dart';
import 'state.dart';
import 'ui.dart';

class WatchTab extends StatefulWidget {
  const WatchTab({super.key, required this.state});
  final AppState state;

  @override
  State<WatchTab> createState() => _WatchTabState();
}

class _WatchTabState extends State<WatchTab> with AutomaticKeepAliveClientMixin {
  Future<Map<String, dynamic>>? _future;
  String _signature = '';

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    widget.state.addListener(_onStateChanged);
    _load();
  }

  @override
  void dispose() {
    widget.state.removeListener(_onStateChanged);
    super.dispose();
  }

  String _currentSignature() {
    final s = widget.state;
    return '${s.baseUrl}|${s.apiKey}|${s.scoringSignature}|${s.watch.map((w) => w.id).join(',')}';
  }

  void _onStateChanged() {
    if (mounted && _currentSignature() != _signature) setState(_load);
  }

  void _load() {
    _signature = _currentSignature();
    _future = (widget.state.configured && widget.state.watch.isNotEmpty) ? _fetch() : null;
  }

  Future<Map<String, dynamic>> _fetch() async {
    final s = widget.state;
    final json = await s.api.post('/watchlist', {
      ...s.scoringBody,
      'ids': s.watch.map((w) => w.id).toList(),
    });
    // Remember this snapshot so the next data day can show what changed.
    final current = <String, Map<String, dynamic>>{};
    for (final raw in (json['players'] as List? ?? const [])) {
      if (raw is! Map) continue;
      final id = (raw['playerId'] as num?)?.toInt();
      if (id == null) continue;
      current[id.toString()] = _snapshot(Map<String, dynamic>.from(raw));
    }
    await s.recordSeen((json['dataThrough'] ?? '').toString(), current);
    return json;
  }

  Map<String, dynamic> _snapshot(Map<String, dynamic> p) {
    final best = _bestScore(p);
    final flags = (p['flags'] as List? ?? const []).whereType<Map>().toList();
    return {
      'score': best?['score'],
      'label': best?['label'],
      'injury': flags.map((f) => '${f['level']}|${f['text']}').join(';'),
    };
  }

  Map<String, dynamic>? _bestScore(Map<String, dynamic> p) {
    final a = p['sustained'];
    final b = p['hot'];
    if (a is Map && b is Map) {
      final sa = (a['score'] as num?)?.toDouble() ?? 0;
      final sb = (b['score'] as num?)?.toDouble() ?? 0;
      return Map<String, dynamic>.from(sa >= sb ? a : b);
    }
    if (a is Map) return Map<String, dynamic>.from(a);
    if (b is Map) return Map<String, dynamic>.from(b);
    return null;
  }

  Future<void> _refresh() async {
    setState(_load);
    try {
      await _future;
    } catch (_) {}
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    if (widget.state.watch.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(32),
          child: Text(
            'Tap the star on any player card, or search for a player, to follow him here. '
            'This tab shows how each player is doing and what changed since you last looked.',
            textAlign: TextAlign.center,
          ),
        ),
      );
    }
    final future = _future;
    if (future == null) {
      return const Center(child: Text('Enter your server address in Settings.'));
    }
    return RefreshIndicator(
      onRefresh: _refresh,
      child: FutureBuilder<Map<String, dynamic>>(
        future: future,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return ListView(children: const [
              SizedBox(height: 120),
              Center(child: CircularProgressIndicator()),
            ]);
          }
          if (snapshot.hasError) {
            return ListView(children: [
              const SizedBox(height: 100),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 32),
                child: Column(children: [
                  const Icon(Icons.cloud_off, size: 40),
                  const SizedBox(height: 12),
                  Text(snapshot.error.toString(), textAlign: TextAlign.center),
                  const SizedBox(height: 16),
                  FilledButton(onPressed: _refresh, child: const Text('Try again')),
                ]),
              ),
            ]);
          }
          return _content(context, snapshot.data!);
        },
      ),
    );
  }

  Widget _content(BuildContext context, Map<String, dynamic> json) {
    final players = (json['players'] as List? ?? const []).whereType<Map>().toList();
    final order = {for (var i = 0; i < widget.state.watch.length; i++) widget.state.watch[i].id: i};
    players.sort((a, b) => (order[(a['playerId'] as num?)?.toInt()] ?? 0)
        .compareTo(order[(b['playerId'] as num?)?.toInt()] ?? 0));
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.only(bottom: 24, top: 6),
      children: [
        for (final raw in players) _card(context, Map<String, dynamic>.from(raw)),
      ],
    );
  }

  double? _num(dynamic v) => v is num ? v.toDouble() : null;

  List<String> _changes(Map<String, dynamic> p) {
    final id = (p['playerId'] as num?)?.toInt().toString() ?? '';
    final before = widget.state.baseline[id];
    final now = widget.state.seen[id];
    if (before == null || now == null) return const [];
    final out = <String>[];
    final b = _num(before['score']);
    final n = _num(now['score']);
    if (b != null && n != null && (n - b).abs() >= 5) {
      out.add('Score ${b.round()} → ${n.round()}');
    } else if (b == null && n != null) {
      out.add('Now on a list: ${now['label'] ?? 'scored ${n.round()}'}');
    } else if (b != null && n == null) {
      out.add('Dropped off the lists');
    }
    final injuryBefore = (before['injury'] ?? '').toString();
    final injuryNow = (now['injury'] ?? '').toString();
    if (injuryBefore != injuryNow) {
      out.add(injuryNow.isEmpty ? 'No longer on the injury list' : 'Injury update');
    }
    return out;
  }

  Widget _card(BuildContext context, Map<String, dynamic> p) {
    final theme = Theme.of(context);
    final id = (p['playerId'] as num?)?.toInt() ?? 0;
    final name = (p['name'] ?? '').toString();
    final team = (p['team'] ?? '').toString();
    final best = _bestScore(p);
    final label = best?['label']?.toString();
    final color = label == null ? theme.colorScheme.primary : labelColor(label);
    final flags = (p['flags'] as List? ?? const [])
        .whereType<Map>()
        .map((f) => Flag.fromJson(Map<String, dynamic>.from(f)))
        .toList();
    final recent = ((p['recentValues'] as List?) ?? const []).map((v) => (v as num).toDouble()).toList();
    final season = _num(p['seasonAverage']);
    final last3 = _num(p['last3Average']);
    final last5 = _num(p['last5Average']);
    final changes = _changes(p);
    final games = (p['gamesPlayed'] as num?)?.toInt() ?? 0;
    final stats = <String>[
      if (p['seasonRank'] != null) 'Rank #${p['seasonRank']}',
      if (season != null) 'Season ${season.toStringAsFixed(1)}',
      if (last5 != null) 'Last 5 ${last5.toStringAsFixed(1)}',
      if (last3 != null) 'Last 3 ${last3.toStringAsFixed(1)}',
    ];
    final minutes = _num(p['minutesRecent']);

    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => Navigator.of(context).push(MaterialPageRoute(
            builder: (_) => DetailScreen(state: widget.state, player: Player.basic(id, name, team)))),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              if (best != null)
                Padding(
                  padding: const EdgeInsets.only(right: 12),
                  child: ScoreBadge(score: (_num(best['score']) ?? 0), color: color),
                ),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(name, style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
                  const SizedBox(height: 2),
                  Text([team, '$games games'].where((e) => e.isNotEmpty).join(' · '),
                      style: theme.textTheme.bodySmall?.copyWith(color: theme.hintColor)),
                  const SizedBox(height: 4),
                  Text(
                    label ?? 'Not on the add lists (already owned-level or too few minutes)',
                    style: TextStyle(color: color, fontWeight: FontWeight.w700, fontSize: 13),
                  ),
                ]),
              ),
              if (recent.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(left: 8),
                  child: Sparkline(values: recent, color: color, reference: season, width: 80, height: 44),
                ),
            ]),
            if (changes.isNotEmpty) ...[
              const SizedBox(height: 10),
              Wrap(spacing: 6, runSpacing: 6, children: [
                for (final c in changes)
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.primary.withAlpha(30),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: theme.colorScheme.primary.withAlpha(120)),
                    ),
                    child: Row(mainAxisSize: MainAxisSize.min, children: [
                      Icon(Icons.bolt, size: 14, color: theme.colorScheme.primary),
                      const SizedBox(width: 4),
                      Text(c, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: theme.colorScheme.primary)),
                    ]),
                  ),
              ]),
            ],
            if (flags.isNotEmpty) ...[
              const SizedBox(height: 10),
              Wrap(spacing: 6, runSpacing: 6, children: [for (final f in flags) FlagChip(f)]),
            ],
            if (best != null && (best['reason'] ?? '').toString().isNotEmpty) ...[
              const SizedBox(height: 10),
              Text(best['reason'].toString(), style: theme.textTheme.bodyMedium),
            ],
            const SizedBox(height: 8),
            Row(children: [
              Expanded(
                child: Text(
                  [...stats, if (minutes != null) '${minutes.round()} min'].join(' · '),
                  style: theme.textTheme.bodySmall?.copyWith(color: theme.hintColor),
                ),
              ),
              IconButton(
                tooltip: 'Remove from watchlist',
                visualDensity: VisualDensity.compact,
                icon: const Icon(Icons.star, color: Color(0xFFE0A100)),
                onPressed: () => widget.state.toggleWatch(id, name, team),
              ),
            ]),
          ]),
        ),
      ),
    );
  }
}
