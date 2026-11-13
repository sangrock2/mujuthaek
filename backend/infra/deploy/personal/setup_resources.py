"""Create only this deployment's static IP, private S3 bucket and bucket-scoped runtime identity."""
import json
import secrets
from pathlib import Path
from aws_personal import AWS, INSTANCE, RUNTIME, REGION, STATIC_IP_NAME


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--account", required=True)
    args = parser.parse_args()
    if (RUNTIME / ".env").exists():
        raise RuntimeError("Runtime environment already exists; do not replace live resources or credentials")
    aws = AWS(args.profile, args.account)
    aws.verify()
    instance = aws.call("lightsail", "get-instance", "--instance-name", INSTANCE)["instance"]
    if not any(t["key"] == "Project" and t.get("value") == "mujuthaek-personal" for t in instance.get("tags", [])):
        raise RuntimeError("Instance ownership tag mismatch")
    ip_name = STATIC_IP_NAME
    ips = aws.call("lightsail", "get-static-ips")["staticIps"]
    ip = next((i for i in ips if i["name"] == ip_name), None)
    if ip is None:
        aws.call("lightsail", "allocate-static-ip", "--static-ip-name", ip_name)
        ip = aws.call("lightsail", "get-static-ip", "--static-ip-name", ip_name)["staticIp"]
    if ip.get("attachedTo") not in {None, "", INSTANCE}:
        raise RuntimeError("IP is attached to a different instance")
    if ip.get("attachedTo") != INSTANCE:
        aws.call("lightsail", "attach-static-ip", "--static-ip-name", ip_name, "--instance-name", INSTANCE)
    bucket = f"mujuthaek-personal-{args.account}-raw"
    buckets = aws.call("s3api", "list-buckets")["Buckets"]
    if not any(b["Name"] == bucket for b in buckets):
        aws.call("s3api", "create-bucket", "--bucket", bucket, "--create-bucket-configuration", f"LocationConstraint={REGION}")
        aws.call("s3api", "put-bucket-tagging", "--bucket", bucket,
                 "--tagging", json.dumps({"TagSet": [{"Key": "Project", "Value": "mujuthaek-personal"}]}))
    else:
        tags = aws.call("s3api", "get-bucket-tagging", "--bucket", bucket)["TagSet"]
        if not any(t["Key"] == "Project" and t["Value"] == "mujuthaek-personal" for t in tags):
            raise RuntimeError("Existing bucket ownership tag mismatch")
    aws.call("s3api", "put-public-access-block", "--bucket", bucket, "--public-access-block-configuration",
             "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true")
    aws.call("s3api", "put-bucket-encryption", "--bucket", bucket, "--server-side-encryption-configuration",
             json.dumps({"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]}))
    RUNTIME.mkdir(exist_ok=True)
    env_file = RUNTIME / ".env"
    if env_file.exists():
        raise RuntimeError("Runtime environment already exists; do not create or replace access keys")
    username = "mujuthaek-personal-runtime-20261113"
    aws.call("iam", "create-user", "--user-name", username, "--tags", "Key=Project,Value=mujuthaek-personal")
    policy = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Action": ["s3:ListBucket", "s3:GetBucketLocation"], "Resource": f"arn:aws:s3:::{bucket}"},
        {"Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:AbortMultipartUpload"], "Resource": f"arn:aws:s3:::{bucket}/*"},
    ]}
    aws.call("iam", "put-user-policy", "--user-name", username, "--policy-name", "PersonalBucketOnly", "--policy-document", json.dumps(policy))
    key = aws.call("iam", "create-access-key", "--user-name", username)["AccessKey"]
    values = {k: secrets.token_hex(32) for k in (
        "POSTGRES_PASSWORD", "API_DB_PASSWORD", "NOTIFICATION_DB_PASSWORD", "COLLECTOR_DB_PASSWORD",
        "EXTRACTION_DB_PASSWORD", "RABBITMQ_PASSWORD", "JWT_SECRET", "NOTIFICATION_INTERNAL_TOKEN",
        "COLLECTOR_ADMIN_TOKEN", "EXTRACTION_REVIEW_TOKEN", "TRAFFIC_INGEST_TOKEN",
    )}
    values.update(AWS_ACCESS_KEY_ID=key["AccessKeyId"], AWS_SECRET_ACCESS_KEY=key["SecretAccessKey"],
                  AWS_REGION=REGION, S3_BUCKET=bucket, PUBLIC_ORIGIN=f'https://{ip["ipAddress"]}',
                  API_TLS_CERT_DIR="/opt/mujuthaek-source/backend/infra/deploy/personal/tls")
    with env_file.open("x", encoding="ascii", newline="\n") as output:
        output.write("".join(f"{k}={v}\n" for k, v in values.items()))
    env_file.chmod(0o600)
    (RUNTIME / "versions.env").write_text("RELEASE=20261113-1\n", encoding="ascii")
    print(json.dumps({"static_ip": ip["ipAddress"], "bucket": bucket, "runtime_user": username, "credentials": "saved locally; not printed"}))


if __name__ == "__main__":
    main()
