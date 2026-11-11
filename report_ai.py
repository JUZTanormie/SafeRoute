from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity


class ReportIntelligence:

    # Prototype category examples.
    # These are demonstration training examples, not
    # real-world safety reports.
    TRAINING_DATA = [
        ("street lights are not working", "Poor Lighting"),
        ("the road is very dark at night", "Poor Lighting"),
        ("no lights on this street", "Poor Lighting"),
        ("street lamps are broken", "Poor Lighting"),
        ("poor visibility because of darkness", "Poor Lighting"),
        ("area has very weak lighting", "Poor Lighting"),
        ("road work is happening here", "Construction"),
        ("construction work blocks part of the road", "Construction"),
        ("building work near the road", "Construction"),
        ("workers are doing construction", "Construction"),
        ("road construction is causing problems", "Construction"),
        ("pavement is blocked", "Blocked Path"),
        ("sidewalk is blocked", "Blocked Path"),
        ("pathway is not accessible", "Blocked Path"),
        ("people cannot walk through this area", "Blocked Path"),
        ("footpath is blocked by objects", "Blocked Path"),
        ("large pothole on the road", "Road Hazard"),
        ("broken road surface", "Road Hazard"),
        ("dangerous pothole", "Road Hazard"),
        ("debris is lying on the road", "Road Hazard"),
        ("road has a dangerous obstacle", "Road Hazard"),
        ("water is covering the road", "Flooding"),
        ("road is flooded", "Flooding"),
        ("heavy waterlogging here", "Flooding"),
        ("standing water on the street", "Flooding"),
        ("water has collected on the road", "Flooding"),
        ("traffic is very heavy", "Traffic"),
        ("vehicles are stuck in traffic", "Traffic"),
        ("major traffic congestion", "Traffic"),
        ("cars and buses are causing congestion", "Traffic"),
        ("traffic flow is very slow", "Traffic"),
        ("something unusual is happening here", "Other"),
        ("there is another safety issue", "Other"),
        ("general concern in this area", "Other"),
        ("unsafe condition observed", "Other"),
        ("other local problem", "Other"),
    ]

    def __init__(self):
        texts = [
            item[0]
            for item in self.TRAINING_DATA
        ]

        labels = [
            item[1]
            for item in self.TRAINING_DATA
        ]

        self.vectorizer = TfidfVectorizer(
            lowercase=True,
            ngram_range=(1, 2),
            sublinear_tf=True,
        )

        features = self.vectorizer.fit_transform(
            texts
        )

        self.model = LogisticRegression(
            max_iter=1000,
            random_state=42,
        )

        self.model.fit(
            features,
            labels
        )

    # ========================================================
    # CATEGORY PREDICTION
    # ========================================================

    def predict_category(self, description):
        description = description.strip()

        if not description:
            return {
                "category": "Other",
                "confidence": 0.0,
            }

        features = self.vectorizer.transform(
            [description]
        )

        probabilities = (
            self.model.predict_proba(features)[0]
        )

        best_index = probabilities.argmax()

        return {
            "category": self.model.classes_[
                best_index
            ],
            "confidence": float(
                probabilities[best_index]
            ),
        }

    # ========================================================
    # SEVERITY SUGGESTION
    # ========================================================

    def suggest_severity(self, description):
        text = description.lower()

        high_terms = [
            "dangerous",
            "severe",
            "major",
            "blocked completely",
            "accident",
            "crash",
            "injury",
            "impassable",
            "deep water",
            "large pothole",
        ]

        moderate_terms = [
            "poor",
            "heavy",
            "broken",
            "blocked",
            "flooded",
            "congestion",
            "dark",
            "hazard",
            "obstacle",
            "waterlogging",
        ]

        if any(
            term in text
            for term in high_terms
        ):
            return 3

        if any(
            term in text
            for term in moderate_terms
        ):
            return 2

        return 1

    # ========================================================
    # REPORT ANALYSIS
    # ========================================================

    def analyze_report(self, description):
        category_result = (
            self.predict_category(
                description
            )
        )

        return {
            "category": category_result[
                "category"
            ],
            "category_confidence": (
                category_result[
                    "confidence"
                ]
            ),
            "suggested_severity": (
                self.suggest_severity(
                    description
                )
            ),
        }

    # ========================================================
    # SIMILAR REPORT DETECTION
    # ========================================================

    def find_similar_reports(
        self,
        description,
        existing_reports,
        category=None,
        threshold=0.62,
        max_results=3,
    ):
        """
        Find possible duplicate/similar reports.

        Two TF-IDF representations are compared:
        1. Word/phrase similarity.
        2. Character-pattern similarity.

        The stronger similarity is retained. This helps with
        small wording changes such as:

        "street lights are broken"
        vs.
        "street lights broken here"

        This is a prototype similarity detector. It does not
        decide whether two reports are truly duplicates.
        """

        description = (
            description
            .strip()
        )

        if not description:
            return []

        candidates = []

        for report in existing_reports:

            report_description = (
                getattr(
                    report,
                    "description",
                    ""
                )
                or ""
            ).strip()

            if not report_description:
                continue

            report_category = (
                getattr(
                    report,
                    "category",
                    None
                )
            )

            candidates.append({
                "report": report,
                "text": report_description,
                "category_match": (
                    category is not None
                    and report_category == category
                ),
            })

        if not candidates:
            return []

        texts = [
            description
        ]

        texts.extend(
            item["text"]
            for item in candidates
        )

        try:
            word_vectorizer = (
                TfidfVectorizer(
                    lowercase=True,
                    ngram_range=(1, 2),
                    sublinear_tf=True,
                )
            )

            word_vectors = (
                word_vectorizer.fit_transform(
                    texts
                )
            )

            word_scores = cosine_similarity(
                word_vectors[0:1],
                word_vectors[1:]
            )[0]

            char_vectorizer = (
                TfidfVectorizer(
                    lowercase=True,
                    analyzer="char_wb",
                    ngram_range=(3, 6),
                    sublinear_tf=True,
                )
            )

            char_vectors = (
                char_vectorizer.fit_transform(
                    texts
                )
            )

            char_scores = cosine_similarity(
                char_vectors[0:1],
                char_vectors[1:]
            )[0]

        except ValueError:
            return []

        matches = []

        for index, item in enumerate(
            candidates
        ):
            similarity = max(
                float(word_scores[index]),
                float(char_scores[index]),
            )

            if similarity < threshold:
                continue

            category_match = (
                item["category_match"]
            )

            matches.append({
                "report": item["report"],
                "similarity": similarity,
                "category_match": (
                    category_match
                ),
                "priority": (
                    1
                    if category_match
                    else 0
                ),
            })

        matches.sort(
            key=lambda item: (
                item["priority"],
                item["similarity"],
            ),
            reverse=True,
        )

        return matches[:max_results]

    # ========================================================
    # REPORT ANALYSIS AGAINST HISTORY
    # ========================================================

    def analyze_report_against_history(
        self,
        description,
        existing_reports,
        category=None,
    ):
        analysis = self.analyze_report(
            description
        )

        similar_reports = (
            self.find_similar_reports(
                description,
                existing_reports,
                category=(
                    category
                    or analysis["category"]
                ),
            )
        )

        analysis["similar_reports"] = (
            similar_reports
        )

        return analysis
