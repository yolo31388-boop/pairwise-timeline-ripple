import pytest

from timeline.ripple import (
    Clip,
    frame_round,
    merge_gaps,
    remap_keyframes,
    ripple_delete,
    ripple_delete_many,
    transition_anchor,
)


def make_clips():
    return [
        Clip("a", "video", 0.0, 1.0),
        Clip("b", "video", 1.0, 2.0),
        Clip("c", "video", 2.0, 3.0, keyframes=[0.0, 0.5]),
        Clip("d", "audio", 2.0, 3.0),
    ]


def test_delete_shifts_later_clip_by_exact_duration():
    result = ripple_delete(make_clips(), "b")
    clip = next(item for item in result if item.name == "c")
    assert clip.start == pytest.approx(1.0)
    assert clip.end == pytest.approx(2.0)


def test_delete_does_not_shift_other_track():
    result = ripple_delete(make_clips(), "b")
    clip = next(item for item in result if item.name == "d")
    assert clip.start == pytest.approx(2.0)
    assert clip.end == pytest.approx(3.0)


def test_delete_does_not_shift_locked_clip():
    clips = make_clips()
    clips[2].locked = True
    result = ripple_delete(clips, "b")
    clip = next(item for item in result if item.name == "c")
    assert clip.start == pytest.approx(2.0)


def test_transition_anchor_returns_left_end_and_right_start():
    assert transition_anchor(make_clips(), "b", "c") == pytest.approx((1.0, 2.0))


def test_merge_gaps_closes_adjacent_gap():
    result = merge_gaps([Clip("a", "v", 0.0, 1.0), Clip("b", "v", 2.0, 3.0)])
    assert result[1].start == pytest.approx(1.0)
    assert result[1].end == pytest.approx(2.0)


def test_remap_keyframes_shifts_relative_times():
    clip = Clip("a", "v", 2.0, 3.0, keyframes=[0.0, 0.5])
    result = remap_keyframes(clip, -1.0)
    assert result.keyframes == pytest.approx([-1.0, -0.5])


def test_frame_round_rounds_to_nearest_frame():
    assert frame_round(1.6 / 24.0, 24) == pytest.approx(2.0 / 24.0)


def test_multi_delete_uses_reverse_order():
    result = ripple_delete_many(make_clips(), ["b", "c"])
    clip = next(item for item in result if item.name == "d")
    assert clip.start == pytest.approx(0.0)


def test_output_is_sorted_by_track_then_start():
    clips = [
        Clip("d", "audio", 2.0, 3.0),
        Clip("a", "video", 0.0, 1.0),
        Clip("b", "video", 1.0, 2.0),
    ]
    result = ripple_delete(clips, "b")
    assert [clip.name for clip in result] == ["a", "d"]


def test_delete_middle_shifts_only_later_clips():
    result = ripple_delete(make_clips(), "b")
    clip = next(item for item in result if item.name == "a")
    assert (clip.start, clip.end) == pytest.approx((0.0, 1.0))


def test_transition_length_recalculated_after_ripple():
    result = ripple_delete(make_clips(), "b")
    assert transition_anchor(result, "c", "d") == pytest.approx((1.0, 1.0))


def test_missing_target_raises_value_error():
    with pytest.raises(ValueError):
        ripple_delete(make_clips(), "missing")


def test_multi_delete_does_not_shift_locked_clip():
    clips = make_clips()
    clips[2].locked = True
    clips.append(Clip("e", "video", 3.0, 4.0))
    result = ripple_delete_many(clips, ["b"])
    locked = next(item for item in result if item.name == "c")
    normal = next(item for item in result if item.name == "e")
    assert locked.start == pytest.approx(2.0)
    assert normal.start == pytest.approx(2.0)


def test_transition_anchor_for_adjacent_untouched_clips():
    assert transition_anchor(make_clips(), "a", "b") == pytest.approx((1.0, 1.0))


def test_remap_keyframes_preserves_media_in():
    clip = Clip("a", "v", 2.0, 3.0, media_in=4.0, keyframes=[0.0])
    result = remap_keyframes(clip, 1.0)
    assert result.media_in == pytest.approx(4.0)
    assert result.keyframes == pytest.approx([1.0])
