from dataclasses import dataclass


@dataclass(frozen=True)
class Video:
    video_id: str
    title: str
    channel_title: str
    published_at: str  # ISO string
    view_count: int
    comment_count: int

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"
