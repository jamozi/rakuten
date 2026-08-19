from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = (ROOT / "infra/terraform/compute-edge/native/main.tf").read_text()
VARIABLES = (ROOT / "infra/terraform/compute-edge/native/variables.tf").read_text()


def test_images_are_digest_only() -> None:
    assert '@sha256:[0-9a-f]{64}$' in VARIABLES
    assert 'image_uri' in VARIABLES


def test_workloads_never_receive_public_ip() -> None:
    assert 'assign_public_ip = false' in MAIN
    assert 'assign_public_ip = true' not in MAIN


def test_origins_are_internal_and_cloudfront_uses_vpc_origins() -> None:
    assert 'internal           = true' in MAIN
    assert 'resource "aws_cloudfront_vpc_origin" "edge"' in MAIN
    assert 'vpc_origin_config {' in MAIN
    assert 'origin_protocol_policy = "https-only"' in MAIN


def test_public_and_admin_are_separate_and_waf_is_mandatory() -> None:
    assert 'public_web' in MAIN
    assert 'admin_web' in MAIN
    assert 'web_acl_id' in MAIN
    assert 'web_acl_ids' in VARIABLES
    assert 'var.web_acl_ids.public' in MAIN
    assert 'var.web_acl_ids.admin' in MAIN
    assert 'var.cache_policy_ids.public' in MAIN
    assert 'var.cache_policy_ids.admin' in MAIN


def test_health_is_explicit_and_not_generic_http_200_shortcut() -> None:
    assert 'path                = var.workloads[each.key].health_path' in MAIN
    assert 'protocol            = "HTTPS"' in MAIN
    assert 'matcher             = "200-299"' in MAIN


def test_logs_are_encrypted_and_bounded() -> None:
    assert 'kms_key_id        = var.log_kms_key_arn' in MAIN
    assert 'retention_in_days = var.log_retention_days' in MAIN
    assert 'prevent_destroy = true' in MAIN


def test_no_iam_policy_or_dns_resource_is_created() -> None:
    assert 'aws_iam_policy' not in MAIN
    assert 'aws_iam_role_policy' not in MAIN
    assert 'aws_route53_' not in MAIN
    assert 'Action = "*"' not in MAIN


def test_worker_and_core_are_not_edge_origins() -> None:
    assert 'local.edge_roles = toset' not in MAIN
    assert 'edge_roles = toset(["public_web", "admin_web"])' in MAIN
