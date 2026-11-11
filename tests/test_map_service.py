import map_service


def test_route_segments_cover_the_route():
    points = [(10.0 + index * 0.001, 78.0 + index * 0.001) for index in range(20)]
    segments = map_service.build_route_segments(points, segment_count=5)
    assert len(segments) == 5
    assert segments[0]["name"] == "Segment 1"
    assert segments[-1]["name"] == "Segment 5"
    assert all(segment["points"] for segment in segments)


def test_google_polyline_decoder_reference_case():
    points = map_service._decode_google_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@")
    assert len(points) == 3
    expected = [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]
    for actual, target in zip(points, expected):
        assert abs(actual[0] - target[0]) < 1e-4
        assert abs(actual[1] - target[1]) < 1e-4

