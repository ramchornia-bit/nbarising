import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api.dart';

class AppState extends ChangeNotifier {
  String baseUrl = '';
  String apiKey = '';
  String format = 'points'; // 'points' or 'categories'
  int poolCutoff = 100;
  SharedPreferences? _prefs;

  bool get configured => baseUrl.trim().isNotEmpty;
  Api get api => Api(baseUrl, apiKey);

  Future<void> load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      _prefs = prefs;
      baseUrl = prefs.getString('baseUrl') ?? '';
      apiKey = prefs.getString('apiKey') ?? '';
      format = prefs.getString('format') ?? 'points';
      poolCutoff = prefs.getInt('poolCutoff') ?? 100;
    } catch (_) {}
    // When the app is opened as a web page served by the API itself, use that address.
    if (baseUrl.isEmpty && kIsWeb) {
      final origin = Uri.base.origin;
      if (origin.startsWith('http') && !origin.contains('localhost')) baseUrl = origin;
    }
  }

  Future<void> update({String? baseUrl, String? apiKey, String? format, int? poolCutoff}) async {
    this.baseUrl = baseUrl ?? this.baseUrl;
    this.apiKey = apiKey ?? this.apiKey;
    this.format = format ?? this.format;
    this.poolCutoff = poolCutoff ?? this.poolCutoff;
    notifyListeners();
    try {
      final prefs = _prefs;
      if (prefs != null) {
        await prefs.setString('baseUrl', this.baseUrl);
        await prefs.setString('apiKey', this.apiKey);
        await prefs.setString('format', this.format);
        await prefs.setInt('poolCutoff', this.poolCutoff);
      }
    } catch (_) {}
  }
}
