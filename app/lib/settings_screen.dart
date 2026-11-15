import 'package:flutter/material.dart';

import 'api.dart';
import 'state.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key, required this.state});
  final AppState state;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late final TextEditingController _url;
  late final TextEditingController _key;
  late double _pool;
  String? _testResult;
  bool _testing = false;

  @override
  void initState() {
    super.initState();
    _url = TextEditingController(text: widget.state.baseUrl);
    _key = TextEditingController(text: widget.state.apiKey);
    _pool = widget.state.poolCutoff.toDouble();
  }

  @override
  void dispose() {
    _url.dispose();
    _key.dispose();
    super.dispose();
  }

  Future<void> _test() async {
    setState(() {
      _testing = true;
      _testResult = null;
    });
    try {
      final json = await Api(_url.text, _key.text).get('/status');
      setState(() => _testResult =
          'Connected. ${json['games']} games, data through ${json['dataThrough'] ?? 'unknown'}.');
    } on ApiException catch (e) {
      setState(() => _testResult = e.message);
    } finally {
      setState(() => _testing = false);
    }
  }

  Future<void> _save() async {
    await widget.state.update(
      baseUrl: _url.text.trim(),
      apiKey: _key.text.trim(),
      poolCutoff: _pool.round(),
    );
    if (mounted) Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
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
          const SizedBox(height: 16),
          TextField(
            controller: _key,
            obscureText: true,
            autocorrect: false,
            decoration: const InputDecoration(
              labelText: 'API key (leave empty if the server has none)',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 16),
          Row(children: [
            FilledButton.tonal(
                onPressed: _testing ? null : _test,
                child: Text(_testing ? 'Testing…' : 'Test connection')),
          ]),
          if (_testResult != null)
            Padding(padding: const EdgeInsets.only(top: 8), child: Text(_testResult!)),
          const SizedBox(height: 28),
          Text('Waiver pool: players ranked below #${_pool.round()}',
              style: Theme.of(context).textTheme.titleSmall),
          Slider(
            value: _pool,
            min: 50,
            max: 250,
            divisions: 20,
            label: _pool.round().toString(),
            onChanged: (v) => setState(() => _pool = v),
          ),
          Text('Players ranked this high by season average are treated as owned and are not suggested.',
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: Theme.of(context).hintColor)),
          const SizedBox(height: 24),
          FilledButton(onPressed: _save, child: const Text('Save')),
        ],
      ),
    );
  }
}
