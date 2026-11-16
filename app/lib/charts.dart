import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'models.dart';
import 'ui.dart';

/// Simple bar chart with an optional dashed reference line, value labels and tap-to-select.
class BarChart extends StatelessWidget {
  const BarChart({
    super.key,
    required this.values,
    required this.labels,
    required this.colors,
    this.reference,
    this.referenceLabel,
    this.height = 150,
    this.selected,
    this.onSelect,
    this.decimals = 0,
  });

  final List<double> values;
  final List<String> labels;
  final List<Color> colors;
  final double? reference;
  final String? referenceLabel;
  final double height;
  final int? selected;
  final ValueChanged<int>? onSelect;
  final int decimals;

  @override
  Widget build(BuildContext context) {
    final textColor = Theme.of(context).colorScheme.onSurface;
    return LayoutBuilder(builder: (context, constraints) {
      final width = constraints.maxWidth;
      return GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTapDown: (onSelect == null || values.isEmpty)
            ? null
            : (details) {
                final slot = width / values.length;
                final index = (details.localPosition.dx / slot).floor().clamp(0, values.length - 1);
                onSelect!(index);
              },
        child: CustomPaint(
          size: Size(width, height),
          painter: _BarPainter(
            values: values,
            labels: labels,
            colors: colors,
            reference: reference,
            referenceLabel: referenceLabel,
            selected: selected,
            decimals: decimals,
            textColor: textColor,
          ),
        ),
      );
    });
  }
}

class _BarPainter extends CustomPainter {
  _BarPainter({
    required this.values,
    required this.labels,
    required this.colors,
    required this.reference,
    required this.referenceLabel,
    required this.selected,
    required this.decimals,
    required this.textColor,
  });

  final List<double> values;
  final List<String> labels;
  final List<Color> colors;
  final double? reference;
  final String? referenceLabel;
  final int? selected;
  final int decimals;
  final Color textColor;

  void _text(Canvas canvas, String text, Offset anchor,
      {double size = 10, Color? color, bool bold = false, TextAlign align = TextAlign.center}) {
    final painter = TextPainter(
      text: TextSpan(
        text: text,
        style: TextStyle(
            fontSize: size, color: color ?? textColor.withAlpha(190), fontWeight: bold ? FontWeight.w700 : null),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    final dx = align == TextAlign.right ? anchor.dx - painter.width : anchor.dx - painter.width / 2;
    painter.paint(canvas, Offset(dx, anchor.dy));
  }

  @override
  void paint(Canvas canvas, Size size) {
    if (values.isEmpty) return;
    const topPad = 16.0;
    const bottomPad = 18.0;
    final plotHeight = size.height - topPad - bottomPad;
    final all = <double>[...values, 0.0, if (reference != null) reference!];
    final hi = all.reduce(math.max);
    final lo = all.reduce(math.min);
    final span = (hi - lo) == 0 ? 1.0 : (hi - lo);
    double y(double v) => topPad + plotHeight * (1 - (v - lo) / span);

    final slot = size.width / values.length;
    final barWidth = math.min(slot * 0.62, 34.0);

    final axis = Paint()
      ..color = textColor.withAlpha(60)
      ..strokeWidth = 1;
    canvas.drawLine(Offset(0, y(0)), Offset(size.width, y(0)), axis);

    for (var i = 0; i < values.length; i++) {
      final x = slot * i + slot / 2;
      final top = math.min(y(values[i]), y(0));
      final bottom = math.max(y(values[i]), y(0));
      final rect = RRect.fromRectAndRadius(
        Rect.fromLTRB(x - barWidth / 2, top, x + barWidth / 2, math.max(bottom, top + 1)),
        const Radius.circular(3),
      );
      canvas.drawRRect(rect, Paint()..color = colors[i]);
      if (selected == i) {
        canvas.drawRRect(
            rect,
            Paint()
              ..style = PaintingStyle.stroke
              ..strokeWidth = 2
              ..color = textColor);
      }
      final valueText = values[i].toStringAsFixed(decimals);
      final labelY = values[i] >= 0 ? top - 13 : bottom + 2;
      _text(canvas, valueText, Offset(x, labelY), bold: selected == i);
      final step = slot < 34 ? 2 : 1;
      if (i % step == 0 && i < labels.length) {
        _text(canvas, labels[i], Offset(x, size.height - 14), size: 9);
      }
    }

    if (reference != null) {
      final line = Paint()
        ..color = textColor.withAlpha(150)
        ..strokeWidth = 1.2;
      final yy = y(reference!);
      for (double dx = 0; dx < size.width; dx += 8) {
        canvas.drawLine(Offset(dx, yy), Offset(math.min(dx + 4, size.width), yy), line);
      }
      if (referenceLabel != null) {
        _text(canvas, referenceLabel!, Offset(size.width - 2, yy - 12),
            size: 10, bold: true, align: TextAlign.right);
      }
    }
  }

  @override
  bool shouldRepaint(covariant _BarPainter old) => true;
}

/// Game values and minutes as two linked bar charts. Tap a bar for that game's box score line.
class GameBars extends StatefulWidget {
  const GameBars({super.key, required this.games, required this.average, required this.color, required this.unit});
  final List<GameLine> games;
  final double average;
  final Color color;
  final String unit;

  @override
  State<GameBars> createState() => _GameBarsState();
}

class _GameBarsState extends State<GameBars> {
  int? _selected;

  void _select(int i) => setState(() => _selected = (_selected == i) ? null : i);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final games = widget.games;
    final grey = theme.hintColor.withAlpha(110);
    final labels = [for (final g in games) g.date.length >= 10 ? g.date.substring(5) : g.date];
    final valueColors = [for (final g in games) g.value >= widget.average ? widget.color : grey];
    final minuteColors = [for (final g in games) g.started ? widget.color : widget.color.withAlpha(90)];
    final sel = _selected;
    final g = (sel != null && sel < games.length) ? games[sel] : null;

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('Game value (${widget.unit}) · colored = at or above season average',
          style: theme.textTheme.bodySmall?.copyWith(color: theme.hintColor)),
      const SizedBox(height: 6),
      BarChart(
        values: [for (final x in games) x.value],
        labels: labels,
        colors: valueColors,
        reference: widget.average,
        referenceLabel: 'avg ${widget.average.toStringAsFixed(1)}',
        height: 190,
        selected: _selected,
        onSelect: _select,
      ),
      const SizedBox(height: 14),
      Text('Minutes · solid = started', style: theme.textTheme.bodySmall?.copyWith(color: theme.hintColor)),
      const SizedBox(height: 6),
      BarChart(
        values: [for (final x in games) x.minutes],
        labels: labels,
        colors: minuteColors,
        height: 110,
        selected: _selected,
        onSelect: _select,
      ),
      const SizedBox(height: 10),
      Container(
        width: double.infinity,
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: theme.colorScheme.onSurface.withAlpha(18),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Text(
          g == null
              ? 'Tap a bar to see that game.'
              : '${g.date} vs ${g.opponent}: ${g.minutes.round()} min${g.started ? ' (started)' : ''} · '
                  '${g.points} pts, ${g.rebounds} reb, ${g.assists} ast, ${g.steals} stl, ${g.blocks} blk, '
                  '${g.turnovers} to · value ${g.value.toStringAsFixed(1)}',
          style: theme.textTheme.bodySmall,
        ),
      ),
    ]);
  }
}

