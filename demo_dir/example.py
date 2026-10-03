"""A small review example. This file is never executed by Looking Glass."""

def box_volume(width: float, height: float, depth: float) -> float:
    # Should we validate dimensions before multiplying?
    return width * height * depth


volume = box_volume(10, 20, 30)
print(f"Volume: {volume}")
