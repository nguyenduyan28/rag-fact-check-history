# Stage 2: Baseline Error Analysis

Baseline file: `data/outputs/verified/hybrid_top5_verified.json`  
Report file: `data/outputs/reports/hybrid_top5_report.txt`  
Retriever output: `data/outputs/retrieved/hybrid_top5.json`

## Baseline Summary

- Total scored rows: 11,494
- Accuracy: 79.98%
- Macro F1: 0.79
- Real recall: 0.95
- Fake recall: 0.73
- False real: 2,115 fake claims predicted as `real`
- False fake: 186 real claims predicted as `fake`

The baseline is much more likely to accept fake claims than to reject real claims. The main weakness is not broad label confusion, but failure to catch small historical contradictions inside otherwise relevant evidence.

## Sampling Method

- Sampled fake claims predicted as `real` from the 2,115 false-real cases.
- Sampled real claims predicted as `fake` from the 186 false-fake cases.
- Compared each sampled claim against `gold_relevant`, retrieved top chunks, and verifier reasoning.
- Checked for date/year errors, entity/place/organization errors, broad non-decisive chunks, and OCR/source noise.
- Used retrieved top-3 because `configs/verify.yaml` sets `verification.top_k_context: 3`.

## Overall Patterns

- Most sampled failures have topically relevant retrieved chunks.
- Many failures happen because the verifier ignores a decisive detail: year, date, number, actor, organization, or direction of an event.
- Some real claims are marked fake because the top-3 context is broad and misses the exact evidence chunk, even though the exact chunk exists in the corpus.
- OCR noise contributes to missed evidence, especially when entity names or short phrases are corrupted or omitted.
- GraphRAG should focus on structured event, time, actor, place, and relation matching rather than only semantic similarity.

## Fake Claims Predicted As Real

### `151_fake`

- Claim: Mặt trận Thống nhất dân tộc phản đế Đông Dương replaced `Mặt trận Cộng hòa Đông Dương`.
- Gold evidence: it replaced `Mặt trận Dân chủ Đông Dương`.
- Retrieved chunks: relevant topic around the 1939-1941 revolutionary line.
- Error type: wrong organization/name.
- Cause: verifier accepted the claim even though the replacement organization name was wrong.
- GraphRAG target: entity/organization relation check: `Mặt trận Phản đế Đông Dương` `REPLACED` `Mặt trận Dân chủ Đông Dương`.

### `183_fake`

- Claim: uprising would only happen in small areas and not become a general uprising.
- Gold evidence: from partial uprisings to general uprising.
- Retrieved chunks: relevant to uprisings, but not decisive enough in the verifier's reasoning.
- Error type: event trajectory/relation error.
- Cause: verifier confused `khởi nghĩa từng phần` with a final limitation, missing `tiến lên tổng khởi nghĩa`.
- GraphRAG target: event sequence relation: partial uprising `LEADS_TO` general uprising.

### `188_fake`

- Claim: Hội nghị Trung ương 8 at Pác Bó happened from 12-21 April 1940.
- Gold evidence: it happened from 10-19 May 1941.
- Retrieved chunks: top chunk discusses the same conference but does not clearly expose all date details in the used context.
- Error type: wrong date/year.
- Cause: verifier accepted the event match and ignored the incorrect date.
- GraphRAG target: temporal node for Hội nghị Trung ương 8: `10-19/5/1941`.

### `191_fake`

- Claim: Việt Minh was founded on 19 May 1942.
- Gold evidence: Việt Minh was founded on 19 May 1941.
- Retrieved chunks: relevant and include the correct event context.
- Error type: wrong year.
- Cause: verifier cited evidence for `1941` but still accepted the claim's `1942`.
- GraphRAG target: strict temporal contradiction detection.

### `203_fake`

- Claim: `Pháp đảo chính Nhật` and issued `Pháp - Nhật bắn nhau...`.
- Gold evidence: `Nhật đảo chính Pháp` and directive `Nhật - Pháp bắn nhau...`.
- Retrieved chunks: relevant to March 1945 and the directive.
- Error type: wrong actors and reversed event direction.
- Cause: verifier normalized the phrase and missed the actor reversal.
- GraphRAG target: actor-relation extraction: `Nhật` `OVERTHREW/COUP_AGAINST` `Pháp`.

### `235_fake`

