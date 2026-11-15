import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'models.dart';

Color labelColor(String? label) {
  switch (label) {
    case 'Good catch':
      return const Color(0xFF1B8A3E);
    case 'Consider adding':
      return const Color(0xFF0E7C86);
    case 'Watch closely':
      return const Color(0xFFB7791F);
    case 'Strong drop candidate':
      return const Color(0xFFC62828);
    case 'Consider dropping':
      return const Color(0xFFD9622B);
    case 'Watch for decline':
      return const Color(0xFFB7791F);
    case 'Injured - stash only':
      return const Color(0xFF6B5B95);
    default:
      return const Color(0xFF6B7280);
  }
}

Color flagColor(String level) {
  switch (level) {
    case 'day_to_day':
      return const Color(0xFFB7791F);
    case 'out_short':
      return const Color(0xFFD9622B);
    case 'out_long':
    case 'season_ending':
      return const Color(0xFFC62828);
    case 'out_unknown':
      return const Color(0xFF8E4A4A);
    default:
      return const Color(0xFF546E7A); // recent_absence and others
  }
}

class ScoreBadge extends StatelessWidget {
  const ScoreBadge({super.key, required this.score, required this.color, this.size = 52});
  final double score;
  final Color color;
  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: color.withAlpha(36),
        border: Border.all(color: color, width: 2),
      ),
      child: Text(
        score.round().toString(),
        style: TextStyle(fontWeight: FontWeight.w700, fontSize: size * 0.36, color: color),
      ),
    );
  }
}

class FlagChip extends StatelessWidget {
  const FlagChip(this.flag, {super.key});
  final Flag flag;

  @override
  Widget build(BuildContext context) {
    final color = flagColor(flag.level);
    final injury = flag.level != 'recent_absence';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withAlpha(30),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withAlpha(120)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(injury ? Icons.warning_amber_rounded : Icons.event_busy, size: 14, color: color),
          const SizedBox(width: 4),
          Flexible(
            child: Text(flag.text, style: TextStyle(fontSize: 12, color: color, fontWeight: FontWeight.w600)),
          ),
        ],
      ),
    );
  }
}

/// Small line chart. [reference] draws a dashed horizontal line (for example the season average).
class Sparkline extends StatelessWidget {
  const Sparkline({
    super.key,
    required this.values,
    required this.color,
    this.reference,
    this.height = 36,
    this.width,
    this.dots = false,
  });

  final List<double> values;
  final Color color;
  final double? reference;
  final double height;
  final double? width;
  final bool dots;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: height,
      width: width,
      child: CustomPaint(
        painter: _SparkPainter(values, color, reference, dots, Theme.of(context).hintColor),
        child: const SizedBox.expand(),
      ),
    );
  }
}

class _SparkPainter extends CustomPainter {
  _SparkPainter(this.values, this.color, this.reference, this.dots, this.refColor);
  final List<double> values;
  final Color color;
  final double? reference;
  final bool dots;
  final Color refColor;

  @override
  void paint(Canvas canvas, Size size) {
    if (values.isEmpty) return;
    final all = [...values, if (reference != null) reference!];
    var lo = all.reduce(math.min);
    var hi = all.reduce(math.max);
    if (hi - lo < 1e-6) {
      hi += 1;
      lo -= 1;
    }
    const pad = 5.0;
    double x(int i) =>
        values.length == 1 ? size.width / 2 : pad + (size.width - 2 * pad) * i / (values.length - 1);
    double y(double v) => pad + (size.height - 2 * pad) * (1 - (v - lo) / (hi - lo));

    if (reference != null) {
      final paint = Paint()
        ..color = refColor.withAlpha(140)
        ..strokeWidth = 1;
      final yy = y(reference!);
      for (double dx = 0; dx < size.width; dx += 8) {
        canvas.drawLine(Offset(dx, yy), Offset(math.min(dx + 4, size.width), yy), paint);
      }
    }
    final line = Paint()
      ..color = color
      ..strokeWidth = 2.2
      ..style = PaintingStyle.stroke
      ..strokeJoin = StrokeJoin.round
      ..strokeCap = StrokeCap.round;
    final path = Path();
    for (var i = 0; i < values.length; i++) {
      final p = Offset(x(i), y(values[i]));
      if (i == 0) {
        path.moveTo(p.dx, p.dy);
      } else {
        path.lineTo(p.dx, p.dy);
      }
    }
    if (values.length > 1) canvas.drawPath(path, line);
    final fill = Paint()..color = color;
    if (dots || values.length == 1) {
      for (var i = 0; i < values.length; i++) {
        canvas.drawCircle(Offset(x(i), y(values[i])), 3.2, fill);
      }
    } else {
      canvas.drawCircle(Offset(x(values.length - 1), y(values.last)), 3.2, fill);
    }
  }

  @override
  bool shouldRepaint(covariant _SparkPainter old) =>
      old.values != values || old.color != color || old.reference != reference || old.dots != dots;
}
