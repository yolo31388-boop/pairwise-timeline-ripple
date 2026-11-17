"""Timeline ripple editing.

所有时间计算都在统一的秒级时间基（timeline timebase）上进行，涉及帧对齐
时统一通过 :func:`frame_round` 按时间线帧率取整，这样不同帧率的素材混排时
音频块与视频块仍然落在同一帧网格上，不会因为各自帧率不同而错位。
"""

from dataclasses import dataclass, field, replace
import copy


@dataclass
class Clip:
    name: str
    track: str
    start: float
    end: float
    media_in: float = 0.0
    locked: bool = False
    keyframes: list = field(default_factory=list)


@dataclass
class Overlay:
    """字幕 / 贴纸等覆盖物。

    anchor_clip 为 None 时挂在时间线绝对时间上；否则跟随指定片段，
    片段被波纹平移时覆盖物带着同样的位移一起走。
    """

    name: str
    start: float
    end: float
    anchor_clip: str = None


def frame_round(seconds, fps):
    """把秒数对齐到最近的帧（四舍五入，而不是 starter 里的向下取整）。"""
    return round(float(seconds) * fps) / float(fps)


def _find_clip(clips, name):
    target = next((clip for clip in clips if clip.name == name), None)
    if target is None:
        raise ValueError(f"clip not found: {name!r}")
    return target


def _sorted(clips):
    """时间线顺序：先按起点，再按轨道、名称保证确定性。"""
    return sorted(clips, key=lambda clip: (clip.start, clip.track, clip.name))


def _shift_clip(clip, delta, fps):
    """平移一个片段：时间落在帧网格上，关键帧随片段起点一起迁移，
    media_in 保持不变（媒体入点是源素材坐标，不随时间线平移改变）。"""
    shifted = replace(
        clip,
        start=frame_round(clip.start + delta, fps),
        end=frame_round(clip.end + delta, fps),
    )
    return remap_keyframes(shifted, delta)


def _ripple_once(clips, target, fps, same_track_only):
    """执行一次波纹删除的单步运算。

    same_track_only=True  （单选删除）：只影响目标所在轨道；
    same_track_only=False （多选删除的每一步）：整条时间线一起收缩，
    否则其它轨道上的音频/视频块不会跟随多选区间移动。
    锁定片段在两种模式下都跳过，锁定轨道上的片段绝不被波纹带动。
    """
    duration = frame_round(target.end - target.start, fps)
    delta = -duration
    output = []
    for clip in clips:
        if clip.name == target.name:
            continue
        if clip.locked:
            output.append(clip)
            continue
        if same_track_only and clip.track != target.track:
            output.append(clip)
            continue
        # 位于删除区间之前的片段不动；同起点或之后的片段前移（多选时这是
        # 跨轨道的全局收缩，因此异轨同起点块也会跟随，保证音频/视频网格
        # 仍然对齐）。
        if clip.start < target.start:
            output.append(clip)
            continue
        output.append(_shift_clip(clip, delta, fps))
    return _sorted(output)


def ripple_delete(clips, target_name, fps=24):
    """波纹删除单个片段：同轨道后续片段整体前移，其它轨道不受影响。"""
    target = _find_clip(clips, target_name)
    return _ripple_once(clips, target, fps, same_track_only=True)


def ripple_delete_many(clips, target_names, fps=24):
    """多选波纹删除。

    必须按时间倒序逐个处理：先删后面的片段，再删前面的，这样每一步的
    位移都基于当前最新坐标累计，正序处理会让后面区间的偏移量算错。
    每一步都是跨轨道的全局收缩，锁定片段始终跳过。
    """
    targets = [_find_clip(clips, name) for name in target_names]
    ordered = sorted(targets, key=lambda clip: clip.start, reverse=True)
    current = list(clips)
    for target in ordered:
        current_target = _find_clip(current, target.name)
        current = _ripple_once(
            current, current_target, fps, same_track_only=False
        )
    return current