- Claim: Bà Rịa and Vũng Tàu were the last localities to seize power on 1 September.
- Gold evidence: Đồng Nai Thượng and Hà Tiên were latest, on 28 August.
- Retrieved chunks: relevant and include the decisive localities and date.
- Error type: wrong places and wrong date.
- Cause: verifier inferred from broad success of the uprising instead of checking named localities.
- GraphRAG target: place-event-time facts for August Revolution local power seizures.

### `247_fake`

- Claim: people contributed 370 kg gold and 200 million dong to `Quỹ độc lập`.
- Gold evidence: 370 kg gold and 20 million dong to `Quỹ độc lập`; 40 million dong to national defense fund.
- Retrieved chunks: relevant to financial campaign, but the exact number may be truncated or not surfaced clearly.
- Error type: wrong number and fund name variation.
- Cause: verifier accepted a plausible financial detail without checking the number.
- GraphRAG target: numeric fact extraction linked to fund names.

### `331_fake`

- Claim: we occupied Tây Bắc and protected Việt Bắc, reducing threat to enemy Thượng Lào.
- Gold evidence: Tây Bắc was occupied by the enemy, threatened Việt Bắc, and shielded enemy Thượng Lào.
- Retrieved chunks: relevant to Tây Bắc campaigns and strategic position.
- Error type: wrong actor/control relation.
- Cause: verifier mixed later liberation campaign context with the initial strategic fact.
- GraphRAG target: time-scoped control relation: `địch` `OCCUPIED` `Tây Bắc` before campaign.

### `464_fake`

- Claim: Hồ Chí Minh left the historical Testament only for the Politburo.
- Gold evidence: he left it for the whole Party and people.
- Retrieved chunks: relevant to the Testament.
- Error type: wrong recipient/scope.
- Cause: verifier treated `Bộ Chính trị` as compatible with `toàn Đảng, toàn dân`, but the claim says `chỉ`.
- GraphRAG target: scope and recipient relation checks.

## Real Claims Predicted As Fake

### `27`

- Claim: Ba Son workers demanded a 20% wage increase.
- Gold evidence: workers demanded 20%; French authorities later accepted 10%.
- Retrieved chunks: exact evidence is in E1.
- Error type: verifier reasoning error, not retrieval error.
- Cause: verifier confused the demand with the final accepted increase.
- GraphRAG target: separate event roles: `DEMAND` 20% vs `ACCEPTED` 10%.

### `104`, `107`, `109`, `110`, `111`

- Claims: Hội nghị Trung ương/October 1930, Hương Cảng, đổi tên Đảng, Trần Phú, Luận cương chính trị.
- Gold evidence: exact details are on `lichsu_12/lichsu_12.pdf_94.jpg.txt`.
- Retrieved chunks: often pages 87-89 about party founding in early 1930, not the October 1930 conference.
- Error type: broad/topically related but non-decisive chunks.
- Cause: retrieval overmatched `Đảng Cộng sản Việt Nam`, `Hương Cảng`, and `1930`, but missed the exact conference page.
- GraphRAG target: distinguish two nearby events: founding conference in early 1930 vs first Central Committee conference in October 1930.

### `122`

- Claim: mass organizations included `hội cấy`, `hội cày`, `hội hiếu hỉ`, and `hội đọc sách báo`.
- Gold evidence: includes `hội hiếu hỉ`.
- Retrieved chunks: `lichsu_12.pdf_96` contains the topic but OCR/source text only shows `hội cấy`, `hội cày`, `hội đọc sách báo`; `hội hiếu hỉ` is missing.
- Error type: OCR/source omission.
- Cause: needed short phrase is absent from the retrieved OCR text.
- GraphRAG target: corpus cleaning and alias/noise handling; GraphRAG alone cannot recover facts absent from text unless another clean source has them.

### `139`

- Claim: after surrendering to Nazi Germany, the French government adopted hostile policy toward progressive forces and colonial revolutionary movements.
- Gold evidence: exact Vietnamese-history chunk exists at `lichsu_12/lichsu_12.pdf_103.jpg.txt`.
- Retrieved chunks: broad WWII France chunks from `lichsu_11`, not the decisive Vietnam 1939-1945 chunk.
- Error type: broad/topically related but non-decisive chunks.
- Cause: retrieval matched France/Germany/WWII but missed the Vietnam-specific consequence.
- GraphRAG target: connect global WWII event to Vietnam/Indochina colonial policy node.

