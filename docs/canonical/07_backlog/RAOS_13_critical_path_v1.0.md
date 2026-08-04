# RAOS MVP Critical Path

以下は技術依存順を示す。並列実装可能なStoryはBacklog YAMLの`depends_on`を正本とする。

1. `ST-0001` — Import canonical design package
2. `ST-0002` — Apply job-state canonical revision
3. `ST-0003` — Apply AI governance canonical revision
4. `ST-0004` — Apply content canonical revision
5. `ST-0101` — Create monorepo layout
6. `ST-0102` — Pin Python toolchain
7. `ST-0103` — Pin Node toolchain
8. `ST-0104` — Install contract repository
9. `ST-0105` — Generate Python and TypeScript types
10. `ST-0106` — Create base CI
11. `ST-0201` — Local PostgreSQL 18 service
12. `ST-0202` — Local S3-compatible object service
13. `ST-0203` — Local queue abstraction
14. `ST-0204` — Configuration and secret loader
15. `ST-0301` — Migration framework
16. `ST-0302` — Foundation schemas and extensions
17. `ST-0303` — IAM/OPS schemas
18. `ST-0304` — Domain schemas
19. `ST-0305` — Publication/analytics/finance schemas
20. `ST-0306` — Database roles and grants
21. `ST-0308` — Persistence ports and repositories
22. `ST-0401` — OIDC adapter and admin login
23. `ST-0402` — MFA and step-up
24. `ST-0403` — Authorization policy engine
25. `ST-0501` — Portfolio CRUD and workflow
26. `ST-0502` — Rakuten adapter recorded
27. `ST-0503` — Catalog normalization
28. `ST-0504` — Product identity decision engine
29. `ST-0601` — Raw artifact registry
30. `ST-0602` — Fact extraction and validation
31. `ST-0604` — Source packet lifecycle
32. `ST-0605` — Claim/evidence service
33. `ST-0701` — AI contract registry loader
34. `ST-0702` — Context pack builder
35. `ST-0703` — OpenAI Responses adapter recorded
36. `ST-0705` — AI output validators
37. `ST-0706` — AI job orchestration
38. `ST-0801` — Content AST types and validator
39. `ST-0802` — Article plan/version lifecycle
40. `ST-0803` — Comparison validator
41. `ST-0804` — Recommendation engine
42. `ST-0805` — Editorial policy engine
43. `ST-0806` — AI draft integration
44. `ST-0901` — Review workflow
45. `ST-0902` — Final approval
46. `ST-0903` — Publication manifest/snapshot
47. `ST-0904` — Public projection
48. `ST-0905` — Publish/unpublish/rollback commands
49. `ST-1001` — Public app shell and policy pages
50. `ST-1002` — Public article renderer
51. `ST-1003` — Comparison and product components
52. `ST-1004` — Disclosure and affiliate CTA
53. `ST-1101` — Admin shell/design system
54. `ST-1102` — Article workspace UI
55. `ST-1201` — Canonical event collector
56. `ST-1202` — Public event instrumentation
57. `ST-1301` — Revenue file intake
58. `ST-1302` — Provider fact commit
59. `ST-1401` — Freshness scheduler and state
60. `ST-1402` — Safe degradation renderer
61. `ST-1404` — Job/Outbox/Inbox runtime
62. `ST-1405` — Kill switch runtime
63. `ST-1501` — Terraform foundation
64. `ST-1502` — Data services infrastructure
65. `ST-1503` — Compute/CDN/WAF infrastructure
66. `ST-1504` — GitHub OIDC deployment
67. `ST-1505` — Staging deployment pipeline
68. `ST-1601` — Observability foundation
69. `ST-1602` — SLI/SLO and alert implementation
70. `ST-1603` — Security verification pack
71. `ST-1605` — Failure injection and runbook drill
72. `ST-1606` — Backup restore drill
73. `ST-1607` — Gate evidence generator
74. `ST-1701` — Resolve MVP business inputs
75. `ST-1702` — Create category fixtures and rules
76. `ST-1703` — End-to-end first article
77. `ST-1704` — 5-10 article editorial pilot
78. `ST-1705` — Pilot security/recovery sign-off
