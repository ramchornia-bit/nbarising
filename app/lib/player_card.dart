import 'package:flutter/material.dart';

import 'models.dart';
import 'ui.dart';

class PlayerCard extends StatelessWidget {
  const PlayerCard({super.key, required this.player, required this.onTap, this.starred = false, this.onStar});
  final Player player;
  final VoidCallback onTap;
  final bool starred;
  final VoidCallback? onStar;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final color = labelColor(player.label);
    final rank = player.seasonRank;
    final details = <String>[
      if (player.team.isNotEmpty) player.team,
      if (rank != null) 'Rank #$rank',
      if (player.gamesPlayed != null) '${player.gamesPlayed} games',
    ];
    final minutes = (player.minutesRecent != null && player.minutesBaseline != null)
        ? 'Minutes ${player.minutesBaseline!.round()} → ${player.minutesRecent!.round()}'
        : null;

    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  ScoreBadge(score: player.score, color: color),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(player.name,
                            style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
                        const SizedBox(height: 2),
                        Text(details.join(' · '),
                            style: theme.textTheme.bodySmall?.copyWith(color: theme.hintColor)),
                        const SizedBox(height: 4),
                        Text(
                          player.capped ? '${player.label ?? ''} · capped' : (player.label ?? ''),
                          style: TextStyle(color: color, fontWeight: FontWeight.w700, fontSize: 13),
                        ),
                      ],
                    ),
                  ),
                  if (player.recentValues.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(left: 8),
                      child: Sparkline(values: player.recentValues, color: color, width: 72, height: 40),
                    ),
                ],
              ),
              if (player.flags.isNotEmpty) ...[
                const SizedBox(height: 10),
                Wrap(spacing: 6, runSpacing: 6, children: [for (final f in player.flags) FlagChip(f)]),
              ],
              if (player.reason.isNotEmpty) ...[
                const SizedBox(height: 10),
                Text(player.reason, style: theme.textTheme.bodyMedium),
              ],
              Row(children: [
                Expanded(
                  child: minutes == null
                      ? const SizedBox.shrink()
                      : Text(minutes, style: theme.textTheme.bodySmall?.copyWith(color: theme.hintColor)),
                ),
                if (onStar != null)
                  IconButton(
                    tooltip: starred ? 'Remove from watchlist' : 'Add to watchlist',
                    visualDensity: VisualDensity.compact,
                    icon: Icon(starred ? Icons.star : Icons.star_border,
                        color: starred ? const Color(0xFFE0A100) : theme.hintColor),
                    onPressed: onStar,
                  ),
              ]),
            ],
          ),
        ),
      ),
    );
  }
}