### `4521_His_17_11`

- Claim: solving illiteracy after the August Revolution involved education reform/literacy action in the first year.
- Gold evidence: exact `Nha Bình dân học vụ`, anti-illiteracy, 76,000 classes, 2.5 million people appears in `lichsu_12/lichsu_12.pdf_124.jpg.txt`.
- Retrieved chunks: broad summary pages around post-August Revolution, not the exact literacy chunk.
- Error type: retrieval miss within the same topic.
- Cause: top-3 verifier context did not include the decisive page.
- GraphRAG target: event/concept node `Giải quyết nạn dốt` linked to `Nha Bình dân học vụ`, `8-9-1945`, `9-1945 to 9-1946`.

### `7764_MET_His_IE_2021_22` and `4560_His_17_21`

- Claim: first French colonial exploitation led to the formation of the Vietnamese working class.
- Gold evidence: exact chunk exists at `lichsu_11/lichsu_11.pdf_139.jpg.txt`.
- Retrieved chunks: often pages 137-138, which are related to the first exploitation but stop before the decisive working-class formation lines.
- Error type: nearby-page retrieval miss and chunk-boundary issue.
- Cause: decisive evidence is on the next page/chunk.
- GraphRAG target: connect adjacent chunks and build concept relation: `first exploitation` `CAUSED/CONTRIBUTED_TO` `formation of Vietnamese working class`.

## Failure Categories

### Wrong Dates Or Years

- Common in fake-to-real errors.
- Examples: `191_fake`, `188_fake`, `235_fake`.
- Baseline often retrieves the right event but does not compare the claim's date against the evidence date.
- GraphRAG should add temporal nodes and temporal consistency checks.

### Wrong People, Places, Organizations, Or Actors

- Examples: `151_fake`, `203_fake`, `235_fake`, `331_fake`.
- Baseline semantic retrieval treats related names as enough, even when the relation is wrong.
- GraphRAG should extract actor-event-place triples and require relation compatibility.

### Broad But Non-Decisive Chunks

- Examples: `104`/`109`/`111`, `139`, `4521_His_17_11`, `7764_MET_His_IE_2021_22`.
- Retrieved chunks are close by topic but not decisive for the exact claim.
- GraphRAG should expand from matched event/entity nodes to linked source chunks and adjacent chunks.

### OCR Noise Or Source Text Problems

- Examples: `122`, `4521_His_17_11`, `7764_MET_His_IE_2021_22`.
- Some text has OCR noise: `giặc dốt` appears as `giác dốt`, `Việt Nam` as `Viết Nam`, and some phrases are omitted.
- Corpus cleaning is required before GraphRAG extraction; otherwise the graph will encode noisy or missing facts.

### Verifier Reasoning Errors Despite Good Evidence

- Examples: `27`, `191_fake`, `203_fake`, `464_fake`.
- The retrieved evidence is good, but the verifier accepts a false claim or rejects a true claim because it fails to distinguish demand/result, actor direction, date, or scope.
- GraphRAG can help by presenting structured facts, but the verifier prompt should also require explicit comparison of claim facts against evidence facts.

## What GraphRAG Should Fix

- Build explicit nodes for events, people, organizations, places, times, and concepts.
- Extract relation triples with source chunk IDs, especially actor-event-time-place relations.
- Add temporal indexing so claims with years/dates retrieve matching historical intervals.
- Link adjacent source chunks so evidence split across page boundaries can still be found.
- Normalize aliases and OCR variants, such as `Mỹ/Mĩ`, `Việt/Viết`, `giặc/giác`, and organization name variants.
- During verification, compare structured claim facts against structured evidence facts before deciding `real` or `fake`.

## What GraphRAG May Not Fully Fix

- If OCR completely omits a short phrase, graph extraction cannot recover it from that chunk alone.
- If the gold evidence itself is mojibake or cleaner than the corpus OCR, corpus cleaning or better OCR is needed first.
- If the verifier prompt still allows guessing when evidence is insufficient, structured retrieval alone may not prevent wrong labels.

## Recommended Next Step

Proceed to Stage 3 corpus cleaning before entity extraction. The graph quality will depend heavily on normalized text, repaired OCR noise, and stable chunk metadata.
