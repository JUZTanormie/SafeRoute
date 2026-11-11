from collections import Counter
from datetime import datetime


class JourneyBriefingEngine:

    """
    Deterministic contextual briefing layer for SafeRoute.

    This module does not invent incidents, locations, or facts.
    It converts already-computed SafeRoute signals into a concise
    journey explanation. It can later be replaced or extended by
    an external generative model without changing the safety engine.
    """

    def generate(
        self,
        relevant_reports,
        score,
        assessment,
        confidence,
        ml_risk,
        ml_factors,
        journey_time,
        journey_type,
        route_distance,
        route_duration,
    ):
        if not relevant_reports:
            return {
                "headline": "Limited safety data available for this journey.",
                "summary": (
                    f"The planned {journey_type.lower()} journey has no relevant "
                    "community reports along the calculated route. This means "
                    "there is insufficient community data to identify route-specific "
                    "concerns; it does not mean the route is guaranteed safe."
                ),
                "priority": "LOW DATA",
                "evidence": [
                    f"Safety Concern Score: {score}/10 ({assessment})",
                    f"Data Confidence: {confidence}",
                    f"Prototype ML Risk Indicator: {ml_risk}/10",
                ],
                "recommendation": (
                    "Treat the result as an information aid and remain aware of "
                    "conditions that may not be represented in the community data."
                ),
            }

        category_counts = Counter(
            report.category
            for report in relevant_reports
        )

        category_order = sorted(
            category_counts.items(),
            key=lambda item: (-item[1], item[0])
        )

        top_categories = [
            category
            for category, _ in category_order[:2]
        ]

        category_text = " and ".join(top_categories)

        recent_count = 0
        high_severity_count = 0

        for report in relevant_reports:
            if getattr(report, "severity", 0) >= 3:
                high_severity_count += 1

            timestamp = getattr(report, "timestamp", "")
            try:
                report_date = datetime.strptime(
                    timestamp,
                    "%Y-%m-%d %H:%M"
                )
                age_days = max(
                    0,
                    (datetime.now() - report_date).days
                )
                if age_days <= 30:
                    recent_count += 1
            except (TypeError, ValueError):
                pass

        if score <= 3:
            priority = "LOW CONCERN"
        elif score <= 7:
            priority = "MODERATE CONCERN"
        else:
            priority = "HIGH CONCERN"

        summary_parts = [
            f"For the planned {journey_type.lower()} journey at {journey_time}, "
            f"SafeRoute found {len(relevant_reports)} relevant community report(s) "
            f"along the {route_distance} km route.",
            f"The main reported categories are {category_text}.",
        ]

        if recent_count:
            summary_parts.append(
                f"{recent_count} of these reports are within the last 30 days, "
                "so recent observations are part of the current assessment."
            )
        else:
            summary_parts.append(
                "No relevant report is within the last 30 days, so the available "
                "observations may not fully represent current conditions."
            )

        if high_severity_count:
            summary_parts.append(
                f"{high_severity_count} report(s) have the highest reported "
                "severity level in the current dataset."
            )

        if abs(score - ml_risk) >= 2.0:
            signal_note = (
                "The rule-based Safety Concern Score and prototype ML indicator "
                "show a noticeable difference, so the ML value should be treated "
                "as supporting context rather than a decision rule."
            )
        else:
            signal_note = (
                "The prototype ML indicator is broadly aligned with the "
                "rule-based Safety Concern Score and is shown only as supporting context."
            )

        evidence = [
            f"Safety Concern Score: {score}/10 — {assessment}",
            f"Data Confidence: {confidence}",
            f"Prototype ML Risk Indicator: {ml_risk}/10",
            f"Route: {route_distance} km • approximately {route_duration} min",
            signal_note,
        ]

        if ml_factors:
            evidence.append(
                "Prototype ML factors: " + "; ".join(ml_factors[:3])
            )

        return {
            "headline": f"{priority}: {assessment}",
            "summary": " ".join(summary_parts),
            "priority": priority,
            "evidence": evidence,
            "recommendation": (
                "Use the reported observations as situational information, "
                "especially around the highlighted categories, and remember "
                "that community data is incomplete by nature."
            ),
        }
