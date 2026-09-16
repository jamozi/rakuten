# Synthetic Rakuten price refresh fixtures

All files here are hand-written for tests. None is copied from a Rakuten API
response, a catalog observation or a published page. Shop codes, item ids,
model numbers, prices and credentials are invented (`synth-*`, `SYN-*`).
Response bodies follow the documented Item Search 2026-07-01 `formatVersion=2`
shape (`items[0].itemName`) and error bodies from the official error table.
