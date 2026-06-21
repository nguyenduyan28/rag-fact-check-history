# Entity Alignment Report

## Summary

- Raw entity mentions: 5866
- Unique normalized type/name entities: 3742
- Exact normalized mentions collapsed: 2124
- Candidate groups generated: 300
- Gemini used: yes
- Gemini decisions: 300
- Gemini errors: 0
- Accepted Gemini merge decisions: 154
- Rejected/low-confidence merge decisions: 0
- Final aligned entities: 3599
- Unique representatives merged beyond exact normalization: 143
- Alias rows: 3742
- Aligned entities with multiple aliases: 420

## Raw Entity Types

| Type | Count |
|---|---:|
| Place | 1313 |
| Time | 1148 |
| Concept | 1119 |
| Event | 925 |
| Organization | 906 |
| Person | 455 |

## Aligned Entity Types

| Type | Count |
|---|---:|
| Concept | 853 |
| Time | 850 |
| Event | 672 |
| Place | 503 |
| Organization | 427 |
| Person | 294 |

## Accepted Merge Examples

- `Hồ Chí Minh` (Person), confidence=0.95: u002111, u002177, u002179, u002202, u002206
- `Đại Cồ Việt` (Organization), confidence=0.95: u001986, u001987
- `Đại Việt` (Organization), confidence=0.9: u001992, u002860
- `Pháp` (Organization), confidence=0.95: u000836, u001823, u001895, u002651
- `Nhật Bản` (Place), confidence=0.95: u001806, u001807, u001824, u002620
- `Liên Xô` (Place), confidence=0.95: u001742, u002541, u002543
- `Mặt trận Việt Nam độc lập đồng minh` (Organization), confidence=0.95: u001757, u001758, u001946
- `Mĩ` (Place), confidence=0.95: u001748, u002589
- `Cộng hòa Nhân dân Trung Hoa` (Organization), confidence=0.95: u001652, u001665, u001668, u002473
- `Cộng hòa Dân chủ Đức` (Place), confidence=0.95: u001658, u002471, u002475
- `Nguyễn Ái Quốc` (Person), confidence=0.95: u002177, u002179, u002206
- `Việt Nam Dân chủ Cộng hoà` (Place), confidence=0.95: u001951, u002786, u002787
- `Anh` (Place), confidence=0.95: u001576, u002374
- `Áo` (Place), confidence=0.95: u001980, u002827
- `Âu Lạc` (Place), confidence=0.95: u001982, u002829
- `Bismarck` (Person), confidence=0.95: u002056, u002059
- `Cao Bằng` (Place), confidence=0.95: u002430, u002432
- `Cham-pa` (Place), confidence=0.95: u001600, u002435
- `Chiến dịch Điện Biên Phủ` (Event), confidence=0.95: u000905, u000906
- `Chính phủ Cách mạng lâm thời Cộng hòa miền Nam Việt Nam` (Organization), confidence=0.95: u001604, u001605

## Output Artifacts

- `data/outputs/graph/entities_raw.json`
- `data/outputs/graph/entities_aligned.json`
- `data/outputs/graph/entity_aliases.json`
- `data/outputs/graph/entity_alignment_decisions.json`
- `data/outputs/graph/entity_alignment_errors.json`
