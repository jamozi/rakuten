# Staging deployment permission boundary

The staging OIDC role is intentionally narrower than a general ECS deployment role.

It may update only explicitly supplied staging service ARNs, run only explicitly supplied reviewed task-definition ARNs on the exact staging cluster, observe/stop tasks only inside the exact staging cluster task namespace, pass only explicitly supplied ECS roles to `ecs-tasks.amazonaws.com`, inspect exact target groups, and invalidate exact staging CloudFront distributions.

It cannot register task definitions. AWS documents that common task-definition registration/description permissions require broad resource scope; task-definition creation therefore remains an IaC/release-build responsibility instead of widening the runtime deploy role.

The policy is attached only to the staging OIDC role. The Production role remains permissionless in this slice. No IAM apply, OIDC assumption, deployment, migration, release or Production action is performed by committing this policy.
