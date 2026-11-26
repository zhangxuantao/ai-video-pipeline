"""状态库：用 SQLite 记录每条视频和每个镜头的阶段状态。"""

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pipeline.episode import Episode, episode_to_json

SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    episode_id TEXT PRIMARY KEY,
    topic      TEXT NOT NULL,
    status     TEXT NOT NULL,
    spec_json  TEXT NOT NULL DEFAULT '',
    error      TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS shots (
    episode_id    TEXT NOT NULL REFERENCES episodes(episode_id),
    shot_no       INTEGER NOT NULL,
    narration     TEXT NOT NULL,
    image_prompt  TEXT NOT NULL,
    motion_prompt TEXT NOT NULL,
    status        TEXT NOT NULL,
    keyframe_path TEXT NOT NULL DEFAULT '',
    clip_path     TEXT NOT NULL DEFAULT '',
    voice_path    TEXT NOT NULL DEFAULT '',
    seed          INTEGER NOT NULL DEFAULT 0,
    attempts      INTEGER NOT NULL DEFAULT 0,
    error         TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (episode_id, shot_no)
);
"""

SHOT_COLUMNS = ("status", "keyframe_path", "clip_path", "voice_path", "seed", "attempts", "error")


class StoreError(LookupError):
    """状态库里找不到对应的记录。

    @author zxt
    @date 2026-11-25
    """


@dataclass(frozen=True)
class EpisodeRecord:
    """一条视频在状态库里的当前状态。

    @author zxt
    @date 2026-11-25
    """

    episode_id: str
    topic: str
    status: str
    spec_json: str
    error: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ShotRecord:
    """一个镜头在状态库里的当前状态。

    @author zxt
    @date 2026-11-25
    """

    shot_no: int
    narration: str
    image_prompt: str
    motion_prompt: str
    status: str
    keyframe_path: str
    clip_path: str
    voice_path: str
    seed: int
    attempts: int
    error: str


def _now() -> str:
    """
    @return: 当前时间，形如 2026-11-25 14:30:05
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Store:
    """SQLite 状态库。每次操作独立建立连接，后台线程和 Web 请求线程可以安全共用。

    @author zxt
    @date 2026-11-25
    """

    def __init__(self, db_path: Path):
        """
        @param db_path: 数据库文件路径，不存在时自动创建
        """
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        """
        @return: 新建的数据库连接
        """
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        # SQLite 默认不检查外键，表结构里声明的引用不会生效，这里每次连接都打开
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def create_episode(self, topic: str, episode_id: str) -> EpisodeRecord:
        """新建一条处于 created 状态的视频记录。

        @param topic: 视频主题
        @param episode_id: 视频编号
        @return: 新建的视频记录
        """
        now = _now()
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO episodes (episode_id, topic, status, created_at, updated_at) VALUES (?, ?, 'created', ?, ?)",
                (episode_id, topic, now, now),
            )
        return self.get_episode(episode_id)

    def save_script(self, episode_id: str, episode: Episode) -> None:
        """保存分镜脚本：写入整条 JSON，并重建它的镜头行。重复调用以最后一次为准。

        @param episode_id: 视频编号
        @param episode: 分镜脚本
        """
        if episode.episode_id != episode_id:
            raise ValueError(f"episode_id 不一致：路径上是 {episode_id}，脚本里是 {episode.episode_id}")
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                "UPDATE episodes SET spec_json = ?, status = 'scripted', error = '', updated_at = ? WHERE episode_id = ?",
                (episode_to_json(episode), _now(), episode_id),
            )
            if cursor.rowcount == 0:
                raise StoreError(f"找不到视频 {episode_id}")
            conn.execute("DELETE FROM shots WHERE episode_id = ?", (episode_id,))
            conn.executemany(
                "INSERT INTO shots (episode_id, shot_no, narration, image_prompt, motion_prompt, status) "
                "VALUES (?, ?, ?, ?, ?, 'pending')",
                [
                    (episode_id, shot.shot_no, shot.narration, shot.image_prompt, shot.motion_prompt)
                    for shot in episode.shots
                ],
            )

    def get_episode(self, episode_id: str) -> EpisodeRecord:
        """
        @param episode_id: 视频编号
        @return: 视频记录
        """
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM episodes WHERE episode_id = ?", (episode_id,)).fetchone()
        if row is None:
            raise StoreError(f"找不到视频 {episode_id}")
        return EpisodeRecord(**dict(row))

    def list_episodes(self) -> list[EpisodeRecord]:
        """
        @return: 全部视频记录，新创建的排在前面
        """
        with closing(self._connect()) as conn:
            rows = conn.execute("SELECT * FROM episodes ORDER BY created_at DESC, rowid DESC").fetchall()
        return [EpisodeRecord(**dict(row)) for row in rows]

    def get_shots(self, episode_id: str) -> list[ShotRecord]:
        """查询一条视频的全部镜头。

        shots 表比 ShotRecord 多一个 episode_id 列，所以这里按列名查询，不用 SELECT *。

        @param episode_id: 视频编号
        @return: 该视频的全部镜头，按镜号升序
        """
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT shot_no, narration, image_prompt, motion_prompt, status, keyframe_path, "
                "clip_path, voice_path, seed, attempts, error FROM shots WHERE episode_id = ? ORDER BY shot_no",
                (episode_id,),
            ).fetchall()
        return [ShotRecord(**dict(row)) for row in rows]

    def update_shot(self, episode_id: str, shot_no: int, **fields) -> None:
        """更新镜头的若干列，只允许改状态、产物路径、种子、尝试次数和错误信息。

        @param episode_id: 视频编号
        @param shot_no: 镜号
        @param fields: 要更新的列和值
        """
        unknown = sorted(set(fields) - set(SHOT_COLUMNS))
        if unknown:
            raise ValueError(f"不能更新这些列：{unknown}")
        if not fields:
            return
        assignments = ", ".join(f"{column} = ?" for column in fields)
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                f"UPDATE shots SET {assignments} WHERE episode_id = ? AND shot_no = ?",
                (*fields.values(), episode_id, shot_no),
            )
            if cursor.rowcount == 0:
                raise StoreError(f"找不到镜头：视频 {episode_id} 第 {shot_no} 镜")

    def set_episode_status(self, episode_id: str, status: str, error: str = "") -> None:
        """更新视频的状态；不传 error 时会把之前的错误信息清空。

        @param episode_id: 视频编号
        @param status: 新状态
        @param error: 错误信息，没有则为空串
        """
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                "UPDATE episodes SET status = ?, error = ?, updated_at = ? WHERE episode_id = ?",
                (status, error, _now(), episode_id),
            )
            if cursor.rowcount == 0:
                raise StoreError(f"找不到视频 {episode_id}")
