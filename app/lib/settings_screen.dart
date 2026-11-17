import 'package:flutter/material.dart';

import 'api.dart';
import 'state.dart';

const _statLabels = {
  'points': 'Points',
  'rebounds': 'Rebounds',
  'assists': 'Assists',
  'steals': 'Steals',
  'blocks': 'Blocks',
  'turnovers': 'Turnovers',
};

const _categoryLabels = {
  'points': 'PTS',
  'rebounds': 'REB',
  'assists': 'AST',
  'steals': 'STL',
  'blocks': 'BLK',
  'turnovers': 'TO',
  'fg3m': '3PM',
  'fg_pct': 'FG%',
  'ft_pct': 'FT%',
  'fgm': 'FGM',
  'ftm': 'FTM',
};

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key, required this.state});
  final AppState state;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late final TextEditingController _url;
  late final TextEditingController _key;
  late final Map<String, TextEditingController> _weights;
  late double _pool;
  late double _poolMax;
  late double _minMinutes;
  late Set<String> _categories;
  String? _testResult;
  String? _error;
  bool _testing = false;

  @override
  void initState() {
    super.initState();
    final s = widget.state;
    _url = TextEditingController(text: s.baseUrl);
    _key = TextEditingController(text: s.apiKey);
    _pool = s.poolCutoff.toDouble();
    _poolMax = s.poolMaxRank.toDouble().clamp(150.0, 450.0);
    _minMinutes = s.minRecentMinutes;
    _categories = s.categories.toSet();
    _weights = {
      for (final k in _statLabels.keys)
        k: TextEditingController(text: _fmt(s.pointsWeights[k] ?? defaultWeights[k] ?? 0)),
    };
  }

  @override
  void dispose() {
    _url.dispose();
    _key.dispose();
    for (final c in _weights.values) {
      c.dispose();
    }
    super.dispose();
  }

  String _fmt(double v) => v == v.roundToDouble() ? v.toStringAsFixed(1) : v.toString();

  Future<void> _test() async {
    setState(() {
      _testing = true;
      _testResult = null;
    });
    String message;
    try {
      final json = await Api(_url.text, _key.text).get('/status');
      message = 'Connected. ${json['games']} games, data through ${json['dataThrough'] ?? 'unknown'}.';
    } on ApiException catch (e) {
      message = e.message;
    }
    if (!mounted) return;
    setState(() {
      _testing = false;
      _testResult = message;
    });
  }

  void _resetScoring() {
    setState(() {
      for (final k in _statLabels.keys) {
        _weights[k]!.text = _fmt(defaultWeights[k]!);
      }
      _categories = defaultCategories.toSet();
      _minMinutes = 12;
      _pool = 100;
      _poolMax = 250;
      _error = null;
    });
  }

  Future<void> _save() async {
    final weights = <String, double>{};
    for (final entry in _weights.entries) {
      final value = double.tryParse(entry.value.text.trim().replaceAll(',', '.'));
      if (value == null) {
        setState(() => _error = 'Check the number for ${_statLabels[entry.key]}.');
        return;
      }
      weights[entry.key] = value;
    }
    if (_categories.length < 3) {
      setState(() => _error = 'Pick at least 3 categories.');
      return;
    }
    // Keep the order of the list below so results are stable.
    final categories = _categoryLabels.keys.where(_categories.contains).toList();
    await widget.state.update(
      baseUrl: _url.text.trim(),
      apiKey: _key.text.trim(),
      poolCutoff: _pool.round(),
      poolMaxRank: (_poolMax < _pool + 25 ? _pool + 25 : _poolMax).round(),
      minRecentMinutes: _minMinutes,
      pointsWeights: weights,
      categories: categories,
    );
    if (mounted) Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final hint = theme.textTheme.bodySmall?.copyWith(color: theme.hintColor);
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('Server', style: theme.textTheme.titleMedium),
          const SizedBox(height: 12),
          TextField(
            controller: _url,
            keyboardType: TextInputType.url,
            autocorrect: false,
            decoration: const InputDecoration(
              labelText: 'Server address',
              hintText: 'https://your-app.onrender.com',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _key,
            obscureText: true,
            autocorrect: false,
            decoration: const InputDecoration(
              labelText: 'API key (leave empty if the server has none)',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          Row(children: [
            FilledButton.tonal(
                onPressed: _testing ? null : _test, child: Text(_testing ? 'Testing…' : 'Test connection')),
          ]),
          if (_testResult != null) Padding(padding: const EdgeInsets.only(top: 8), child: Text(_testResult!)),
          const Divider(height: 40),
          Text('Points league scoring', style: theme.textTheme.titleMedium),
          const SizedBox(height: 4),
          Text('Fantasy points per stat. Used when "Points league" is selected.', style: hint),
          const SizedBox(height: 12),
          Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              for (final entry in _statLabels.entries)
                SizedBox(
                  width: 140,
                  child: TextField(
                    controller: _weights[entry.key],
                    keyboardType: const TextInputType.numberWithOptions(decimal: true, signed: true),
                    decoration: InputDecoration(labelText: entry.value, border: const OutlineInputBorder()),
                  ),
                ),
            ],
          ),
          const Divider(height: 40),
          Text('9-category league', style: theme.textTheme.titleMedium),
          const SizedBox(height: 4),
          Text('Categories your league counts. Used when "9-category" is selected.', style: hint),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 4,
            children: [
              for (final entry in _categoryLabels.entries)
                FilterChip(
                  label: Text(entry.value),
                  selected: _categories.contains(entry.key),
                  onSelected: (on) => setState(() {
                    if (on) {
                      _categories.add(entry.key);
                    } else {
                      _categories.remove(entry.key);
                    }
                  }),
                ),
            ],
          ),
          const Divider(height: 40),
          Text('Waiver pool', style: theme.textTheme.titleMedium),
          const SizedBox(height: 8),
          Text('Available players are ranked #${_pool.round() + 1} to #${(_poolMax < _pool + 25 ? _pool + 25 : _poolMax).round()} '
              'by season average', style: theme.textTheme.bodyMedium),
          const SizedBox(height: 4),
          Text('Owned from rank #${_pool.round() + 1}: players ranked above this are treated as owned and never suggested.',
              style: hint),
          Slider(
            value: _pool,
            min: 50,
            max: 250,
            divisions: 20,
            label: _pool.round().toString(),
            onChanged: (v) => setState(() => _pool = v),
          ),
          Text('Ignore players ranked worse than #${(_poolMax < _pool + 25 ? _pool + 25 : _poolMax).round()}: '
              'nobody is worth a roster spot there.', style: hint),
          Slider(
            value: _poolMax,
            min: 150,
            max: 450,
            divisions: 30,
            label: _poolMax.round().toString(),
            onChanged: (v) => setState(() => _poolMax = v),
          ),
          const SizedBox(height: 16),
          Text('Minimum recent minutes: ${_minMinutes.round()}', style: theme.textTheme.bodyMedium),
          Slider(
            value: _minMinutes,
            min: 5,
            max: 25,
            divisions: 20,
            label: _minMinutes.round().toString(),
            onChanged: (v) => setState(() => _minMinutes = v),
          ),
          Text('Add lists skip players who play fewer minutes than this.', style: hint),
          const SizedBox(height: 24),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Text(_error!, style: TextStyle(color: theme.colorScheme.error)),
            ),
          Row(children: [
            Expanded(child: FilledButton(onPressed: _save, child: const Text('Save'))),
            const SizedBox(width: 12),
            OutlinedButton(onPressed: _resetScoring, child: const Text('Reset scoring')),
          ]),
        ],
      ),
    );
  }
}
