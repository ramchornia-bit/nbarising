import 'package:flutter/material.dart';

import 'home_screen.dart';
import 'state.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final state = AppState();
  await state.load();
  runApp(CourtSignalApp(state: state));
}

class CourtSignalApp extends StatelessWidget {
  const CourtSignalApp({super.key, required this.state});
  final AppState state;

  @override
  Widget build(BuildContext context) {
    const seed = Color(0xFF1B5E20);
    return MaterialApp(
      title: 'Court Signal',
      debugShowCheckedModeBanner: false,
      themeMode: ThemeMode.system,
      theme: ThemeData(colorSchemeSeed: seed, useMaterial3: true, brightness: Brightness.light),
      darkTheme: ThemeData(colorSchemeSeed: seed, useMaterial3: true, brightness: Brightness.dark),
      home: HomeScreen(state: state),
    );
  }
}
