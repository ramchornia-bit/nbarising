import 'package:flutter/material.dart';

import 'api.dart';
import 'detail_screen.dart';
import 'models.dart';
import 'state.dart';

class SearchScreen extends StatefulWidget {
  const SearchScreen({super.key, required this.state});
  final AppState state;

  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  final _controller = TextEditingController();
  List<Player> _results = [];
  String? _error;
  bool _loading = false;
  int _requestId = 0;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _search(String text) async {
    final query = text.trim();
    final id = ++_requestId;
    if (query.length < 2) {
      setState(() {
        _results = [];
        _error = null;
        _loading = false;
      });
      return;
    }
    setState(() => _loading = true);
    try {
      final json = await widget.state.api.get('/players', {'q': query});
      if (!mounted || id != _requestId) return;
      final list = (json['players'] as List?) ?? const [];
      setState(() {
        _results = list
            .whereType<Map>()
            .map((p) => Player.basic((p['playerId'] as num?)?.toInt() ?? 0,
                (p['name'] ?? '').toString(), (p['team'] ?? '').toString()))
            .toList();
        _error = null;
        _loading = false;
      });
    } on ApiException catch (e) {
      if (!mounted || id != _requestId) return;
      setState(() {
        _error = e.message;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: TextField(
          controller: _controller,
          autofocus: true,
          autocorrect: false,
          decoration: const InputDecoration(hintText: 'Search any player', border: InputBorder.none),
          onChanged: _search,
        ),
      ),
      body: _error != null
          ? Center(child: Padding(padding: const EdgeInsets.all(24), child: Text(_error!)))
          : ListView(children: [
              if (_loading) const LinearProgressIndicator(),
              for (final p in _results)
                ListTile(
                  title: Text(p.name),
                  subtitle: Text(p.team),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () => Navigator.of(context).push(MaterialPageRoute(
                      builder: (_) => DetailScreen(state: widget.state, player: p))),
                ),
              if (!_loading && _results.isEmpty && _controller.text.trim().length >= 2)
                const Padding(padding: EdgeInsets.all(24), child: Center(child: Text('No players found.'))),
            ]),
    );
  }
}
