from datetime import datetime

import numpy as np
from sklearn.ensemble import RandomForestRegressor


class SafetyRiskModel:

    """
    Prototype ML risk model.

    Important:
    SafeRoute does not yet have enough validated historical
    safety outcomes to train a real-world predictive model.
    Therefore this model is trained on a synthetic prototype
    dataset.

    The ML result remains separate from the rule-based
    Safety Concern Score.
    """

    CATEGORIES = [
        "Poor Lighting",
        "Construction",
        "Blocked Path",
        "Road Hazard",
        "Flooding",
        "Traffic",
        "Other",
    ]

    FEATURE_NAMES = [
        "Report count",
        "Maximum severity",
        "Average severity",
        "Recent report ratio",
        "Very recent report ratio",
        "Average distance from route",
        "Poor lighting ratio",
        "Construction ratio",
        "Blocked path ratio",
        "Road hazard ratio",
        "Flooding ratio",
        "Traffic ratio",
        "Journey hour",
        "Nighttime",
        "Evening",
        "Lighting-time interaction",
    ]

    def __init__(self):

        self.model = RandomForestRegressor(
            n_estimators=250,
            random_state=42,
            min_samples_leaf=3,
            max_depth=10,
            n_jobs=-1,
        )

        features, targets = (
            self._build_prototype_training_data()
        )

        self.model.fit(
            features,
            targets
        )

    # ========================================================
    # PROTOTYPE TRAINING DATA
    # ========================================================

    def _build_prototype_training_data(
        self
    ):

        rng = np.random.default_rng(42)

        rows = []
        targets = []

        for _ in range(1600):

            report_count = int(
                rng.integers(0, 9)
            )

            max_severity = int(
                rng.integers(0, 4)
            )

            avg_severity = (
                rng.uniform(0.0, 3.0)
                if report_count > 0
                else 0.0
            )

            recent_ratio = (
                rng.uniform(0.0, 1.0)
                if report_count > 0
                else 0.0
            )

            very_recent_ratio = (
                rng.uniform(0.0, 1.0)
                if report_count > 0
                else 0.0
            )

            avg_distance = (
                rng.uniform(0.0, 0.75)
                if report_count > 0
                else 0.75
            )

            lighting_ratio = (
                rng.uniform(0.0, 1.0)
                if report_count > 0
                else 0.0
            )

            construction_ratio = (
                rng.uniform(0.0, 1.0)
                if report_count > 0
                else 0.0
            )

            blocked_ratio = (
                rng.uniform(0.0, 1.0)
                if report_count > 0
                else 0.0
            )

            hazard_ratio = (
                rng.uniform(0.0, 1.0)
                if report_count > 0
                else 0.0
            )

            flooding_ratio = (
                rng.uniform(0.0, 1.0)
                if report_count > 0
                else 0.0
            )

            traffic_ratio = (
                rng.uniform(0.0, 1.0)
                if report_count > 0
                else 0.0
            )

            hour = int(
                rng.integers(0, 24)
            )

            nighttime = int(
                hour >= 21
                or hour < 5
            )

            evening = int(
                16 <= hour < 21
            )

            lighting_time_interaction = (
                lighting_ratio
                * (
                    1.5
                    if nighttime
                    else (
                        1.25
                        if evening
                        else 0.8
                    )
                )
            )

            density_factor = min(
                report_count / 6.0,
                1.5
            )

            proximity_factor = max(
                0.0,
                1.0 - (
                    avg_distance / 0.75
                )
            )

            raw_risk = (
                0.9 * max_severity
                + 1.0 * avg_severity
                + 2.3 * recent_ratio
                + 1.2 * very_recent_ratio
                + 1.6 * density_factor
                + 1.8 * proximity_factor
                + 2.4 * lighting_time_interaction
                + 0.9 * flooding_ratio
                + 0.8 * hazard_ratio
                + 0.55 * construction_ratio
                + 0.55 * blocked_ratio
                + 0.45 * traffic_ratio
            )

            raw_risk += rng.normal(
                0.0,
                0.8
            )

            if report_count == 0:

                raw_risk = max(
                    0.0,
                    rng.normal(
                        0.6,
                        0.25
                    )
                )

            target = max(
                0.0,
                min(
                    10.0,
                    raw_risk
                )
            )

            rows.append([
                report_count,
                max_severity,
                avg_severity,
                recent_ratio,
                very_recent_ratio,
                avg_distance,
                lighting_ratio,
                construction_ratio,
                blocked_ratio,
                hazard_ratio,
                flooding_ratio,
                traffic_ratio,
                hour,
                nighttime,
                evening,
                lighting_time_interaction,
            ])

            targets.append(
                target
            )

        return (
            np.asarray(rows),
            np.asarray(targets)
        )

    # ========================================================
    # FEATURE EXTRACTION
    # ========================================================

    def build_route_features(
        self,
        relevant_reports,
        journey_hour
    ):

        report_count = len(
            relevant_reports
        )

        if report_count == 0:

            return np.asarray([[
                0,
                0,
                0.0,
                0.0,
                0.0,
                0.75,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                journey_hour,
                int(
                    journey_hour >= 21
                    or journey_hour < 5
                ),
                int(
                    16 <= journey_hour < 21
                ),
                0.0,
            ]])

        severities = [
            report.severity
            for report in relevant_reports
        ]

        average_severity = (
            sum(severities)
            / report_count
        )

        max_severity = max(
            severities
        )

        recent_weights = []

        for report in relevant_reports:

            timestamp = getattr(
                report,
                "timestamp",
                ""
            )

            try:

                report_date = datetime.strptime(
                    timestamp,
                    "%Y-%m-%d %H:%M"
                )

                age_days = max(
                    0,
                    (
                        datetime.now()
                        - report_date
                    ).days
                )

            except (
                TypeError,
                ValueError
            ):

                age_days = 999

            recent_weights.append(
                1.0
                if age_days <= 7
                else (
                    0.7
                    if age_days <= 30
                    else (
                        0.4
                        if age_days <= 90
                        else 0.2
                    )
                )
            )

        recent_ratio = (
            sum(
                weight >= 0.7
                for weight
                in recent_weights
            )
            / report_count
        )

        very_recent_ratio = (
            sum(
                weight >= 1.0
                for weight
                in recent_weights
            )
            / report_count
        )

        distances = []

        for report in relevant_reports:

            distance = getattr(
                report,
                "matched_distance_km",
                None
            )

            if distance is None:
                distance = 0.75

            distances.append(
                min(
                    max(
                        distance,
                        0.0
                    ),
                    0.75
                )
            )

        average_distance = (
            sum(distances)
            / len(distances)
        )

        category_count = {
            category: 0
            for category
            in self.CATEGORIES
        }

        for report in relevant_reports:

            if (
                report.category
                in category_count
            ):

                category_count[
                    report.category
                ] += 1

        def ratio(category):

            return (
                category_count[
                    category
                ]
                / report_count
            )

        lighting_ratio = ratio(
            "Poor Lighting"
        )

        construction_ratio = ratio(
            "Construction"
        )

        blocked_ratio = ratio(
            "Blocked Path"
        )

        hazard_ratio = ratio(
            "Road Hazard"
        )

        flooding_ratio = ratio(
            "Flooding"
        )

        traffic_ratio = ratio(
            "Traffic"
        )

        nighttime = int(
            journey_hour >= 21
            or journey_hour < 5
        )

        evening = int(
            16 <= journey_hour < 21
        )

        lighting_time_interaction = (
            lighting_ratio
            * (
                1.5
                if nighttime
                else (
                    1.25
                    if evening
                    else 0.8
                )
            )
        )

        return np.asarray([[
            report_count,
            max_severity,
            average_severity,
            recent_ratio,
            very_recent_ratio,
            average_distance,
            lighting_ratio,
            construction_ratio,
            blocked_ratio,
            hazard_ratio,
            flooding_ratio,
            traffic_ratio,
            journey_hour,
            nighttime,
            evening,
            lighting_time_interaction,
        ]])

    # ========================================================
    # RISK PREDICTION
    # ========================================================

    def predict_route_risk(
        self,
        relevant_reports,
        journey_hour
    ):

        features = (
            self.build_route_features(
                relevant_reports,
                journey_hour
            )
        )

        prediction = float(
            self.model.predict(
                features
            )[0]
        )

        prediction = max(
            0.0,
            min(
                10.0,
                prediction
            )
        )

        return round(
            prediction,
            2
        )

    # ========================================================
    # EXPLAINABLE ML FACTORS
    # ========================================================
    # ========================================================
    # EXPLAINABLE ML FACTORS
    # ========================================================

    def explain_route_risk(
        self,
        relevant_reports,
        journey_hour,
        max_factors=4
    ):
        """
        Return human-readable prototype factors associated with
        the ML prediction.

        The ranking combines Random Forest feature importance,
        current feature strength, and a small contextual priority
        for journey-time-sensitive factors. It is an explanatory
        indicator only, not a causal explanation such as SHAP.
        """

        features = (
            self.build_route_features(
                relevant_reports,
                journey_hour
            )
        )[0]

        prediction = self.predict_route_risk(
            relevant_reports,
            journey_hour
        )

        if not relevant_reports:
            return {
                "risk": prediction,
                "factors": [
                    "No relevant community reports were found for the route."
                ],
            }

        normalized = [
            min(max(features[0] / 8.0, 0.0), 1.0),
            min(max(features[1] / 3.0, 0.0), 1.0),
            min(max(features[2] / 3.0, 0.0), 1.0),
            features[3],
            features[4],
            max(
                0.0,
                min(
                    1.0,
                    1.0 - (features[5] / 0.75)
                )
            ),
            features[6],
            features[7],
            features[8],
            features[9],
            features[10],
            features[11],
            0.0,
            features[13],
            features[14],
            min(max(features[15] / 1.5, 0.0), 1.0),
        ]

        importances = self.model.feature_importances_

        # Base contribution follows the trained model's feature
        # importance multiplied by the strength of that feature.
        # Small contextual boosts make journey-time effects more
        # visible when they are actually present in the route data.
        contextual_boost = {
            3: 0.05,   # recent reports
            4: 0.06,   # very recent reports
            6: 0.08,   # poor lighting
            7: 0.03,   # construction
            8: 0.03,   # blocked path
            9: 0.05,   # road hazard
            10: 0.05,  # flooding
            11: 0.02,  # traffic
            13: 0.08,  # nighttime
            14: 0.06,  # evening
            15: 0.18,  # lighting-time interaction
        }

        ranked = []

        for index, value in enumerate(normalized):
            if value <= 0:
                continue

            score = (
                float(importances[index])
                * float(value)
                + contextual_boost.get(index, 0.0)
                * float(value)
            )

            ranked.append((score, index))

        ranked.sort(reverse=True)

        factors = []
        used_indices = set()

        def add_factor(index, text):
            if index in used_indices:
                return
            factors.append(text)
            used_indices.add(index)

        # --------------------------------------------------------
        # CONTEXT-FIRST FACTORS
        # --------------------------------------------------------

        if features[6] > 0 and (features[13] == 1 or features[14] == 1):
            if features[13] == 1:
                add_factor(
                    15,
                    "Poor-lighting reports are present and the journey occurs at night."
                )
            else:
                add_factor(
                    15,
                    "Poor-lighting reports are present and the journey occurs in the evening."
                )

        elif features[6] > 0:
            add_factor(
                6,
                f"{features[6] * 100:.0f}% of reports concern poor lighting."
            )

        if features[10] > 0:
            add_factor(
                10,
                f"{features[10] * 100:.0f}% of reports concern flooding."
            )

        if features[9] > 0:
            add_factor(
                9,
                f"{features[9] * 100:.0f}% of reports concern road hazards."
            )

        # --------------------------------------------------------
        # MODEL-RANKED FACTORS
        # --------------------------------------------------------

        for _, index in ranked:
            if len(factors) >= max_factors:
                break

            if index in used_indices:
                continue

            value = features[index]
            feature_name = self.FEATURE_NAMES[index]

            if feature_name == "Report count":
                add_factor(
                    index,
                    f"{int(value)} relevant community reports are associated with the route."
                )

            elif feature_name == "Maximum severity":
                add_factor(
                    index,
                    f"Highest reported severity is {int(value)}/3."
                )

            elif feature_name == "Average severity":
                add_factor(
                    index,
                    f"Average report severity is {value:.1f}/3."
                )

            elif feature_name == "Recent report ratio":
                add_factor(
                    index,
                    f"{value * 100:.0f}% of reports are recent."
                )

            elif feature_name == "Very recent report ratio":
                add_factor(
                    index,
                    f"{value * 100:.0f}% of reports are very recent."
                )

            elif feature_name == "Average distance from route":
                add_factor(
                    index,
                    f"Reports are approximately {value * 1000:.0f} m from the route on average."
                )

            elif feature_name == "Poor lighting ratio":
                add_factor(
                    index,
                    f"{value * 100:.0f}% of reports concern poor lighting."
                )

            elif feature_name == "Construction ratio":
                add_factor(
                    index,
                    f"{value * 100:.0f}% of reports concern construction."
                )

            elif feature_name == "Blocked path ratio":
                add_factor(
                    index,
                    f"{value * 100:.0f}% of reports concern blocked paths."
                )

            elif feature_name == "Road hazard ratio":
                add_factor(
                    index,
                    f"{value * 100:.0f}% of reports concern road hazards."
                )

            elif feature_name == "Flooding ratio":
                add_factor(
                    index,
                    f"{value * 100:.0f}% of reports concern flooding."
                )

            elif feature_name == "Traffic ratio":
                add_factor(
                    index,
                    f"{value * 100:.0f}% of reports concern traffic."
                )

            elif feature_name == "Nighttime" and value == 1:
                add_factor(
                    index,
                    "The journey occurs during nighttime."
                )

            elif feature_name == "Evening" and value == 1:
                add_factor(
                    index,
                    "The journey occurs during the evening."
                )

            elif feature_name == "Lighting-time interaction" and value > 0:
                add_factor(
                    index,
                    "Lighting-related reports have higher relevance at this journey time."
                )

        if not factors:
            factors.append(
                "The prototype model found no dominant risk feature."
            )

        return {
            "risk": prediction,
            "factors": factors[:max_factors],
        }
