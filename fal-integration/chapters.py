from dataclasses import dataclass


@dataclass
class Chapter:
    """A chapter of a speech mapped to a video generation prompt."""
    number: int
    title: str
    speech_text: str
    video_prompt: str


# ---------------------------------------------------------------------------
# Example: a short motivational speech split into 4 chapters.
# Each chapter has the original speech text and a corresponding animation
# prompt that describes the visual scene to generate.
# ---------------------------------------------------------------------------

EXAMPLE_SPEECH_CHAPTERS: list[Chapter] = [
    Chapter(
        number=1,
        title="The Spark",
        speech_text=(
            "Every great journey begins with a single moment of courage. "
            "A decision to step beyond what is comfortable and into the unknown. "
            "That spark, however small, is the beginning of transformation."
        ),
        video_prompt=(
            "CG animation style, a small glowing ember floats in a vast dark "
            "void, slowly growing brighter. Particles of light begin swirling "
            "around it, forming the silhouette of a person standing at the edge "
            "of a cliff overlooking an endless ocean at dawn. Warm golden tones, "
            "cinematic lighting, inspired by Pixar animation. [Zoom in]"
        ),
    ),
    Chapter(
        number=2,
        title="The Climb",
        speech_text=(
            "The path is never straight. There will be storms that test your "
            "resolve, mountains that seem impossible to climb. But every step "
            "forward, no matter how small, carries you closer to who you are "
            "meant to become."
        ),
        video_prompt=(
            "CG animation style, an animated character climbs a steep rocky "
            "mountain during a thunderstorm. Rain pours down, lightning flashes "
            "in the background. The character slips but grabs hold and keeps "
            "pulling upward with determination. Dark dramatic clouds, stylized "
            "3D animation with cel-shading, vibrant storm colors. [Tilt up]"
        ),
    ),
    Chapter(
        number=3,
        title="The Breakthrough",
        speech_text=(
            "And then, one day, the clouds part. The struggle gives way to "
            "clarity. You reach the summit and realize the view was worth "
            "every hardship. The world stretches out before you, full of "
            "possibility."
        ),
        video_prompt=(
            "CG animation style, the same animated character reaches the "
            "mountain peak and stands triumphantly. The storm clears revealing "
            "a breathtaking panoramic landscape bathed in warm sunlight. Lush "
            "green valleys, rivers, and distant cities visible below. Golden "
            "hour lighting, sweeping cinematic camera, Pixar-quality rendering. "
            "[Pan left] [Pull out]"
        ),
    ),
    Chapter(
        number=4,
        title="The Legacy",
        speech_text=(
            "But the true victory is not in reaching the top. It is in turning "
            "back and extending your hand to those still climbing. Your story "
            "becomes their courage. Your journey lights the way for others."
        ),
        video_prompt=(
            "CG animation style, the character on the mountaintop reaches down "
            "and helps another smaller character climb up. Behind them, a long "
            "line of diverse animated characters follow the trail upward. The "
            "sun sets in the background casting long warm shadows. Emotional, "
            "hopeful atmosphere, soft orchestral mood, stylized 3D animation. "
            "[Tracking shot]"
        ),
    ),
]
