import 'package:flutter/material.dart';

import 'detail_screen.dart';
import 'models.dart';
import 'player_card.dart';
import 'state.dart';

class ListTab extends StatefulWidget {
  const ListTab({super.key, required this.state, required this.listName});
  final AppState state;
  final String listName; // sustained | hot | drop

  @override
  State<ListTab> createState() => _ListTabState();
}

class _ListTabState extends State<ListTab> with AutomaticKeepAliveClientMixin {
  Future<ListResult>? _future;
  String _window = 'sustained'; // drop list only
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
    return '${s.baseUrl}|${s.apiKey}|${s.scoringSignature}';
  }

  void _onStateChanged() {
    if (mounted && _currentSignature() != _signature) {
      setState(_load);
    }
  }

  void _load() {
    _signature = _currentSignature();
    _future = widget.state.configured ? _fetch() : null;
  }

  Future<ListResult> _fetch() async {
    final s = widget.state;
    final json = await s.api.post('/lists/${widget.listName}', {
      ...s.scoringBody,
      'limit': 60,
      if (widget.listName == 'drop') 'window': _window,
    });
    return ListResult.fromJson(json);
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
    final future = _future;
    if (future == null) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text('Enter your server address in Settings (top right) to load players.',
              textAlign: TextAlign.center),
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: _refresh,
      child: FutureBuilder<ListResult>(
        future: future,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return ListView(children: const [
              SizedBox(height: 120),
              Center(child: CircularProgressIndicator()),
              SizedBox(height: 16),
              Padding(
                padding: EdgeInsets.symmetric(horizontal: 32),
                child: Text('Loading… a sleeping free server can take about a minute.',
                    textAlign: TextAlign.center),
              ),
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

  Widget _content(BuildContext context, ListResult result) {
    final theme = Theme.of(context);
    final main = result.players.where((p) => !p.stash).toList();
    final stash = result.players.where((p) => p.stash).toList();
    void open(Player p) => Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => DetailScreen(state: widget.state, player: p)));

    final header = <String>[
      if (result.dataThrough != null) 'Games through ${result.dataThrough}',
      if (result.recentGames != null && result.baselineGames != null)
        'Last ${result.recentGames} games vs the ${result.baselineGames} before',
    ];

    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.only(bottom: 24),
      children: [
        if (widget.listName == 'drop')
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 10, 12, 0),
            child: Wrap(spacing: 8, children: [
              ChoiceChip(
                label: const Text('Sustained'),
                selected: _window == 'sustained',
                onSelected: (_) => setState(() {
                  _window = 'sustained';
                  _load();
                }),
              ),
              ChoiceChip(
                label: const Text('Last 3 games'),
                selected: _window == 'hot',
                onSelected: (_) => setState(() {
                  _window = 'hot';
                  _load();
                }),
              ),
            ]),
          ),
        if (header.isNotEmpty)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 10, 16, 4),
            child: Text(header.join(' · '), style: theme.textTheme.bodySmall?.copyWith(color: theme.hintColor)),
          ),
        for (final note in result.notes)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 4, 16, 4),
            child: Text(note, style: theme.textTheme.bodySmall),
          ),
        if (main.isEmpty && stash.isEmpty)
          const Padding(
            padding: EdgeInsets.all(32),
            child: Center(child: Text('No players on this list right now.')),
          ),
        for (final p in main) PlayerCard(player: p, onTap: () => open(p)),
        if (stash.isNotEmpty) ...[
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 20, 16, 4),
            child: Text('Injured – stash only',
                style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Text('Long-term injuries: only worth a roster spot if you can hold them.',
                style: theme.textTheme.bodySmall?.copyWith(color: theme.hintColor)),
          ),
          for (final p in stash) PlayerCard(player: p, onTap: () => open(p)),
        ],
      ],
    );
  }
}