def merge_gaps(clips):
    """合并同轨道上相邻片段之间的空白间隙，使片段首尾相接。

    按轨道分组后沿时间轴压实：每个未锁定片段移动到前一个片段的 end；
    锁定片段保持原位，并作为后续片段压实的新边界，避免压到锁定内容。
    """
    tracks = {}
    for clip in clips:
        tracks.setdefault(clip.track, []).append(clip)

    result = []
    for track, track_clips in tracks.items():
        cursor = None
        for clip in sorted(track_clips, key=lambda c: c.start):
            if cursor is None:
                cursor = clip.start
            if clip.locked:
                result.append(clip)
                cursor = max(cursor, clip.end)
                continue
            if clip.start > cursor:
                duration = clip.end - clip.start
                moved = replace(clip, start=cursor, end=cursor + duration)
                result.append(moved)
                cursor = moved.end
            else:
                result.append(clip)
                cursor = max(cursor, clip.end)
    return _sorted(result)


def transition_anchor(clips, left_name, right_name):
    """返回转场在时间线上的 (起点, 终点) 锚点窗口。

    - 两个片段不在同一轨道时不存在真正的交叉转场，退化为挂在左片段
      起点上的零长度锚点；
    - 同轨相邻时，转场右边界就是切点（右片段 start）；左边界回退到
      同轨前驱片段的 end——没有前驱（左片段是轨道上第一个片段）时
      退化为切点处的零长度锚点。
    波纹后相邻片段位置变化，锚点按新坐标重算；媒体入点不在这里修改，
    由调用方保持 media_in 不变，避免长度变化后出现重复帧。
    """
    left = _find_clip(clips, left_name)
    right = _find_clip(clips, right_name)

    if left.track != right.track:
        return (left.start, left.start)

    cut = right.start
    previous = None
    for clip in clips:
        if clip.track != left.track:
            continue
        if clip.name in (left.name, right.name):
            continue
        if clip.end <= left.start and (
            previous is None or clip.end > previous.end
        ):
            previous = clip

    if previous is None:
        return (cut, cut)
    return (previous.end, cut)


def remap_keyframes(clip, delta):
    """关键帧按相对片段起点的时间整体平移，media_in 等其它字段保持不变。"""
    return replace(
        clip, keyframes=[frame_time + delta for frame_time in clip.keyframes]
    )


def remap_overlay(overlay, delta):
    """覆盖物（字幕/贴纸）随锚点迁移：绝对时间锚点同样按 delta 平移。"""
    return replace(overlay, start=overlay.start + delta, end=overlay.end + delta)


def remap_overlays(overlays, before, after):
    """波纹后重算所有覆盖物位置。

    挂在片段上的覆盖物跟随该片段的位移；挂在时间线绝对时间上的覆盖物
    按其所在时间区间实际被收缩掉的时长平移。
    """
    before_by_name = {clip.name: clip for clip in before}
    after_by_name = {clip.name: clip for clip in after}
    remapped = []
    for overlay in overlays:
        if overlay.anchor_clip is not None and overlay.anchor_clip in after_by_name:
            old = before_by_name[overlay.anchor_clip]
            new = after_by_name[overlay.anchor_clip]
            delta = new.start - old.start
        else:
            removed = [
                clip
                for clip in before
                if clip.name not in after_by_name
                and clip.end <= overlay.start
            ]
            delta = -sum(clip.end - clip.start for clip in removed)
        remapped.append(remap_overlay(overlay, delta))
    return remapped


class UndoRedoStack:
    """撤销/重做栈，每一次编辑都压入完整深拷贝快照。

    只记录删除前的时间范围无法支撑 redo：redo 时没有完整坐标就会把
    片段位置算乱。完整快照保证 undo/redo 都是简单的状态整体替换。
    """

    def __init__(self, initial):
        self._past = [copy.deepcopy(initial)]
        self._future = []

    def commit(self, state):
        self._past.append(copy.deepcopy(state))
        self._future.clear()

    def can_undo(self):
        return len(self._past) > 1

    def can_redo(self):
        return bool(self._future)

    def undo(self):
        if not self.can_undo():
            raise IndexError("undo stack is empty")
        self._future.append(self._past.pop())
        return copy.deepcopy(self._past[-1])

    def redo(self):
        if not self.can_redo():
            raise IndexError("redo stack is empty")
        self._past.append(self._future.pop())
        return copy.deepcopy(self._past[-1])
