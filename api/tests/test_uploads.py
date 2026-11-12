"""Multipart uploads and single-use upload links against real routes and SQLite."""

import hashlib
import sys
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from uuid import UUID

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from app.api.routes import auth, entries, uploads
from app.core.config import AuthMode, settings
from app.core.timeutils import utcnow
from app.db.database import Base, get_db
from app.models.entry import Entry, SourceType
from app.models.personal_access_token import PersonalAccessToken
from app.models.project import Project, ProjectMember, ProjectRole
from app.models.upload_session import UploadSession
from app.models.user import User
from app.services import upload_session_service
from app.services.pat_service import ALL_PAT_PERMISSIONS, PATService, hash_pat
from app.services.upload_service import (
    clean_filename,
    file_extension,
    storage_content_type,
)
from app.services.upload_session_service import UploadSessionService


@compiles(PGUUID, "sqlite")
def sqlite_uuid(type_, compiler, **kwargs):
    return "CHAR(32)"


class FakeS3:
    """Stands in for S3Service; records stored objects."""

    def __init__(self):
        self.objects = {}
        self.fail = False

    def __call__(self):
        return self

    def upload_file(self, fileobj, key, content_type=None):
        if self.fail:
            return False
        self.objects[key] = (fileobj.read(), content_type)
        return True

    def delete_file(self, key):
        self.objects.pop(key, None)
        return True


class UploadTestCase(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = create_engine(
            f"sqlite:///{self.temp.name}/test.db",
            connect_args={"check_same_thread": False},
        )
        self.addCleanup(self.engine.dispose)
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)
        with self.session() as db:
            alice = User(email="alice@test", display_name="Alice")
            bob = User(email="bob@test", display_name="Bob")
            db.add_all([alice, bob])
            db.flush()
            self.alice_id, self.bob_id = alice.id, bob.id
            self.full = self.make_pat(db, alice.id, list(ALL_PAT_PERMISSIONS))
            self.read = self.make_pat(db, alice.id, ["entries:read"])
            self.write = self.make_pat(db, alice.id, ["entries:write"])
            self.bob = self.make_pat(db, bob.id, list(ALL_PAT_PERMISSIONS))
            project = Project(name="Shared", created_by=alice.id)
            db.add(project)
            db.flush()
            self.project_id = str(project.id)
            db.add_all(
                [
                    ProjectMember(
                        project_id=project.id,
                        user_id=alice.id,
                        role=ProjectRole.OWNER,
                    ),
                    ProjectMember(
                        project_id=project.id,
                        user_id=bob.id,
                        role=ProjectRole.EDITOR,
                    ),
                ],
            )
            db.commit()

        self.s3 = FakeS3()
        for patcher in (
            patch.object(settings, "auth_mode", AuthMode.OIDC),
            patch.object(settings, "public_base_url", "https://vv.test/"),
            patch("app.services.upload_service.S3Service", self.s3),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

        app = FastAPI()
        app.include_router(auth.router, prefix="/api/auth")
        app.include_router(uploads.router, prefix="/api")
        app.include_router(entries.router, prefix="/api/entries")

        def test_db():
            with self.session() as db:
                yield db

        app.dependency_overrides[get_db] = test_db
        self.client = TestClient(app)

    @staticmethod
    def make_pat(db, user_id, scopes):
        _, raw = PATService(db).create(
            user_id=user_id,
            name="upload test",
            permissions=scopes,
            expires_at=None,
        )
        return raw

    @staticmethod
    def auth(token):
        return {"Authorization": f"Bearer {token}"}

    def entry_count(self):
        with self.session() as db:
            return db.query(Entry).count()


class MultipartUploadTests(UploadTestCase):
    def upload(self, filename, content=b"audio-bytes", token=None, **form):
        return self.client.post(
            "/api/entries/upload",
            headers=self.auth(token or self.full),
            data={"title": "Recording", **form},
            files={"file": (filename, content, "text/html")},
        )

    def test_upload_stores_file_and_queues_entry(self):
        response = self.upload("meeting.MP3")

        self.assertEqual(response.status_code, 200, response.text)
        entry = response.json()
        self.assertEqual(entry["status"], "NEW")
        self.assertEqual(entry["filename"], "meeting.MP3")
        self.assertTrue(entry["has_audio"])
        stored, content_type = self.s3.objects[f"uploads/{entry['id']}.mp3"]
        self.assertEqual(stored, b"audio-bytes")
        # the client claimed text/html; storage keeps a type derived from the extension
        self.assertEqual(content_type, "audio/mpeg")

    def test_unsupported_format_is_a_400_not_a_500(self):
        response = self.upload("notes.txt")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Unsupported file format", response.json()["detail"])
        self.assertEqual(self.entry_count(), 0)

    def test_storage_failure_removes_the_entry(self):
        self.s3.fail = True

        response = self.upload("meeting.mp3")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.entry_count(), 0)
        self.assertEqual(self.s3.objects, {})

    def test_project_upload_needs_editor_role(self):
        with self.session() as db:
            member = (
                db.query(ProjectMember)
                .filter(ProjectMember.user_id == self.bob_id)
                .one()
            )
            member.role = ProjectRole.VIEWER
            db.commit()

        response = self.upload(
            "meeting.mp3",
            token=self.bob,
            project_id=self.project_id,
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.entry_count(), 0)


