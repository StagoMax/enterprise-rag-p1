# P3 金标逐题复核报告

- 复核版本：`p3-gold-v4-2026-08-09`
- 基础检索金标：140
- 基础检索纳入计分：135
- 基础检索排除计分：5
- 全部评测行（含图谱、权限、拒答和工具）：240

## 复核结论

逐条检查了题目、期望答案和期望文档正文。只有能在当前语料建立证据链的题目才纳入计分；排除项保留原始标注和原因，不会静默删除。

| 状态 | 数量 |
|---|---:|
| ambiguous | 1 |
| corrected | 4 |
| excluded | 5 |
| expanded | 2 |
| verified | 128 |

## 基础检索 140 道逐题记录

| ID | 类别 | 计分 | 状态 | 期望文档 | 复核备注 |
|---|---|---:|---|---|---|
| rag-001 | rag | 是 | verified | `swg21179559` | 题目、答案与来源正文一致，保留原标注。 |
| rag-002 | rag | 是 | verified | `swg21636093` | 题目、答案与来源正文一致，保留原标注。 |
| rag-003 | rag | 是 | verified | `swg21263677` | 题目、答案与来源正文一致，保留原标注。 |
| rag-004 | rag | 是 | verified | `swg21648497` | 题目、答案与来源正文一致，保留原标注。 |
| rag-005 | rag | 是 | ambiguous | `swg21998452, swg22003256, swg22009455, swg21979065, swg22007664` | The security bulletin is published as several near-identical Red Hat Linux advisory records; all five are evidence-equivalent for this question. |
| rag-006 | rag | 是 | expanded | `swg21469413, swg21605502` | The original ulimit guidance is valid; a DASH/TIP-specific 'Too many open files' technote is an additional equivalent source. |
| rag-007 | rag | 是 | verified | `swg27019359` | 题目、答案与来源正文一致，保留原标注。 |
| rag-008 | rag | 是 | verified | `swg21611073` | 题目、答案与来源正文一致，保留原标注。 |
| rag-009 | rag | 是 | verified | `swg24035040` | 题目、答案与来源正文一致，保留原标注。 |
| rag-010 | rag | 是 | verified | `swg21611699` | 题目、答案与来源正文一致，保留原标注。 |
| rag-011 | rag | 是 | verified | `swg21964202` | 题目、答案与来源正文一致，保留原标注。 |
| rag-012 | rag | 是 | verified | `swg21406783` | 题目、答案与来源正文一致，保留原标注。 |
| rag-013 | rag | 是 | verified | `swg21318593` | 题目、答案与来源正文一致，保留原标注。 |
| rag-014 | rag | 是 | verified | `swg21660890` | 题目、答案与来源正文一致，保留原标注。 |
| rag-015 | rag | 是 | verified | `swg21502037` | 题目、答案与来源正文一致，保留原标注。 |
| rag-016 | rag | 是 | verified | `swg21660890` | 题目、答案与来源正文一致，保留原标注。 |
| rag-017 | rag | 是 | verified | `swg21502037` | 题目、答案与来源正文一致，保留原标注。 |
| rag-018 | rag | 是 | verified | `swg21445430` | 题目、答案与来源正文一致，保留原标注。 |
| rag-019 | rag | 否 | excluded | `swg1PI37248` | The expected PI37248 document concerns PFBC parsing and contains no Portal 8.5 INSTCONFFAILED installation evidence. No corpus document establishes the full question-to-answer mapping. |
| rag-020 | rag | 是 | verified | `swg27045339` | 题目、答案与来源正文一致，保留原标注。 |
| rag-021 | rag | 是 | verified | `swg21636533` | 题目、答案与来源正文一致，保留原标注。 |
| rag-022 | rag | 是 | verified | `swg21451229` | 题目、答案与来源正文一致，保留原标注。 |
| rag-023 | rag | 是 | verified | `swg21406783` | 题目、答案与来源正文一致，保留原标注。 |
| rag-024 | rag | 是 | verified | `swg1PI34677` | 题目、答案与来源正文一致，保留原标注。 |
| rag-025 | rag | 是 | verified | `swg21598779` | 题目、答案与来源正文一致，保留原标注。 |
| rag-026 | rag | 是 | verified | `swg21634612` | 题目、答案与来源正文一致，保留原标注。 |
| rag-027 | rag | 否 | excluded | `swg21268440` | The expected document is about SessionObjectSize NotSerializableException and does not contain the Decision Center IlrStorePolicy ClassCastException. No exact supporting document was found in the corpus. |
| rag-028 | rag | 是 | verified | `swg21067352` | 题目、答案与来源正文一致，保留原标注。 |
| rag-029 | rag | 是 | verified | `swg24039742` | 题目、答案与来源正文一致，保留原标注。 |
| rag-030 | rag | 否 | excluded | `swg27050456` | The expected document is an OMEGAMON MQ Configuration Agent withdrawal notice and does not explain the KCIJPALO ABEND S013. No exact supporting document was found in the corpus. |
| rag-031 | rag | 是 | verified | `swg21639375` | 题目、答案与来源正文一致，保留原标注。 |
| rag-032 | rag | 是 | verified | `swg21163875` | 题目、答案与来源正文一致，保留原标注。 |
| rag-033 | rag | 是 | verified | `swg21308281` | The question describes Installation Manager on a mounted Linux server; the technote directly says not to install it on an NFS-mounted disk and to install it only on a local disk. |
| rag-034 | rag | 是 | expanded | `swg21624731, swg21608705` | Both technotes directly explain the three-second WLM/HA messaging-engine lookup delay and prescribe tuning sib.trm.linger in sib.properties; either document is evidence-equivalent for this question. |
| rag-035 | rag | 是 | verified | `swg21426787` | 题目、答案与来源正文一致，保留原标注。 |
| rag-036 | rag | 是 | verified | `swg21695094` | 题目、答案与来源正文一致，保留原标注。 |
| rag-037 | rag | 是 | verified | `swg27023910` | 题目、答案与来源正文一致，保留原标注。 |
| rag-038 | rag | 是 | verified | `swg21512291` | 题目、答案与来源正文一致，保留原标注。 |
| rag-039 | rag | 是 | verified | `swg21639375` | 题目、答案与来源正文一致，保留原标注。 |
| rag-040 | rag | 否 | excluded | `swg1PI37248` | The expected PI37248 document concerns PFBC parsing and does not contain the supplied Portal profile augmentation failure or portal01_create.log evidence. No exact supporting document was found in the corpus. |
| rag-041 | rag | 是 | verified | `swg21162896` | 题目、答案与来源正文一致，保留原标注。 |
| rag-042 | rag | 是 | verified | `swg21292808` | 题目、答案与来源正文一致，保留原标注。 |
| rag-043 | rag | 是 | verified | `swg21994039` | 题目、答案与来源正文一致，保留原标注。 |
| rag-044 | rag | 是 | verified | `swg21600618` | 题目、答案与来源正文一致，保留原标注。 |
| rag-045 | rag | 是 | verified | `swg21497604` | 题目、答案与来源正文一致，保留原标注。 |
| rag-046 | rag | 是 | corrected | `swg21659259, swg21244384` | The original reinitialize technote is the referenced procedure, while the downgrade technote states the supported major-release rule and the required license precaution. |
| rag-047 | rag | 是 | verified | `swg21618139` | 题目、答案与来源正文一致，保留原标注。 |
| rag-048 | rag | 是 | verified | `swg1PI34677` | 题目、答案与来源正文一致，保留原标注。 |
| rag-049 | rag | 是 | verified | `swg21612222` | 题目、答案与来源正文一致，保留原标注。 |
| rag-050 | rag | 是 | verified | `swg22002443` | 题目、答案与来源正文一致，保留原标注。 |
| rag-051 | rag | 是 | verified | `swg21249798` | 题目、答案与来源正文一致，保留原标注。 |
| rag-052 | rag | 是 | corrected | `swg24043474, swg1PI73197` | The original answer predates the PI73197 fix. The corpus contains both the downloadable fix record and the APAR record that directly answer the 8.5.5.9-or-later question. |
| rag-053 | rag | 是 | verified | `swg21192604` | 题目、答案与来源正文一致，保留原标注。 |
| rag-054 | rag | 否 | excluded | `swg21445801` | The expected document is a post-migration authoring-portlet issue, while the question asks about a blank/corrupted WCM syndicator 'Subscribe Now' popup. The corpus has a different syndicator error but no exact evidence for this symptom. |
| rag-055 | rag | 是 | verified | `swg21701478` | 题目、答案与来源正文一致，保留原标注。 |
| rag-056 | rag | 是 | corrected | `swg21397335` | The source is directly relevant and even shows a Deployment Manager service example, but the original gold answer quoted the older downloadable WASServiceCmd.exe steps. The BPM 8.5 question requires the V8-and-later WASServiceHelper.bat instruction stated in the same technote. |
| rag-057 | rag | 是 | verified | `swg21365841` | 题目、答案与来源正文一致，保留原标注。 |
| rag-058 | rag | 是 | verified | `swg21269136` | 题目、答案与来源正文一致，保留原标注。 |
| rag-059 | rag | 是 | verified | `swg24041563` | 题目、答案与来源正文一致，保留原标注。 |
| rag-060 | rag | 是 | verified | `swg21255545` | 题目、答案与来源正文一致，保留原标注。 |
| rag-061 | rag | 是 | verified | `swg21996508` | 题目、答案与来源正文一致，保留原标注。 |
| rag-062 | rag | 是 | verified | `swg21675316` | 题目、答案与来源正文一致，保留原标注。 |
| rag-063 | rag | 是 | verified | `swg21412061` | 题目、答案与来源正文一致，保留原标注。 |
| rag-064 | rag | 是 | verified | `swg21696083` | 题目、答案与来源正文一致，保留原标注。 |
| rag-065 | rag | 是 | verified | `swg21298897` | 题目、答案与来源正文一致，保留原标注。 |
| rag-066 | rag | 是 | verified | `swg21591076` | 题目、答案与来源正文一致，保留原标注。 |
| rag-067 | rag | 是 | verified | `swg21413628` | 题目、答案与来源正文一致，保留原标注。 |
| rag-068 | rag | 是 | verified | `swg21576245` | 题目、答案与来源正文一致，保留原标注。 |
| rag-069 | rag | 是 | verified | `swg21451229` | 题目、答案与来源正文一致，保留原标注。 |
| rag-070 | rag | 是 | verified | `swg21664629` | 题目、答案与来源正文一致，保留原标注。 |
| rag-071 | rag | 是 | verified | `swg21648986` | 题目、答案与来源正文一致，保留原标注。 |
| rag-072 | rag | 是 | verified | `swg21965783` | 题目、答案与来源正文一致，保留原标注。 |
| rag-073 | rag | 是 | verified | `swg21979066` | 题目、答案与来源正文一致，保留原标注。 |
| rag-074 | rag | 是 | verified | `swg21978641` | 题目、答案与来源正文一致，保留原标注。 |
| rag-075 | rag | 是 | verified | `swg21998312` | 题目、答案与来源正文一致，保留原标注。 |
| rag-076 | rag | 是 | verified | `swg27046676` | 题目、答案与来源正文一致，保留原标注。 |
| rag-077 | rag | 是 | verified | `swg21959224` | 题目、答案与来源正文一致，保留原标注。 |
| rag-078 | rag | 是 | verified | `swg21568844` | 题目、答案与来源正文一致，保留原标注。 |
| rag-079 | rag | 是 | verified | `swg21577138` | 题目、答案与来源正文一致，保留原标注。 |
| rag-080 | rag | 是 | verified | `swg21666489` | 题目、答案与来源正文一致，保留原标注。 |
| rag-081 | rag | 是 | verified | `swg21959714` | 题目、答案与来源正文一致，保留原标注。 |
| rag-082 | rag | 是 | verified | `swg21988389` | 题目、答案与来源正文一致，保留原标注。 |
| rag-083 | rag | 是 | verified | `swg21664126` | 题目、答案与来源正文一致，保留原标注。 |
| rag-084 | rag | 是 | corrected | `swg21980860` | The raw answer was a malformed cause fragment. The corrected gold answer uses the direct instruction in RESOLVING THE PROBLEM. |
| rag-085 | rag | 是 | verified | `swg21220832` | 题目、答案与来源正文一致，保留原标注。 |
| rag-086 | rag | 是 | verified | `swg21417266` | 题目、答案与来源正文一致，保留原标注。 |
| rag-087 | rag | 是 | verified | `swg21663414` | 题目、答案与来源正文一致，保留原标注。 |
| rag-088 | rag | 是 | verified | `swg21500040` | 题目、答案与来源正文一致，保留原标注。 |
| rag-089 | rag | 是 | verified | `swg21656263` | 题目、答案与来源正文一致，保留原标注。 |
| rag-090 | rag | 是 | verified | `swg21642839` | 题目、答案与来源正文一致，保留原标注。 |
| rag-091 | rag | 是 | verified | `swg21380213` | 题目、答案与来源正文一致，保留原标注。 |
| rag-092 | rag | 是 | verified | `swg21687172` | 题目、答案与来源正文一致，保留原标注。 |
| rag-093 | rag | 是 | verified | `swg21674924` | 题目、答案与来源正文一致，保留原标注。 |
| rag-094 | rag | 是 | verified | `swg21572905` | 题目、答案与来源正文一致，保留原标注。 |
| rag-095 | rag | 是 | verified | `swg21974757` | 题目、答案与来源正文一致，保留原标注。 |
| rag-096 | rag | 是 | verified | `swg27044407` | 题目、答案与来源正文一致，保留原标注。 |
| rag-097 | rag | 是 | verified | `swg21417765` | 题目、答案与来源正文一致，保留原标注。 |
| rag-098 | rag | 是 | verified | `swg21501900` | 题目、答案与来源正文一致，保留原标注。 |
| rag-099 | rag | 是 | verified | `swg21592093` | 题目、答案与来源正文一致，保留原标注。 |
| rag-100 | rag | 是 | verified | `swg21982008` | 题目、答案与来源正文一致，保留原标注。 |
| rag-101 | rag | 是 | verified | `swg21662193` | 题目、答案与来源正文一致，保留原标注。 |
| rag-102 | rag | 是 | verified | `swg21691034` | 题目、答案与来源正文一致，保留原标注。 |
| rag-103 | rag | 是 | verified | `swg21655808` | 题目、答案与来源正文一致，保留原标注。 |
| rag-104 | rag | 是 | verified | `swg21651101` | 题目、答案与来源正文一致，保留原标注。 |
| rag-105 | rag | 是 | verified | `swg21971127` | 题目、答案与来源正文一致，保留原标注。 |
| rag-106 | rag | 是 | verified | `swg21690184` | 题目、答案与来源正文一致，保留原标注。 |
| rag-107 | rag | 是 | verified | `swg27049061` | 题目、答案与来源正文一致，保留原标注。 |
| rag-108 | rag | 是 | verified | `swg21395327` | 题目、答案与来源正文一致，保留原标注。 |
| rag-109 | rag | 是 | verified | `swg21688071` | 题目、答案与来源正文一致，保留原标注。 |
| rag-110 | rag | 是 | verified | `swg21618719` | 题目、答案与来源正文一致，保留原标注。 |
| rag-111 | rag | 是 | verified | `swg21902654` | 题目、答案与来源正文一致，保留原标注。 |
| rag-112 | rag | 是 | verified | `swg21967756` | 题目、答案与来源正文一致，保留原标注。 |
| rag-113 | rag | 是 | verified | `swg21445430` | 题目、答案与来源正文一致，保留原标注。 |
| rag-114 | rag | 是 | verified | `swg21480262` | 题目、答案与来源正文一致，保留原标注。 |
| rag-115 | rag | 是 | verified | `swg21690163` | 题目、答案与来源正文一致，保留原标注。 |
| rag-116 | rag | 是 | verified | `swg21244655` | 题目、答案与来源正文一致，保留原标注。 |
| rag-117 | rag | 是 | verified | `swg21442694` | 题目、答案与来源正文一致，保留原标注。 |
| rag-118 | rag | 是 | verified | `swg21412061` | 题目、答案与来源正文一致，保留原标注。 |
| rag-119 | rag | 是 | verified | `swg21982451` | 题目、答案与来源正文一致，保留原标注。 |
| rag-120 | rag | 是 | verified | `swg21529563` | 题目、答案与来源正文一致，保留原标注。 |
| exact-001 | exact_search | 是 | verified | `swg21179559` | 题目显式指定文档 ID；ID、标题、状态和权限范围一致。 |
| exact-002 | exact_search | 是 | verified | `swg21636093` | 题目显式指定文档 ID；ID、标题、状态和权限范围一致。 |
| exact-003 | exact_search | 是 | verified | `swg21263677` | 题目显式指定文档 ID；ID、标题、状态和权限范围一致。 |
| exact-004 | exact_search | 是 | verified | `swg21515420` | 题目显式指定文档 ID；ID、标题、状态和权限范围一致。 |
| exact-005 | exact_search | 是 | verified | `swg21648497` | 题目显式指定文档 ID；ID、标题、状态和权限范围一致。 |
| exact-006 | exact_search | 是 | verified | `swg21998452` | 题目显式指定文档 ID；ID、标题、状态和权限范围一致。 |
| exact-007 | exact_search | 是 | verified | `swg21469413` | 题目显式指定文档 ID；ID、标题、状态和权限范围一致。 |
| exact-008 | exact_search | 是 | verified | `swg27019359` | 题目显式指定文档 ID；ID、标题、状态和权限范围一致。 |
| exact-009 | exact_search | 是 | verified | `swg21611073` | 题目显式指定文档 ID；ID、标题、状态和权限范围一致。 |
| exact-010 | exact_search | 是 | verified | `swg24035040` | 题目显式指定文档 ID；ID、标题、状态和权限范围一致。 |
| exact-011 | exact_search | 是 | verified | `swg21611699` | 题目显式指定文档 ID；ID、标题、状态和权限范围一致。 |
| exact-012 | exact_search | 是 | verified | `swg22011689` | 题目显式指定文档 ID；ID、标题、状态和权限范围一致。 |
| exact-013 | exact_search | 是 | verified | `swg21964202` | 题目显式指定文档 ID；ID、标题、状态和权限范围一致。 |
| exact-014 | exact_search | 是 | verified | `swg21406783` | 题目显式指定文档 ID；ID、标题、状态和权限范围一致。 |
| exact-015 | exact_search | 是 | verified | `swg21318593` | 题目显式指定文档 ID；ID、标题、状态和权限范围一致。 |
| exact-016 | exact_search | 是 | verified | `swg21660890` | 题目显式指定文档 ID；ID、标题、状态和权限范围一致。 |
| exact-017 | exact_search | 是 | verified | `swg22005055` | 题目显式指定文档 ID；ID、标题、状态和权限范围一致。 |
| exact-018 | exact_search | 是 | verified | `swg21998655` | 题目显式指定文档 ID；ID、标题、状态和权限范围一致。 |
| exact-019 | exact_search | 是 | verified | `swg22012345` | 题目显式指定文档 ID；ID、标题、状态和权限范围一致。 |
| exact-020 | exact_search | 是 | verified | `swg21502037` | 题目显式指定文档 ID；ID、标题、状态和权限范围一致。 |
