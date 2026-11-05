# Exam Catalogue Audit — Baseline

**Repository baseline:** `main`  
**Catalogue source:** `backend/exams/catalogue.py`  
**Audit date:** 2026-11-05  
**Purpose:** Establish the exact catalogue inventory before changing rule, passage, input, mistake, or scoring behavior.

## Inventory result

- Catalogue entries in source tuple: 166
- Unique exam profile names: 162
- Exact duplicate names in source tuple: Rajasthan HC STENO/JJA/LDC English; Rajasthan HC STENO/JJA/LDC Hindi; MP High Court Jabalpur English; MP High Court Jabalpur Hindi
- Current catalogue seed tests require all entries to remain unverified until reviewed.
- This is a profile-name inventory, not proof that each profile corresponds to a distinct official examination.

## Current schema observations

The existing `ExamConfiguration` model already stores duration, language/script, passage format/layout, typography, source mode, minimum WPM, required keystrokes, strokes-per-word, error allowance, mistake penalty, trial/review/correction time, input restrictions, scoring mode and JSON scoring/qualification rules, verification status, and official-source metadata.

The existing session start service snapshots many of these fields into each attempt. This is a useful compatibility foundation, but the runtime still has separate scoring-mode branches and the snapshot is manually assembled. The new registry must become the single resolver while retaining the immutable historical snapshot.

## Important baseline risks

1. **Names are not authoritative exam identities.** Similar names may refer to different notifications, posts, stages, or years.
2. **Variants must not be merged by guesswork.** English/Hindi, keyboard layouts, accessibility variants, and recruitment-year variants may share only some rules.
3. **Broad catalogue labels are not executable rules.** Entries such as “State Related Typing Test”, “Other State Related Typing Test”, and “Typing Test Links” must remain catalogue/navigation profiles, not receive invented scoring.
4. **Rule fields can be confused.** Passage minimum words/strokes, candidate input keystrokes, and scoring strokes-per-word are distinct quantities and must have separate units.
5. **Input behavior needs provenance.** Backspace, Delete, arrows, paste, copy, cut, Space, Enter, and Tab must be NOT_SPECIFIED unless a primary source defines them. A practice default must not be represented as an official rule.
6. **Verification must be domain-aware.** An official duration does not verify the passage format, keyboard policy, error taxonomy, or score formula.
7. **Scoring must be deterministic.** Define whether speed is rounded, floored, or compared as a decimal; define Unicode/Hindi stroke measurement and exact penalty units before marking a formula verified.
8. **Historical results must remain reproducible.** A result must retain the exact specification version and scoring-engine version used at attempt time.

## Catalogue profile inventory

The names below are copied from the current source tuple. They are listed for audit and do not imply that any rule has been verified.

