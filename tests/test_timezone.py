"""
Testes E2E para o fix de timezone.

Verifica que TODOS os endpoints da API retornam datetimes com sufixo 'Z'
(UTC explícito), garantindo que o frontend interpreta corretamente.

Bug original: backend enviava "2026-03-02T11:00:00" (sem Z),
frontend interpretava como hora local → diff errado → "agora" sempre.
"""

import json
import re

import pytest


def _extrair_isostrings(obj, path=""):
    """Extrai todos os valores que parecem ISO datetime de um JSON recursivamente.

    Retorna lista de tuplas (json_path, valor).
    """
    resultados = []
    iso_re = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")

    if isinstance(obj, dict):
        for key, value in obj.items():
            current_path = f"{path}.{key}" if path else key
            if isinstance(value, str) and iso_re.match(value):
                resultados.append((current_path, value))
            elif isinstance(value, (dict, list)):
                resultados.extend(_extrair_isostrings(value, current_path))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            current_path = f"{path}[{i}]"
            if isinstance(item, str) and iso_re.match(item):
                resultados.append((current_path, item))
            elif isinstance(item, (dict, list)):
                resultados.extend(_extrair_isostrings(item, current_path))

    return resultados


def _assert_all_datetimes_have_z(data, endpoint_name):
    """Verifica que TODAS as strings ISO datetime tem sufixo Z ou offset."""
    isostrings = _extrair_isostrings(data)

    for json_path, value in isostrings:
        has_z = value.endswith("Z")
        has_offset = bool(re.search(r"[+-]\d{2}:\d{2}$", value))
        assert has_z or has_offset, (
            f"[{endpoint_name}] Campo '{json_path}' tem datetime naive (sem Z/offset): "
            f"'{value}'. Deve terminar com 'Z' para indicar UTC."
        )


# =============================================
# /api/clients (CRUD)
# =============================================

class TestApiClientsCRUD:
    """Testa serialização de datetimes no CRUD de clientes."""

    def test_list_clients_datetimes_tem_z(self, client, seed_data):
        resp = client.get("/api/clients")
        assert resp.status_code == 200

        data = resp.get_json()
        assert data["total"] >= 1

        _assert_all_datetimes_have_z(data, "GET /api/clients")

    def test_get_client_detail_datetimes_tem_z(self, client, seed_data):
        cid = seed_data["client_id"]
        resp = client.get(f"/api/clients/{cid}")
        assert resp.status_code == 200

        data = resp.get_json()
        _assert_all_datetimes_have_z(data, f"GET /api/clients/{cid}")

    def test_client_dict_campos_especificos(self, client, seed_data):
        """Verifica campos individuais que causavam o bug."""
        cid = seed_data["client_id"]
        resp = client.get(f"/api/clients/{cid}")
        data = resp.get_json()

        # Campos que causavam o bug
        assert data["last_check"].endswith("Z"), f"last_check sem Z: {data['last_check']}"
        assert data["created_at"].endswith("Z"), f"created_at sem Z: {data['created_at']}"
        assert data["expires_at"].endswith("Z"), f"expires_at sem Z: {data['expires_at']}"

        # Task logs
        for log in data.get("task_logs", []):
            assert log["created_at"].endswith("Z"), f"task_log.created_at sem Z: {log['created_at']}"

        # Payments
        for p in data.get("payments", []):
            assert p["created_at"].endswith("Z"), f"payment.created_at sem Z: {p['created_at']}"


# =============================================
# /api/clients/status (Dashboard)
# =============================================

class TestApiClientsStatus:
    """Testa serialização no endpoint de status dos clientes."""

    def test_clients_status_datetimes_tem_z(self, client, seed_data):
        resp = client.get("/api/clients/status")
        assert resp.status_code == 200

        data = resp.get_json()
        assert len(data) >= 1

        _assert_all_datetimes_have_z(data, "GET /api/clients/status")

    def test_clients_status_last_check_tem_z(self, client, seed_data):
        resp = client.get("/api/clients/status")
        data = resp.get_json()

        for item in data:
            if item["last_check"]:
                assert item["last_check"].endswith("Z"), (
                    f"last_check sem Z para cliente {item['nome']}: {item['last_check']}"
                )

    def test_clients_status_last_task_time_tem_z(self, client, seed_data):
        resp = client.get("/api/clients/status")
        data = resp.get_json()

        for item in data:
            if item.get("last_task"):
                assert item["last_task"]["time"].endswith("Z"), (
                    f"last_task.time sem Z para cliente {item['nome']}: {item['last_task']['time']}"
                )


# =============================================
# /api/clients/<id>/status (Status individual)
# =============================================

class TestApiClientStatus:
    """Testa serialização no endpoint de status individual."""

    def test_client_status_datetimes_tem_z(self, client, seed_data):
        cid = seed_data["client_id"]
        resp = client.get(f"/api/clients/{cid}/status")
        assert resp.status_code == 200

        data = resp.get_json()
        _assert_all_datetimes_have_z(data, f"GET /api/clients/{cid}/status")

    def test_client_status_recent_logs_tem_z(self, client, seed_data):
        cid = seed_data["client_id"]
        resp = client.get(f"/api/clients/{cid}/status")
        data = resp.get_json()

        for log in data.get("recent_logs", []):
            assert log["created_at"].endswith("Z"), (
                f"recent_logs.created_at sem Z: {log['created_at']}"
            )


# =============================================
# /api/logs/recent
# =============================================

class TestApiRecentLogs:
    """Testa serialização no endpoint de logs recentes."""

    def test_recent_logs_datetimes_tem_z(self, client, seed_data):
        resp = client.get("/api/logs/recent")
        assert resp.status_code == 200

        data = resp.get_json()
        assert len(data) >= 1

        _assert_all_datetimes_have_z(data, "GET /api/logs/recent")


# =============================================
# /api/errors/recent
# =============================================

class TestApiRecentErrors:
    """Testa serialização no endpoint de erros recentes."""

    def test_recent_errors_datetimes_tem_z(self, client, seed_data):
        resp = client.get("/api/errors/recent")
        assert resp.status_code == 200

        data = resp.get_json()
        assert len(data) >= 1  # temos 1 erro no seed_data

        _assert_all_datetimes_have_z(data, "GET /api/errors/recent")


# =============================================
# /api/activity/timeline
# =============================================

class TestApiActivityTimeline:
    """Testa serialização no endpoint de timeline."""

    def test_activity_timeline_hours_tem_z(self, client, seed_data):
        resp = client.get("/api/activity/timeline")
        assert resp.status_code == 200

        data = resp.get_json()
        assert len(data) >= 1

        for item in data:
            assert item["hour"].endswith("Z"), (
                f"activity_timeline.hour sem Z: {item['hour']}"
            )


# =============================================
# /api/health
# =============================================

class TestApiHealth:
    """Testa serialização no health check."""

    def test_health_timestamp_tem_z(self, app):
        """Health check nao precisa de auth."""
        with app.test_client() as c:
            resp = c.get("/api/health")
            # Pode ser 200 ou 503, nao importa
            data = resp.get_json()
            assert data["timestamp"].endswith("Z"), (
                f"health.timestamp sem Z: {data['timestamp']}"
            )
