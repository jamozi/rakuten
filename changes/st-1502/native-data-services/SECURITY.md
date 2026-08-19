# Security invariants

The native ST-1502 candidate requires private database networking, KMS-backed encryption, S3 public-access blocking, versioning, non-destructive bucket defaults, encrypted SQS queues with DLQs, RDS-managed master credentials, deletion protection, and final snapshots.

It deliberately contains no IAM workload policy yet; least-privilege workload access must be introduced with the consuming compute slice rather than by adding wildcard permissions here.