class UploadHelperTests(TestCase):
    def test_clean_filename_keeps_only_the_base_name(self):
        self.assertEqual(clean_filename("C:\\Users\\me\\talk.mp3"), "talk.mp3")
        self.assertEqual(clean_filename("../../etc/talk.mp3"), "talk.mp3")
        for bad in (None, "", "  ", "dir/", "x" * 252 + ".mp3"):
            with self.assertRaises(HTTPException) as ctx:
                clean_filename(bad)
            self.assertEqual(ctx.exception.status_code, 400)

    def test_file_extension_requires_a_supported_suffix(self):
        self.assertEqual(file_extension("a.WAV"), "wav")
        for bad in ("mp3", ".mp3", "a.txt", "a.mp3.exe"):
            with self.assertRaises(HTTPException):
                file_extension(bad)

    def test_storage_content_type_only_keeps_media_types(self):
        self.assertEqual(storage_content_type("mp3", "text/html"), "audio/mpeg")
        # an extension the platform can't map falls back to the declared type
        self.assertEqual(storage_content_type("zzz", "audio/x-foo; x=1"), "audio/x-foo")
        self.assertEqual(
            storage_content_type("zzz", "text/html"),
            "application/octet-stream",
        )


class UploadLinkTests(UploadTestCase):
    def create_link(self, token=None, **body):
        return self.client.post(
            "/api/entries/upload-sessions",
            headers=self.auth(token or self.full),
            json=body,
        )

    def link(self, **body):
        response = self.create_link(**body)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def put(self, link, content, filename=None, token=None):
        return self.client.put(
            f"/api/uploads/{link['id']}",
            params={"filename": filename} if filename else None,
            headers=self.auth(token or link["token"]),
            content=content,
        )

    def status(self, link, token=None):
        return self.client.get(
            f"/api/entries/upload-sessions/{link['id']}",
            headers=self.auth(token or self.full),
        )

    def set_link(self, link, **values):
        with self.session() as db:
            row = db.get(UploadSession, UUID(link["id"]))
            for key, value in values.items():
                setattr(row, key, value)
            db.commit()

    def test_link_upload_creates_one_entry_and_reports_it(self):
        content = b"x" * 1000
        link = self.link(
            filename="talk.mp3",
            title="Weekly sync",
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest().upper(),
            language="DE",
        )
        self.assertTrue(link["token"].startswith("vvupl_"))
        self.assertEqual(link["state"], "pending")
        self.assertEqual(
            link["upload_url"],
            f"https://vv.test/api/uploads/{link['id']}",
        )
        self.assertEqual(
            link["browser_url"],
            f"https://vv.test/upload#{link['id']}.{link['token']}",
        )
        self.assertEqual(link["max_bytes"], len(content))

        info = self.client.get(
            f"/api/uploads/{link['id']}",
            headers=self.auth(link["token"]),
        )
        self.assertEqual(info.status_code, 200)
        self.assertEqual(info.json()["title"], "Weekly sync")
        self.assertIn("mp3", info.json()["supported_formats"])
        self.assertNotIn("token", info.json())

        response = self.put(link, content)
        self.assertEqual(response.status_code, 200, response.text)
        entry = response.json()["entry"]
        self.assertEqual(response.json()["status"], "uploaded")
        self.assertEqual(entry["title"], "Weekly sync")
        self.assertEqual(entry["language"], "de")
        self.assertEqual(entry["status"], "NEW")
        self.assertEqual(entry["source_type"], "upload")
        self.assertEqual(self.s3.objects[f"uploads/{entry['id']}.mp3"][0], content)

        status = self.status(link).json()
        self.assertEqual(status["state"], "completed")
        self.assertEqual(status["entry_id"], entry["id"])

        # a retry after a lost response must not create a second entry
        again = self.put(link, content)
        self.assertEqual(again.status_code, 409)
        self.assertIn(entry["id"], again.json()["detail"])
        self.assertEqual(self.entry_count(), 1)
        with self.session() as db:
            stored = db.get(Entry, UUID(entry["id"]))
            self.assertEqual(stored.user_id, self.alice_id)
            self.assertEqual(stored.file_size_bytes, len(content))
            self.assertEqual(stored.source_type, SourceType.UPLOAD)

    def test_filename_can_be_supplied_with_the_upload(self):
        link = self.link()
        self.assertIsNone(link["filename"])

        self.assertEqual(self.put(link, b"data").status_code, 400)
        rejected = self.put(link, b"data", filename="notes.txt")
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("Unsupported file format", rejected.json()["detail"])

        response = self.put(link, b"data", filename="Board meeting.wav")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["entry"]["title"], "Board meeting")
        self.assertEqual(response.json()["entry"]["filename"], "Board meeting.wav")

    def test_bad_details_are_rejected_before_any_bytes(self):
        self.assertEqual(self.create_link(filename="notes.txt").status_code, 400)
        with patch.object(settings, "max_upload_size", 100):
            self.assertEqual(self.create_link(size_bytes=101).status_code, 400)
        self.assertEqual(self.create_link(sha256="not-a-hash").status_code, 422)
        self.assertEqual(self.entry_count(), 0)

    def test_incomplete_or_corrupted_upload_can_be_retried(self):
        content = b"0123456789"
        link = self.link(
            filename="a.mp3",
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )

        short = self.put(link, content[:5])
        self.assertEqual(short.status_code, 400)
        self.assertIn("incomplete", short.json()["detail"])
        corrupted = self.put(link, b"9876543210")
        self.assertEqual(corrupted.status_code, 400)
        self.assertIn("Checksum mismatch", corrupted.json()["detail"])
        self.assertEqual(self.status(link).json()["state"], "pending")
        self.assertEqual(self.entry_count(), 0)

        self.assertEqual(self.put(link, content).status_code, 200)

    def test_oversized_body_is_refused(self):
        with patch.object(settings, "max_upload_size", 8):
            link = self.link(filename="a.mp3")
            # declared up front
            self.assertEqual(self.put(link, b"123456789").status_code, 413)
            # chunked, no Content-Length: counted while streaming
            chunked = self.put(link, iter([b"12345", b"6789"]))
            self.assertEqual(chunked.status_code, 413)
            self.assertEqual(self.put(link, b"").status_code, 400)
            self.assertEqual(self.put(link, b"12345678").status_code, 200)

    def test_invalid_and_expired_links(self):
        link = self.link(filename="a.mp3")
        url = f"/api/uploads/{link['id']}"

        for headers in ({}, self.auth("vvupl_wrong"), self.auth(self.full)):
            self.assertEqual(
                self.client.put(url, headers=headers, content=b"x").status_code,
                401,
            )
            self.assertEqual(self.client.get(url, headers=headers).status_code, 401)
        other = self.link(filename="b.mp3")
        self.assertEqual(self.put(link, b"x", token=other["token"]).status_code, 401)

        self.set_link(link, expires_at=utcnow() - timedelta(seconds=1))
        self.assertEqual(self.put(link, b"x").status_code, 410)
        info = self.client.get(url, headers=self.auth(link["token"]))
        self.assertEqual(info.json()["state"], "expired")

    def test_link_is_bound_to_its_creators_permissions(self):
        revoked = self.link(filename="a.mp3")
        kept = self.link(token=self.write, filename="b.mp3")
        with self.session() as db:
            db.query(PersonalAccessToken).filter(
                PersonalAccessToken.token_hash == hash_pat(self.full),
            ).one().revoked_at = utcnow()
            db.commit()

        self.assertEqual(self.put(revoked, b"x").status_code, 401)
        self.assertEqual(self.put(kept, b"x").status_code, 200)

    def test_link_checks_owner_and_project_role_at_upload(self):
        project_link = self.link(
            token=self.bob,
            filename="a.mp3",
            project_id=self.project_id,
        )
        inactive_link = self.link(filename="b.mp3")
        with self.session() as db:
            member = (
                db.query(ProjectMember)
                .filter(ProjectMember.user_id == self.bob_id)
                .one()
            )
            member.role = ProjectRole.VIEWER
            db.get(User, self.alice_id).is_active = False
            db.commit()

        self.assertEqual(self.put(project_link, b"x").status_code, 403)
        self.assertEqual(self.put(inactive_link, b"x").status_code, 401)
        self.assertEqual(self.entry_count(), 0)

    def test_creating_a_project_link_needs_editor_role(self):
        with self.session() as db:
            member = (
                db.query(ProjectMember)
                .filter(ProjectMember.user_id == self.bob_id)
                .one()
            )
            member.role = ProjectRole.VIEWER
            db.commit()

        response = self.create_link(token=self.bob, project_id=self.project_id)
        self.assertEqual(response.status_code, 403)

    def test_storage_failure_releases_the_link(self):
        link = self.link(filename="a.mp3")
        self.s3.fail = True

        self.assertEqual(self.put(link, b"data").status_code, 503)
        self.assertEqual(self.entry_count(), 0)
        self.assertEqual(self.status(link).json()["state"], "pending")

        self.s3.fail = False
        self.assertEqual(self.put(link, b"data").status_code, 200)
        self.assertEqual(self.entry_count(), 1)

    def test_scopes_and_ownership(self):
        self.assertEqual(self.create_link(token=self.read).status_code, 403)
        link = self.link(token=self.write)
        self.assertEqual(self.status(link, token=self.write).status_code, 403)
        self.assertEqual(self.status(link, token=self.read).status_code, 200)
        self.assertEqual(self.status(link, token=self.bob).status_code, 404)

    def test_open_links_are_capped(self):
        with patch.object(upload_session_service, "MAX_PENDING_PER_USER", 2):
            self.link()
            used = self.link(filename="a.mp3")
            self.assertEqual(self.create_link().status_code, 429)
            self.assertEqual(self.put(used, b"x").status_code, 200)
            self.assertEqual(self.create_link().status_code, 201)

    def test_links_need_a_public_base_url(self):
        with patch.object(settings, "public_base_url", None):
            response = self.create_link()
        self.assertEqual(response.status_code, 503)
        self.assertIn("PUBLIC_BASE_URL", response.json()["detail"])

    def test_claim_is_exclusive_until_released_or_stale(self):
        link = self.link(filename="a.mp3")
        with self.session() as db:
            service = UploadSessionService(db)
            row = db.get(UploadSession, UUID(link["id"]))
            self.assertTrue(service.claim(row))
            self.assertFalse(service.claim(row))
        self.assertEqual(self.put(link, b"x").status_code, 409)

        # a request that died mid-store frees the link after a while
        self.set_link(link, claimed_at=utcnow() - timedelta(hours=1))
        self.assertEqual(self.status(link).json()["state"], "pending")
        self.assertEqual(self.put(link, b"x").status_code, 200)
