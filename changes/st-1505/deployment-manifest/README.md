# ST-1505 immutable deployment manifest candidate

This slice closes the mutable-coordinate gap between staging admission and the least-privilege staging IAM policy. A deployment attempt is represented by one canonical JSON manifest whose exact bytes are SHA-256 bound before any future OIDC credential acquisition.

The strict offline verifier rejects duplicate or unknown keys, non-canonical JSON, malformed or cross-account/region ARNs, wildcard resources, mutable container tags, wrong environment, service/cluster mismatch, duplicate service identities, destructive migration classification, invalid migration networking, missing/distinct health surfaces, and rollback artifacts/task definitions that are not distinct from the candidate deployment.

The `supply_chain.signature_sha256` field binds the bytes of a detached signature artifact. **This verifier does not perform cryptographic signature verification and does not claim that the signature is valid.** A future executable artifact-admission phase must independently verify that signature against an approved trust root and bind the resulting verification receipt before any staging write is permitted. The same applies to the SBOM, vulnerability, and provenance digests: this slice binds immutable references; it does not reinterpret their contents.

The verifier performs no network access, provider call, credential read, Terraform action, staging write, migration, release, or Production action. Its success receipt fixes both external-write and Production action counts to zero.
