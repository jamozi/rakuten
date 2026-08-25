# ST-0803 historical drift and compatibility record

The predecessor implementation was a local V1 matrix validator. It intentionally
did not consume the later executable ST-0605 receipt contract, bind Article and
Packet hashes, or emit an ST-0605-compatible `COMPARISON` receipt. ST-0804
imports that V1 domain module directly.

V2 is therefore additive:

- `comparison_validation.py` and its historical tests remain unchanged;
- `comparison_validation_v2.py` owns the new exact hash/receipt handshake;
- V2 application, port and recorded adapter modules are separate;
- no package facade is widened, avoiding unrelated owner-manifest drift;
- V1 `PASS` remains local/test-only and is not reinterpreted as V2
  `LOCAL_VALIDATED` or as an ST-0605 receipt.

This compatibility decision does not preserve V1 omissions inside V2. V2 fails
closed on every missing exact binding and retains no ranking, recommendation,
publication or Production authority.