/// Stacked bar showing how many players fall in each tier.
class TierBar extends StatelessWidget {
  const TierBar({super.key, required this.distribution});
  final Map<String, int> distribution;

  static const _order = [
    'Good catch',
    'Consider adding',
    'Watch closely',
    'Strong drop candidate',
    'Consider dropping',
    'Watch for decline',
    'Below list threshold',
  ];

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final entries = [
      for (final key in _order)
        if ((distribution[key] ?? 0) > 0) MapEntry(key, distribution[key]!),
    ];
    final total = entries.fold<int>(0, (sum, e) => sum + e.value);
    if (total == 0) return const SizedBox.shrink();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      ClipRRect(
        borderRadius: BorderRadius.circular(5),
        child: SizedBox(
          height: 10,
          child: Row(children: [
            for (final e in entries)
              Expanded(flex: e.value, child: Container(color: labelColor(e.key))),
          ]),
        ),
      ),
      const SizedBox(height: 6),
      Wrap(spacing: 12, runSpacing: 2, children: [
        for (final e in entries)
          Row(mainAxisSize: MainAxisSize.min, children: [
            Container(width: 8, height: 8, decoration: BoxDecoration(color: labelColor(e.key), shape: BoxShape.circle)),
            const SizedBox(width: 4),
            Text('${e.key == 'Below list threshold' ? 'Not listed' : e.key} ${e.value}',
                style: theme.textTheme.bodySmall),
          ]),
      ]),
    ]);
  }
}

/// A bar that grows left (negative) or right (positive) from a center line.
class DeltaBar extends StatelessWidget {
  const DeltaBar({super.key, required this.value, required this.maxAbs, required this.color});
  final double value;
  final double maxAbs;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final axis = Theme.of(context).colorScheme.onSurface.withAlpha(80);
    return SizedBox(
      height: 14,
      child: CustomPaint(painter: _DeltaPainter(value, maxAbs <= 0 ? 1 : maxAbs, color, axis), child: const SizedBox.expand()),
    );
  }
}

class _DeltaPainter extends CustomPainter {
  _DeltaPainter(this.value, this.maxAbs, this.color, this.axis);
  final double value;
  final double maxAbs;
  final Color color;
  final Color axis;

  @override
  void paint(Canvas canvas, Size size) {
    final mid = size.width / 2;
    final length = (value.abs() / maxAbs).clamp(0.0, 1.0) * mid;
    final rect = value >= 0
        ? Rect.fromLTWH(mid, 2, length, size.height - 4)
        : Rect.fromLTWH(mid - length, 2, length, size.height - 4);
    canvas.drawRRect(RRect.fromRectAndRadius(rect, const Radius.circular(3)), Paint()..color = color);
    canvas.drawLine(Offset(mid, 0), Offset(mid, size.height), Paint()..color = axis..strokeWidth = 1);
  }

  @override
  bool shouldRepaint(covariant _DeltaPainter old) =>
      old.value != value || old.maxAbs != maxAbs || old.color != color;
}
