import 'package:flutter/material.dart';

import 'list_tab.dart';
import 'settings_screen.dart';
import 'state.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.state});
  final AppState state;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  @override
  void initState() {
    super.initState();
    if (!widget.state.configured) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _openSettings();
      });
    }
  }

  void _openSettings() {
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => SettingsScreen(state: widget.state)));
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: widget.state,
      builder: (context, _) {
        final state = widget.state;
        return DefaultTabController(
          length: 3,
          child: Scaffold(
            appBar: AppBar(
              title: const Text('Court Signal'),
              actions: [
                IconButton(
                  tooltip: 'Settings',
                  icon: const Icon(Icons.settings),
                  onPressed: _openSettings,
                ),
              ],
              bottom: PreferredSize(
                preferredSize: const Size.fromHeight(104),
                child: Column(children: [
                  SizedBox(
                    height: 56,
                    child: Center(
                      child: SegmentedButton<String>(
                        showSelectedIcon: false,
                        segments: const [
                          ButtonSegment(value: 'points', label: Text('Points league')),
                          ButtonSegment(value: 'categories', label: Text('9-category')),
                        ],
                        selected: {state.format},
                        onSelectionChanged: (s) => state.update(format: s.first),
                      ),
                    ),
                  ),
                  const TabBar(tabs: [
                    Tab(text: 'Rising'),
                    Tab(text: 'Hot (3 games)'),
                    Tab(text: 'Drop'),
                  ]),
                ]),
              ),
            ),
            body: TabBarView(children: [
              ListTab(state: state, listName: 'sustained'),
              ListTab(state: state, listName: 'hot'),
              ListTab(state: state, listName: 'drop'),
            ]),
          ),
        );
      },
    );
  }
}