1. SSC Typing Test Links
2. SSC Data Processing Assistant Grade-A
3. SSC CHSL 2025 English Test (TCS Interface)
4. SSC CHSL 2025 VH Category English
5. SSC CHSL 2025 Hindi (KurtiDev)
6. SSC CHSL 2025 Hindi (Mangal Font)
7. SSC CGL 2025 Typing Test (TCS)
8. SSC CGL 2025 VH Category
9. SSC CGL 2025 More Strokes Test
10. SSC MTS-ER10321-IX Typing Test
11. SSC GD Typing Test
12. SSC CAG DEO Typing Test
13. Honb Court Related Typing Test
14. Supreme Court of India - JCA Test
15. Bombay High Court - English Test
16. Andhra Pradesh APHC High Court
17. Allahabad High Court - RO & ARO Test
18. Telangana High Court Skill Test
19. Gujarat High Court - Assistant
20. Patna High Court English Test
21. Patna High Court Hindi Test
22. Punjab & Haryana High Court
23. Calcutta High Court Typing
24. MP High Court Jabalpur English
25. MP High Court Jabalpur Hindi
26. Chhattisgarh High Court English
27. Chhattisgarh High Court Unicode
28. Chhattisgarh High Court KurtiDev
29. Delhi High Court - PA / SPA Test
30. Delhi High Court - JJA Test
31. Allahabad HC Junior Assistant (Eng)
32. Allahabad HC Junior Assistant (Hindi)
33. Rajasthan HC STENO/JJA/LDC English
34. Rajasthan HC STENO/JJA/LDC Hindi
35. RRB NTPC GDCE Related Typing Test
36. RRB NTPC Typing Test
37. RRB GDCE Typing Test
38. RRB NTPC Hindi KURTIDEV
39. RRB NTPC Hindi MANGAL Inscript
40. RRB NTPC Hindi MANGAL Remington Gail
41. CAPF HCM Typing Test
42. BSF Head Constable (HCM)
43. BSF HCM English Test
44. BSF HCM Hindi Mangal Gail
45. BSF HCM Hindi Mangal Inscript
46. SSB HCM English Typing Test
47. Delhi Police HC English Test
48. Delhi Police HC Hindi Test
49. CISF Head Constable (HCM)
50. CRPF HCM English Typing
51. CRPF HCM Hindi (Mangal)
52. CRPF HCM Hindi Typing
53. ITBP HCM English Test
54. Army Agniveer Typing Test
55. Delhi NCR Related Typing Test
56. DSSSB Advt. 05/2023 English
57. DSSSB Mangal-Gail-Hindi Test
58. DSSSB Mangal-Inscript-Hindi
59. DSSSB Advt. 01/2024 English
60. DSSSB Hindi Typing Test
61. DDA ASO English Typing
62. DDA JSA English Typing
63. DU NTA Non-Teaching English
64. JNU NTA Non-Teaching English
65. CBSE English Typing Test
66. Delhi Police AWO/TPO Test
67. Bihar State Related Typing Test
68. BPSC Hindi Typing Test
69. Jeevika BRLPS English Test
70. Bihar Police ASI English
71. Bihar Police ASI Hindi
72. BELTRON English Typing Test
73. BELTRON Mangal Gail Hindi
74. BELTRON Mangal Inscript Hindi
75. BELTRON Demo Typing Test
76. Bihar Vidhan Parishad English
77. Bihar Vidhan Parishad Hindi (Kurti)
78. Bihar Vidhan Parishad Hindi (Gail)
79. Civil Courts Deposition Writer (Eng)
80. Civil Courts Deposition Writer (Hindi)
81. Bihar SSC English Typing
82. Bihar SSC Remington Gail Hindi
83. BCECEB Bihar SFC English & Hindi
84. UP State Related Typing Test
85. BHU English & Hindi Typing Test
86. UP Police SI / ASI / CO English
87. UP Police SI / ASI / CO Hindi
88. UPPSC APS Hindi Typing
89. UPPSC APS Mangal Inscript
90. UPSSSC Junior Assistant English
91. UPSSSC Junior Assistant Kurtidev
92. UPSSSC Junior Assistant Mangal
93. UPPCL & UPRVUNL Typing Test
94. UPPSC RO/ARO Krutidev Hindi
95. UPPSC RO/ARO Mangal Hindi
96. UPPSC RO/ARO English Test
97. UPPSC Computer Operator English
98. UPPSC Computer Operator Hindi
99. Other State Related Typing Test
100. CCRAS English Typing Test
101. Kurukshetra University Clerk
102. LUVAS, Lala Lajpat Rai University of Veterinary and Animal Sciences, Hisar
103. HARTRON SETC DEST EXAM
104. Postal PA / SA / MTS DEST EXAM
105. IIT Jodhpur Junior Assistant
106. SPMCIL Test Software
107. NCERT Post LDC English
108. Chandigarh Admin Clerk English
109. NIT Raipur English Typing Test
110. Central Silk Board English Test
111. NBEMS English Test
112. Visva Bharati Non-Teaching Test
113. LAHD-SSRB Junior Assistant
114. NPCIL Assistant Grade-1 English
115. EMRS JSA English Typing Test
116. PGIMER Junior Admin Assistant
117. IGNOU JAT English Typing Test
118. IGNOU JAT Mangal Gail Hindi
119. JIPMER Puducherry English Test
120. DPSR University Assistant
121. DRDO English Typing Test
122. DRDO Hindi Typing Test
123. EPFO SSA English Typing
124. KVS JSA English Typing Test
125. KVS JSA Hindi Typing Test
126. WBPSC Clerkship English Test
127. NIT Patna Junior Assistant
128. Jharkhand State Related Typing Test
129. JIS(CKHT)CCE LDC JSSC Exam
130. Jharkhand High Court Civil Clerk
131. Jharkhand HC English (Adv.03-24)
132. Jharkhand HC Hindi (Adv.03-24)
133. Jharkhand High Court Skill Test
134. Rajasthan State Related Typing Test
135. RSMSSB LDC English Typing Test
136. RSSB Informatics Assistant (Eng)
137. RSSB Informatics Assistant (Hindi)
138. RVUNL Junior Assistant Typing Test
139. AIIMS Related Typing Test
140. AIIMS CRE English Typing Test
141. AIIMS CRE Hindi Mangal Inscript
142. AIIMS CRE Hindi Mangal Gail
143. AIIMS Bhubaneswar DEO English
144. AIIMS JAA English Typing Test
145. AIIMS BHOPAL English Typing Test
146. Speed Booster RKC Test
147. Speed Booster English Typing Test
148. Speed Booster Mangal Remington Gail
149. Speed Booster Mangal Inscript
150. Speed Booster Kurtidev Hindi
151. Maharashtra State Typing Test
152. Bombay High Court English Test
153. MPSC Typist Marathi Remington Gail
154. MPSC Clerk Typist English Test
155. MPSC Marathi Hindi Kurtidev 055
156. MP State Typing Test
157. MP POLICE ASI Mangal Gail Hindi
158. MP POLICE ASI Mangal Inscript
159. Bank Note Press Dewas (MP) English
160. MP-CPCT Mangal Remington Gail
161. MP-CPCT Mangal Inscript Hindi
162. MP-CPCT English Typing Test

## Audit workflow per profile

For each profile, create a reviewed identity record with:
- exact authority, post, notification/recruitment year, and test stage;
- primary official notice/rulebook URL, title, publication date, page and clause;
- language/script and any accessibility or keyboard-layout variant;
- separately verified pattern, passage, input policy, error taxonomy, scoring, and qualification domains;
- unresolved questions and reviewer/date.

Allowed verification values:
- `UNVERIFIED`: no reliable primary-source confirmation;
- `PARTIAL`: only some rule domains supported by authoritative sources;
- `VERIFIED`: all enabled official-rule domains have adequate primary-source provenance and matching automated tests.

A profile can be partially verified without enabling unsupported fields. Do not promote a profile to VERIFIED merely because a few headline values are known.

## Next engineering gate

Before migrating runtime behavior:
1. inspect every profile's current database values and admin edits without mutating them;
2. map existing fields and JSON keys to the canonical schema;
3. identify conflicting/duplicate profile identities;
4. write source-backed profile records;
5. add compatibility tests for current behavior;
6. only then implement the registry resolver and engine adapters.
