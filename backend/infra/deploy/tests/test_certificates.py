import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location("certificates", Path(__file__).resolve().parents[1] / "certificates.py")
certificates = importlib.util.module_from_spec(spec)
spec.loader.exec_module(certificates)


@pytest.mark.parametrize(
    "identifier",
    ["127.0.0.1", "169.254.169.254", "10.0.0.1", "::1", "file:///etc/passwd", "-evil.example", "api.example\n.org"],
)
def test_unsafe_identifiers_cannot_reach_certbot(identifier):
    with pytest.raises(ValueError):
        certificates.identifier_args(identifier)


def test_public_ip_uses_ip_san_and_short_lived_profile():
    assert certificates.identifier_args("1.1.1.1") == ["--ip-address", "1.1.1.1", "--preferred-profile", "shortlived"]
    assert certificates.identifier_args("api.example.org") == ["-d", "api.example.org"]


def test_certbot_keeps_credentials_in_own_mount_without_docker_socket(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(certificates, "run", lambda *args: calls.append(args))
    certificates.certbot(tmp_path, "renew", "--dry-run")
    call = calls[0]
    assert certificates.CERTBOT_IMAGE in call and call[-2:] == ("renew", "--dry-run")
    assert sum("type=bind" in arg for arg in call) == 4
    assert not any("docker.sock" in arg or arg == "--privileged" for arg in call)


def test_tls_setting_preserves_other_environment_entries(tmp_path):
    path = tmp_path / ".env"
    path.write_text("UNCHANGED=test-only\nAPI_TLS_CERT_DIR=/old/path\n")
    certificates.persist_tls_path(tmp_path)
    assert path.read_text() == f'UNCHANGED=test-only\nAPI_TLS_CERT_DIR="{tmp_path / "tls"}"\n'


@pytest.mark.skipif(__import__("os").name == "nt", reason="symlink activation uses Linux deployment semantics")
def test_activation_validates_before_atomic_pair_switch(tmp_path, monkeypatch):
    lineage = tmp_path / "letsencrypt/live/mujuthaek-prod"
    lineage.mkdir(parents=True)
    (tmp_path / "tls").mkdir()
    for name in ["cert.pem", "chain.pem", "fullchain.pem", "privkey.pem"]:
        (lineage / name).write_text("first-" + name)
    calls = []

    def openssl(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout="matching-public-key")

    monkeypatch.setattr(certificates, "run", openssl)
    settings = {"identifier": "1.1.1.1", "cert_name": "mujuthaek-prod"}
    certificates.activate(tmp_path, settings)
    original = (tmp_path / "tls/current").resolve()
    assert (tmp_path / "tls/fullchain.pem").read_text() == "first-fullchain.pem"
    assert any("-verify_ip" in call for call in calls)
    assert any("verify" in call for call in calls)

    def invalid(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(certificates, "run", invalid)
    (lineage / "fullchain.pem").write_text("second-fullchain.pem")
    with pytest.raises(subprocess.CalledProcessError):
        certificates.activate(tmp_path, settings)
    assert (tmp_path / "tls/current").resolve() == original
    assert (tmp_path / "tls/fullchain.pem").read_text() == "first-fullchain.pem"
