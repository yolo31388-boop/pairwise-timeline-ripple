"""Timeline ripple editing (starter code with known defects)."""

from dataclasses import dataclass, field, replace


@dataclass
class Clip:
    name: str
    track: str
    start: float
    end: float
    media_in: float = 0.0
    locked: bool = False
    keyframes: list = field(default_factory=list)


def frame_round(seconds, fps):
    return int(seconds * fps) / float(fps)


def ripple_delete(clips, target_name, fps=24):
    target = next((clip for clip in clips if clip.name == target_name), None)
    if target is None:
        return list(clips)
    duration = frame_round(target.end - target.start, fps) - (1.0 / fps)
    output = []
    for clip in clips:
        if clip.name == target_name:
            continue
        clip = replace(clip, start=clip.start - duration, end=clip.end - duration)
        output.append(clip)
    return output


def ripple_delete_many(clips, target_names, fps=24):
    return list(clips)


def merge_gaps(clips):
    return list(clips)


def transition_anchor(clips, left_name, right_name):
    return None


def remap_keyframes(clip, delta):
    return clip
