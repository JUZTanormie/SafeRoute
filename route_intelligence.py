from collections import Counter
from datetime import datetime


class RouteIntelligence:

    """
    Segment-level route intelligence built from the existing
    deterministic SafetyAnalyzer.

    This module does not create a new safety score. It identifies
    where the available community evidence is concentrated so the
    journey explanation can say which route segments deserve attention.
    """

    def analyze(self, relevant_reports, analyzer, max_segments=3):
        if not relevant_reports:
            return {
                "total_reports": 0,
                "segment_count": 0,
                "total_contribution": 0.0,
                "hotspots": [],
                "summary": "No route segments have report activity in the current dataset.",
            }

        repeat_weights = analyzer.get_repeat_weights(
            relevant_reports
        )

        grouped = {}

        for report in relevant_reports:
            segment = (
                report.matched_segment
                or report.location
                or "Unknown segment"
            )

            bucket = grouped.setdefault(
                segment,
                {
                    "reports": [],
                    "categories": Counter(),
                    "contribution": 0.0,
                    "distances": [],
                    "recent_count": 0,
                    "high_severity_count": 0,
                    "max_severity": 0,
                }
            )

            bucket["reports"].append(report)
            bucket["categories"][report.category] += 1

            key = (
                report.matched_segment,
                report.category
            )

            repeat_weight = repeat_weights.get(
                key,
                1.0
            )

            bucket["contribution"] += (
                analyzer.calculate_report_contribution(
                    report,
                    repeat_weight
                )
            )

            distance = getattr(
                report,
                "matched_distance_km",
                None
            )

            if distance is not None:
                bucket["distances"].append(distance)

            if analyzer.get_recency_weight(
                getattr(report, "timestamp", "")
            ) >= 0.7:
                bucket["recent_count"] += 1

            severity = int(
                getattr(report, "severity", 0)
            )

            bucket["max_severity"] = max(
                bucket["max_severity"],
                severity
            )

            if severity >= 3:
                bucket["high_severity_count"] += 1

        total_contribution = sum(
            bucket["contribution"]
            for bucket in grouped.values()
        )

        ordered = sorted(
            grouped.items(),
            key=lambda item: (
                -item[1]["contribution"],
                -len(item[1]["reports"]),
                item[0],
            )
        )

        hotspots = []

        for segment, bucket in ordered[:max_segments]:
            report_count = len(bucket["reports"])

            categories = [
                category
                for category, _ in sorted(
                    bucket["categories"].items(),
                    key=lambda item: (-item[1], item[0])
                )
            ]

            average_distance = None
            if bucket["distances"]:
                average_distance = round(
                    sum(bucket["distances"])
                    / len(bucket["distances"]),
                    3
                )

            share = 0.0
            if total_contribution > 0:
                share = (
                    bucket["contribution"]
                    / total_contribution
                ) * 100

            hotspots.append({
                "segment": segment,
                "report_count": report_count,
                "categories": categories,
                "contribution": round(
                    bucket["contribution"],
                    2
                ),
                "contribution_share": round(
                    share,
                    1
                ),
                "recent_count": bucket["recent_count"],
                "high_severity_count": bucket["high_severity_count"],
                "max_severity": bucket["max_severity"],
                "average_distance_km": average_distance,
            })

        if hotspots:
            top = hotspots[0]
            category_text = " and ".join(
                top["categories"][:2]
            )

            summary = (
                f"The highest concentration of route concern is near "
                f"{top['segment']}, with {top['report_count']} report(s)"
            )

            if category_text:
                summary += f" mainly involving {category_text}"

            summary += "."
        else:
            summary = (
                "No route hotspot could be identified from the available data."
            )

        return {
            "total_reports": len(relevant_reports),
            "segment_count": len(grouped),
            "total_contribution": round(
                total_contribution,
                2
            ),
            "hotspots": hotspots,
            "summary": summary,
        }
