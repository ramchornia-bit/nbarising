import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api.dart';

const Map<String, double> defaultWeights = {
  'points': 1.0,
  'rebounds': 1.2,
  'assists': 1.5,
  'steals': 3.0,
  'blocks': 3.0,
  'turnovers': -1.0,
};
const List<String> defaultCategories = [
  'points', 'rebounds', 'assists', 'steals', 'blocks', 'fg3m', 'fg_pct', 'ft_pct', 'turnovers',
];

class AppState extends ChangeNotifier {
  String baseUrl = '';
  String apiKey = '';
  String format = 'points'; // 'points' or 'categories'
  int poolCutoff = 100;
  double minRecentMinutes = 12;
  Map<String, double> pointsWeights = Map<String, double>.of(defaultWeights);
  List<String> categories = List<String>.of(defaultCategories);
  SharedPreferences? _prefs;

  bool get configured => baseUrl.trim().isNotEmpty;
  Api get api => Api(baseUrl, apiKey);

  /// Everything the server needs to score players the way this league does.
  Map<String, dynamic> get scoringBody => {
        'league_format': format,
        'pool_cutoff': poolCutoff,
        'min_recent_minutes': minRecentMinutes,
        'points_weights': pointsWeights,
        'categories': categories,
      };

  String get scoringSignature => jsonEncode(scoringBody);

  Future<void> load() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      _prefs = prefs;
      baseUrl = prefs.getString('baseUrl') ?? '';
      apiKey = prefs.getString('apiKey') ?? '';
      format = prefs.getString('format') ?? 'points';
      poolCutoff = prefs.getInt('poolCutoff') ?? 100;
      minRecentMinutes = prefs.getDouble('minRecentMinutes') ?? 12;
      final weights = prefs.getString('weights');
      if (weights != null) {
        final decoded = jsonDecode(weights);
        if (decoded is Map) {
          pointsWeights = decoded.map((k, v) => MapEntry(k.toString(), (v as num).toDouble()));
        }
      }
      final cats = prefs.getStringList('categories');
      if (cats != null && cats.isNotEmpty) categories = cats;
    } catch (_) {}
    // When the app is opened as a web page served by the API itself, use that address.
    if (baseUrl.isEmpty && kIsWeb) {
      final origin = Uri.base.origin;
      if (origin.startsWith('http') && !origin.contains('localhost')) baseUrl = origin;
    }
  }

  Future<void> update({
    String? baseUrl,
    String? apiKey,
    String? format,
    int? poolCutoff,
    double? minRecentMinutes,
    Map<String, double>? pointsWeights,
    List<String>? categories,
  }) async {
    this.baseUrl = baseUrl ?? this.baseUrl;
    this.apiKey = apiKey ?? this.apiKey;
    this.format = format ?? this.format;
    this.poolCutoff = poolCutoff ?? this.poolCutoff;
    this.minRecentMinutes = minRecentMinutes ?? this.minRecentMinutes;
    this.pointsWeights = pointsWeights ?? this.pointsWeights;
    this.categories = categories ?? this.categories;
    notifyListeners();
    try {
      final prefs = _prefs;
      if (prefs != null) {
        await prefs.setString('baseUrl', this.baseUrl);
        await prefs.setString('apiKey', this.apiKey);
        await prefs.setString('format', this.format);
        await prefs.setInt('poolCutoff', this.poolCutoff);
        await prefs.setDouble('minRecentMinutes', this.minRecentMinutes);
        await prefs.setString('weights', jsonEncode(this.pointsWeights));
        await prefs.setStringList('categories', this.categories);
      }
    } catch (_) {}
  }
}
