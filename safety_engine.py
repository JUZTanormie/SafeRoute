from datetime import datetime
from math import radians, sin, cos, sqrt, atan2

from location_intelligence import LocationIntelligence


class SafetyAnalyzer:

    """
    Deterministic rule-based safety analysis engine.

    This module deliberately contains only the rule-based safety
    calculation. Prototype ML is handled separately by risk_model.py.
    Keeping the two layers separate prevents duplicate ML pipelines and
    makes the final Safety Concern Score explainable.
    """

    def __init__(self, incidents, journey_type=None, journey_hour=None):
        self.incidents = incidents
        self.journey_type = journey_type
        self.journey_hour = journey_hour
        self.location_intelligence = LocationIntelligence()

    # ========================================================
    # DISTANCE CALCULATION
    # ========================================================

    def calculate_distance_km(
        self,
        latitude_1,
        longitude_1,
        latitude_2,
        longitude_2
    ):
        earth_radius = 6371.0

        lat1 = radians(latitude_1)
        lat2 = radians(latitude_2)
        delta_lat = radians(latitude_2 - latitude_1)
        delta_lon = radians(longitude_2 - longitude_1)

        a = (
            sin(delta_lat / 2) ** 2
            + cos(lat1)
            * cos(lat2)
            * sin(delta_lon / 2) ** 2
        )

        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        return earth_radius * c

    # ========================================================
    # FIND CLOSEST ROUTE SEGMENT
    # ========================================================

    def find_closest_segment(self, incident, route):
        if incident.latitude is None or incident.longitude is None:
            return None
        return self.location_intelligence.closest_segment(
            incident.latitude, incident.longitude, route.segments
        )

    # ========================================================
    # FIND RELEVANT REPORTS
    # ========================================================

    def find_relevant_reports(self, route):
        return self.location_intelligence.match_observations(self.incidents, route)

    # ========================================================
    # RECENCY
    # ========================================================

    def get_recency_weight(self, timestamp):
        try:
            report_date = datetime.strptime(
                timestamp,
                "%Y-%m-%d %H:%M"
            )
        except (TypeError, ValueError):
            return 0.2

        current_date = datetime.now()
        age = max(0, (current_date - report_date).days)

        if age <= 7:
            return 1.0
        elif age <= 30:
            return 0.7
        elif age <= 90:
            return 0.4

        return 0.2

    # ========================================================
    # DISTANCE RELEVANCE
    # ========================================================

    def get_distance_weight(self, incident):
        distance = getattr(
            incident,
            "matched_distance_km",
            None
        )

        if distance is None:
            return 1.0

        if distance <= 0.10:
            return 1.0
        elif distance <= 0.25:
            return 0.9
        elif distance <= 0.50:
            return 0.75

        return 0.6

    # ========================================================
    # CATEGORY IMPACT
    # ========================================================

    def get_category_weight(self, category):
        category_weights = {
            "Poor Lighting": 1.25,
            "Construction": 1.10,
            "Blocked Path": 1.15,
            "Road Hazard": 1.25,
            "Flooding": 1.20,
            "Traffic": 1.00,
            "Other": 1.00
        }

        return category_weights.get(
            category,
            1.00
        )

    # ========================================================
    # JOURNEY-TIME IMPACT
    # ========================================================

    def get_time_weight(self, category):
        hour = self.journey_hour

        if hour is None:
            return 1.0

        category = category.strip().title()

        if category == "Poor Lighting":
            if 21 <= hour or hour < 5:
                return 1.50
            elif 16 <= hour < 21:
                return 1.35
            elif 5 <= hour < 8:
                return 1.20
            return 0.80

        if category == "Traffic":
            if 7 <= hour < 11 or 16 <= hour < 21:
                return 1.20
            return 0.90

        if category == "Flooding":
            return 1.10

        return 1.0

    # ========================================================
    # REPEATED REPORT IMPACT
    # ========================================================

    def get_repeat_weights(self, relevant_reports):
        counts = {}

        for incident in relevant_reports:
            key = (
                incident.matched_segment,
                incident.category
            )

            counts[key] = counts.get(key, 0) + 1

        weights = {}

        for key, count in counts.items():
            weights[key] = min(
                1.0 + ((count - 1) * 0.15),
                1.45
            )

        return weights

    # ========================================================
    # REPORT CONTRIBUTION
    # ========================================================

    def calculate_report_contribution(
        self,
        incident,
        repeat_weight=1.0
    ):
        recency_weight = self.get_recency_weight(
            incident.timestamp
        )

        distance_weight = self.get_distance_weight(
            incident
        )

        category_weight = self.get_category_weight(
            incident.category
        )

        time_weight = self.get_time_weight(
            incident.category
        )

        contribution = (
            incident.severity
            * recency_weight
            * distance_weight
            * category_weight
            * time_weight
            * repeat_weight
        )

        return round(contribution, 2)

    # ========================================================
    # SAFETY SCORE
    # ========================================================

    def calculate_score(self, relevant_reports):
        if not relevant_reports:
            return 0.0

        repeat_weights = self.get_repeat_weights(
            relevant_reports
        )

        score = 0.0

        for incident in relevant_reports:
            key = (
                incident.matched_segment,
                incident.category
            )

            repeat_weight = repeat_weights.get(
                key,
                1.0
            )

            score += self.calculate_report_contribution(
                incident,
                repeat_weight
            )

        return round(score, 2)

    # ========================================================
    # ASSESSMENT
    # ========================================================

    def get_assessment(self, score):
        if score == 0:
            return "Insufficient Safety Data"
        elif score <= 3:
            return "This journey has low safety concerns."
        elif score <= 7:
            return "This journey has moderate safety concerns."

        return "This journey has significant safety concerns."

    # ========================================================
    # CONFIDENCE
    # ========================================================

    def get_confidence(self, relevant_reports):
        if not relevant_reports:
            return "Low"

        recent_reports = 0

        for incident in relevant_reports:
            if self.get_recency_weight(
                incident.timestamp
            ) >= 0.7:
                recent_reports += 1

        if len(relevant_reports) >= 4 and recent_reports >= 2:
            return "High"

        if len(relevant_reports) >= 2 or recent_reports >= 1:
            return "Moderate"

        return "Low"

    # ========================================================
    # SAFETY BRIEFING
    # ========================================================

    def generate_briefing(
        self,
        relevant_reports,
        score
    ):
        briefing = []

        if not relevant_reports:
            briefing.append(
                "No community safety reports "
                "were found for this route."
            )

            briefing.append(
                "This does not mean the route "
                "is completely safe."
            )

            briefing.append(
                "Safety data confidence: Low."
            )

            return briefing

        briefing.append(
            f"Contextual safety score: {score}"
        )

        briefing.append(
            self.get_assessment(score)
        )

        briefing.append(
            f"{len(relevant_reports)} relevant "
            f"community report(s) were found "
            f"along the route."
        )

        briefing.append(
            f"Safety data confidence: "
            f"{self.get_confidence(relevant_reports)}."
        )

        if self.journey_type:
            briefing.append(
                f"Analysis considers the planned "
                f"{self.journey_type.lower()} journey."
            )

        for incident in relevant_reports:
            segment_text = (
                incident.matched_segment
                if incident.matched_segment
                else incident.location
            )

            distance = getattr(
                incident,
                "matched_distance_km",
                None
            )

            if distance is not None:
                distance_text = (
                    f" ({distance * 1000:.0f} m from "
                    f"the route)"
                )
            else:
                distance_text = ""

            briefing.append(
                f"{incident.category} reported "
                f"near {segment_text}"
                f"{distance_text}."
            )

        briefing.append(
            "The assessment is an indicator based "
            "on available community data and is "
            "not a guarantee of safety."
        )

        return briefing
