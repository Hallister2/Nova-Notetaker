from __future__ import annotations

from contextlib import closing
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from app.intelligence.insights import load_or_build_insights
from app.storage.meeting_store import MeetingStore
from app.workflows.meeting_processor import MeetingProcessor


INDEX_SCHEMA_VERSION = 2
CLOSED_ACTION_STATUSES = {"done", "closed"}
INDEX_DB_NAME = "meeting_index.sqlite3"


@dataclass(frozen=True)
class MeetingIndexRecord:
    folder: str
    title: str
    started_at: str
    status: str
    has_transcript: bool
    open_actions: int
    review_count: int
    dates: list[str]
    owners: list[str]
    searchable_text: str


@dataclass(frozen=True)
class MeetingSearchResult:
    folder: str
    title: str
    file_name: str
    match: str


def build_meeting_index(store: MeetingStore | None = None) -> dict:
    meeting_store = store or MeetingStore()
    records: list[MeetingIndexRecord] = []
    for folder in meeting_store.list_meetings():
        record, _documents = _build_record_and_documents(meeting_store, folder)
        if record:
            records.append(record)

    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        "records": [asdict(record) for record in records],
    }


def write_meeting_index(store: MeetingStore | None = None) -> Path:
    meeting_store = store or MeetingStore()
    index = _write_sqlite_index(meeting_store)
    path = meeting_store.meetings_root / "index.json"
    path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    return path


def read_meeting_index(store: MeetingStore | None = None) -> dict:
    meeting_store = store or MeetingStore()
    path = meeting_store.meetings_root / "index.json"
    if not path.exists():
        return build_meeting_index(meeting_store)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return build_meeting_index(meeting_store)
    if data.get("schema_version") != INDEX_SCHEMA_VERSION:
        return build_meeting_index(meeting_store)
    return data


