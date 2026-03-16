"""
Tests for call recording streaming endpoint
"""

import pytest
from httpx import AsyncClient

from api.v1.routers.company.recordings import _validate_recording_url


class TestStreamRecording:
    """Tests for GET /api/v1/company/recordings/{call_id}"""

    @pytest.mark.asyncio
    async def test_recording_not_found_invalid_call(
        self, client: AsyncClient, auth_headers
    ):
        """Non-existent call returns 404."""
        response = await client.get(
            "/api/v1/company/recordings/9999999",
            headers=auth_headers
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_recording_not_found_no_record_url(
        self, client: AsyncClient, auth_headers, test_call_event
    ):
        """Call without recording URL returns 404."""
        # test_call_event has no record_url by default
        response = await client.get(
            f"/api/v1/company/recordings/{test_call_event.id}",
            headers=auth_headers
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_recording_unauthorized(self, client: AsyncClient):
        """Unauthenticated request should fail."""
        response = await client.get("/api/v1/company/recordings/123")
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_recording_operator_can_access(
        self, client: AsyncClient, operator_auth_headers, test_call_event
    ):
        """Operator with calls.read can access recordings endpoint."""
        response = await client.get(
            f"/api/v1/company/recordings/{test_call_event.id}",
            headers=operator_auth_headers
        )
        # 404 is expected since test_call_event has no record_url
        # but should NOT be 403
        assert response.status_code == 404


class TestRecordingMultiTenancy:
    """Multi-tenancy isolation for recordings"""

    @pytest.mark.asyncio
    async def test_cannot_access_other_company_recording(
        self, client: AsyncClient, active_auth_headers, test_call_event
    ):
        """Company B cannot access Company A's call recording."""
        response = await client.get(
            f"/api/v1/company/recordings/{test_call_event.id}",
            headers=active_auth_headers
        )
        assert response.status_code == 404


class TestRecordingUrlValidation:
    """Unit tests for _validate_recording_url SSRF protection"""

    def test_https_url_passes(self):
        """HTTPS URLs should pass validation."""
        # Should not raise
        _validate_recording_url("https://recordings.example.com/file.mp3")

    def test_http_url_rejected(self):
        """HTTP (non-HTTPS) URLs should be rejected."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _validate_recording_url("http://recordings.example.com/file.mp3")
        assert exc_info.value.status_code == 400

    def test_ftp_url_rejected(self):
        """FTP URLs should be rejected."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _validate_recording_url("ftp://recordings.example.com/file.mp3")
        assert exc_info.value.status_code == 400

    def test_no_hostname_rejected(self):
        """URL with no hostname should be rejected."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _validate_recording_url("https://")
        assert exc_info.value.status_code == 400

    def test_file_scheme_rejected(self):
        """file:// scheme should be rejected."""
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            _validate_recording_url("file:///etc/passwd")
        assert exc_info.value.status_code == 400
