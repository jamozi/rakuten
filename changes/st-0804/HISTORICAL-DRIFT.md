# ST-0804 historical candidate drift

Local status: `LOCAL_IMPLEMENTATION_COMPLETE`.

Historical candidate `c24ab82af37030ccc0bf78d65806effff1b95f74` supplied a
strong pure Decimal engine and its CT-0887--CT-0906 local regression suite. It
predated the integrated ST-0803 V2 envelope, emitted report and receipt.

The V1 source and tests remain unchanged. The additive V2 closes the drift by
binding the exact ST-0803 request/report/record receipt, article/body/Packet/
Claim/candidate/axis/Fact/time hashes, versioned decision context, methodology,
axis definition and normalization decisions. It adds a recorded-only
application boundary, recursive finance-alias rejection, bounded fixtures and
foreign-preserving owner generation. No historical branch was merged
wholesale and no publication or ranking authority was added.

Formal/live/staging/release/Production evidence remains `NOT_EXECUTED`.