def search_meeting_index(query: str, store: MeetingStore | None = None, limit: int = 100) -> list[MeetingSearchResult]:
    query = query.strip()
    if not query:
        return []

    meeting_store = store or MeetingStore()
    db_path = meeting_store.meetings_root / INDEX_DB_NAME
    if not db_path.exists():
        write_meeting_index(meeting_store)

    try:
        with closing(sqlite3.connect(db_path)) as conn:
            rows = conn.execute(
                """
                SELECT d.folder, m.title, d.file_name, snippet(meeting_documents_fts, 1, '', '', '...', 12)
                FROM meeting_documents_fts
                JOIN meeting_documents d ON d.id = meeting_documents_fts.rowid
                JOIN meetings m ON m.folder = d.folder
                WHERE meeting_documents_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (_fts_query(query), limit),
            ).fetchall()
    except sqlite3.Error:
        return _search_meeting_files(query, meeting_store, limit)

    return [
        MeetingSearchResult(
            folder=str(row[0]),
            title=str(row[1] or Path(str(row[0])).name),
            file_name=str(row[2]),
            match=str(row[3] or ""),
        )
        for row in rows
    ]


def _write_sqlite_index(meeting_store: MeetingStore) -> dict:
    records: list[MeetingIndexRecord] = []
    documents_indexed = 0
    db_path = meeting_store.meetings_root / INDEX_DB_NAME
    with closing(sqlite3.connect(db_path)) as conn:
        _ensure_schema(conn)
        conn.execute("DROP TABLE IF EXISTS meeting_documents_fts")
        conn.execute("DROP TABLE IF EXISTS meeting_documents")
        conn.execute("DROP TABLE IF EXISTS meetings")
        _ensure_schema(conn)
        for folder in meeting_store.list_meetings():
            record, folder_documents = _build_record_and_documents(meeting_store, folder)
            if record is None:
                continue
            records.append(record)
            conn.execute(
                """
                INSERT INTO meetings (
                    folder, title, started_at, status, has_transcript,
                    open_actions, review_count, dates_json, owners_json, modified_ns
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.folder,
                    record.title,
                    record.started_at,
                    record.status,
                    int(record.has_transcript),
                    record.open_actions,
                    record.review_count,
                    json.dumps(record.dates),
                    json.dumps(record.owners),
                    _folder_modified_ns(folder),
                ),
            )
            for file_name, body in folder_documents:
                cursor = conn.execute(
                    "INSERT INTO meeting_documents (folder, file_name, body) VALUES (?, ?, ?)",
                    (record.folder, file_name, body),
                )
                conn.execute(
                    "INSERT INTO meeting_documents_fts (rowid, title, body) VALUES (?, ?, ?)",
                    (cursor.lastrowid, record.title, body),
                )
                documents_indexed += 1
        conn.commit()

    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        "records": [asdict(record) for record in records],
        "documents_indexed": documents_indexed,
        "sqlite_path": str(db_path),
    }


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS meetings (
            folder TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            started_at TEXT NOT NULL,
            status TEXT NOT NULL,
            has_transcript INTEGER NOT NULL,
            open_actions INTEGER NOT NULL,
            review_count INTEGER NOT NULL,
            dates_json TEXT NOT NULL,
            owners_json TEXT NOT NULL,
            modified_ns INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS meeting_documents (
            id INTEGER PRIMARY KEY,
            folder TEXT NOT NULL,
            file_name TEXT NOT NULL,
            body TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS meeting_documents_fts
        USING fts5(title, body)
        """
    )


def _build_record_and_documents(meeting_store: MeetingStore, folder: Path) -> tuple[MeetingIndexRecord | None, list[tuple[str, str]]]:
    try:
        metadata = meeting_store.read_metadata(folder)
        insights = load_or_build_insights(folder)
    except Exception:
        return None, []

    notes_text = _read_text(folder / "notes.md")
    transcript_text = _read_text(folder / "transcript.md")
    usable_transcript = MeetingProcessor._usable_existing_transcript_text(transcript_text)
    open_actions = sum(1 for item in insights.actions if item.status.lower() not in CLOSED_ACTION_STATUSES)
    review_count = len(insights.quality_warnings) + len(insights.warnings)
    record = MeetingIndexRecord(
        folder=str(folder),
        title=metadata.title or folder.name,
        started_at=metadata.started_at,
        status=metadata.status,
        has_transcript=bool(usable_transcript.strip()),
        open_actions=open_actions,
        review_count=review_count,
        dates=[item.date_label or item.text for item in insights.dates],
        owners=sorted({item.owner for item in insights.actions if item.owner and item.owner.lower() != "unknown"}),
        searchable_text=" ".join([metadata.title or folder.name, _preview_text(notes_text), _preview_text(transcript_text)]).lower(),
    )
    documents = [
        ("notes.md", notes_text),
        ("transcript.md", transcript_text),
        ("metadata", " ".join([record.title, " ".join(record.owners), " ".join(record.dates)])),
    ]
    return record, documents


def _search_meeting_files(query: str, meeting_store: MeetingStore, limit: int) -> list[MeetingSearchResult]:
    results: list[MeetingSearchResult] = []
    lowered = query.lower()
    for folder in meeting_store.list_meetings():
        try:
            metadata = meeting_store.read_metadata(folder)
            title = metadata.title or folder.name
        except Exception:
            title = folder.name
        for file_name in ("notes.md", "transcript.md"):
            path = folder / file_name
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                plain = line.strip()
                if lowered in plain.lower() or lowered in title.lower():
                    results.append(MeetingSearchResult(str(folder), title, file_name, plain[:220] or title))
                    break
            if len(results) >= limit:
                return results
    return results


def _fts_query(query: str) -> str:
    terms = [term for term in query.replace('"', " ").split() if term]
    return " OR ".join(f'"{term}"' for term in terms) or '""'


def _preview_text(text: str, limit: int = 2000) -> str:
    return " ".join(text.split())[:limit]


def _folder_modified_ns(folder: Path) -> int:
    mtimes = [folder.stat().st_mtime_ns]
    for file_name in ("metadata.json", "notes.md", "transcript.md", "insights.json"):
        path = folder / file_name
        if path.exists():
            mtimes.append(path.stat().st_mtime_ns)
    return max(mtimes)


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")
