# ST-1503 native compute/edge candidate

This slice promotes the existing ST-1503 interface-only intent into native Terraform source while retaining disabled external execution.

It defines four ECS/Fargate workload roles with immutable digest-only images, encrypted bounded logs, private subnets and no public task IPs. Only `public_web` and `admin_web` receive load balancers, and those ALBs are internal. CloudFront reaches them through VPC origins. Public and admin use distinct distributions, domains, cache policies and mandatory WAF Web ACL IDs. `core_api` and `worker_pool` have no edge origin.

All physical networking, role ARNs, certificates, domains, WAF IDs and cache-policy IDs are explicit caller inputs. This candidate creates no IAM policy, DNS record, VPC, subnet, security group, certificate or WAF. It supplies no account, region, backend, credential or provider configuration.

No Terraform init/validate/plan/apply, AWS request, staging deployment, DNS mutation, release or Production action is claimed. Before integration this branch must be reconstructed onto the exact integrated ST-1502/ST-1501 predecessor and verified with the pinned native toolchain.
