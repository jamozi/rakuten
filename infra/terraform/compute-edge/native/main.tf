locals {
  edge_roles = toset(["public_web", "admin_web"])
}

resource "aws_ecs_cluster" "this" {
  name = var.cluster_name
  tags = var.tags
}

resource "aws_cloudwatch_log_group" "workload" {
  for_each = var.workloads

  name              = "/raos/${var.cluster_name}/${each.key}"
  retention_in_days = var.log_retention_days
  kms_key_id        = var.log_kms_key_arn
  tags              = var.tags

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_ecs_task_definition" "workload" {
  for_each = var.workloads

  family                   = "${var.cluster_name}-${each.key}"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = each.value.cpu
  memory                   = each.value.memory
  execution_role_arn       = each.value.execution_role_arn
  task_role_arn            = each.value.task_role_arn

  container_definitions = jsonencode([
    {
      name      = each.key
      image     = each.value.image_uri
      essential = true
      portMappings = each.key == "worker_pool" ? [] : [
        {
          containerPort = each.value.container_port
          protocol      = "tcp"
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.workload[each.key].name
          awslogs-region        = data.aws_region.current.name
          awslogs-stream-prefix = each.key
        }
      }
    }
  ])

  tags = var.tags
}

data "aws_region" "current" {}

resource "aws_lb" "edge" {
  for_each = local.edge_roles

  name               = substr("${var.cluster_name}-${each.key}", 0, 32)
  internal           = true
  load_balancer_type = "application"
  subnets            = var.private_subnet_ids
  security_groups = [
    each.key == "public_web" ? var.alb_security_group_ids.public : var.alb_security_group_ids.admin,
  ]
  enable_deletion_protection = true
  drop_invalid_header_fields = true
  tags                       = var.tags
}

resource "aws_lb_target_group" "edge" {
  for_each = local.edge_roles

  name        = substr("${var.cluster_name}-${each.key}", 0, 32)
  port        = var.workloads[each.key].container_port
  protocol    = "HTTPS"
  target_type = "ip"
  vpc_id      = data.aws_subnet.first.vpc_id

  health_check {
    enabled             = true
    protocol            = "HTTPS"
    path                = var.workloads[each.key].health_path
    matcher             = "200-299"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
    timeout             = 5
  }

  tags = var.tags
}

data "aws_subnet" "first" {
  id = var.private_subnet_ids[0]
}

resource "aws_lb_listener" "edge" {
  for_each = local.edge_roles

  load_balancer_arn = aws_lb.edge[each.key].arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.origin_certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.edge[each.key].arn
  }
}

resource "aws_ecs_service" "workload" {
  for_each = var.workloads

  name            = "${var.cluster_name}-${each.key}"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.workload[each.key].arn
  desired_count   = each.value.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.service_security_group_ids[each.key]]
    assign_public_ip = false
  }

  dynamic "load_balancer" {
    for_each = contains(local.edge_roles, each.key) ? [1] : []
    content {
      target_group_arn = aws_lb_target_group.edge[each.key].arn
      container_name   = each.key
      container_port   = each.value.container_port
    }
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  tags = var.tags
}

resource "aws_cloudfront_vpc_origin" "edge" {
  for_each = local.edge_roles

  vpc_origin_endpoint_config {
    name                   = "${var.cluster_name}-${each.key}"
    arn                    = aws_lb.edge[each.key].arn
    http_port              = 80
    https_port             = 443
    origin_protocol_policy = "https-only"

    origin_ssl_protocols {
      items    = ["TLSv1.2"]
      quantity = 1
    }
  }

  tags = var.tags
}

resource "aws_cloudfront_distribution" "edge" {
  for_each = local.edge_roles

  enabled         = true
  is_ipv6_enabled = true
  aliases = [
    each.key == "public_web" ? var.domains.public : var.domains.admin,
  ]
  web_acl_id = each.key == "public_web" ? var.web_acl_ids.public : var.web_acl_ids.admin

  origin {
    domain_name = aws_lb.edge[each.key].dns_name
    origin_id   = each.key

    vpc_origin_config {
      vpc_origin_id           = aws_cloudfront_vpc_origin.edge[each.key].id
      origin_keepalive_timeout = 5
      origin_read_timeout      = 30
    }
  }

  default_cache_behavior {
    target_origin_id       = each.key
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id = each.key == "public_web" ? var.cache_policy_ids.public : var.cache_policy_ids.admin
    compress        = true
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = var.viewer_certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = var.tags
}
