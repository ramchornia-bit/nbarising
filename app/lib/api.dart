import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

class ApiException implements Exception {
  ApiException(this.message, [this.status]);
  final String message;
  final int? status;
  @override
  String toString() => message;
}

class Api {
  Api(this.baseUrl, this.apiKey);
  final String baseUrl;
  final String apiKey;

  Uri _uri(String path, Map<String, String> query) {
    var base = baseUrl.trim();
    while (base.endsWith('/')) {
      base = base.substring(0, base.length - 1);
    }
    if (!base.startsWith('http')) base = 'https://$base';
    final uri = Uri.parse('$base/api/v1$path');
    return query.isEmpty ? uri : uri.replace(queryParameters: query);
  }

  Future<Map<String, dynamic>> get(String path, [Map<String, String> query = const {}]) =>
      _send('GET', path, query, null);

  Future<Map<String, dynamic>> post(String path, Map<String, dynamic> body) =>
      _send('POST', path, const {}, body);

  Future<Map<String, dynamic>> _send(
      String method, String path, Map<String, String> query, Map<String, dynamic>? body) async {
    final headers = <String, String>{
      'Accept': 'application/json',
      if (body != null) 'Content-Type': 'application/json',
      if (apiKey.trim().isNotEmpty) 'X-API-Key': apiKey.trim(),
    };
    http.Response response;
    try {
      final uri = _uri(path, query);
      final request = method == 'POST'
          ? http.post(uri, headers: headers, body: jsonEncode(body ?? {}))
          : http.get(uri, headers: headers);
      response = await request.timeout(const Duration(seconds: 90));
    } on TimeoutException {
      throw ApiException(
          'The server took too long to answer. A free server needs about a minute to wake up. Pull down to try again.');
    } catch (_) {
      throw ApiException(
          'Cannot reach the server. Check the address in Settings and your internet connection.');
    }
    dynamic decoded;
    try {
      decoded = jsonDecode(utf8.decode(response.bodyBytes));
    } catch (_) {
      throw ApiException('Unexpected answer from the server (${response.statusCode}).',
          response.statusCode);
    }
    if (response.statusCode != 200) {
      final message = decoded is Map && decoded['error'] != null
          ? decoded['error'].toString()
          : 'Server error ${response.statusCode}';
      throw ApiException(message, response.statusCode);
    }
    return decoded as Map<String, dynamic>;
  }
}
