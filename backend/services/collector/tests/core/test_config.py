from mujuthaek_collector.config import Settings


def test_local_defaults_need_no_env(monkeypatch):
    for name in ("DB_URL", "RABBITMQ_URL", "S3_ENDPOINT", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings.from_env()
    assert settings.db_url.endswith("@localhost:5432/collector")
    assert settings.s3_endpoint == "http://localhost:9000"  # 로컬 MinIO
    assert (settings.s3_access_key, settings.s3_secret_key) == ("minio", "minio-pass")


def test_empty_endpoint_means_aws_s3(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT", "")
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    settings = Settings.from_env()
    assert settings.s3_endpoint is None and settings.s3_access_key is None  # boto3 기본 인증 (EC2 역할)
