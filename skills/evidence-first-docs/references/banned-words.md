# Banned and Loaded Words

Use this list before publishing technical documentation. The point is not to
ban ambition; it is to stop ambition from being mistaken for evidence.

## Rule

A loaded word is allowed only when the same sentence or table row states the
evidence, scope, and status it relies on. Otherwise replace it.

Bad: "The cache is robust and the API is secure."

Good: "The cache returns stale data for at most 30 s after a write (test
T-12, `tested`, single-node configuration). Role Y cannot write table T on
PostgreSQL 14–17 (tests T-04..T-11, `tested`; superuser and DBA out of scope)."

## English

| Avoid | Why it hides the claim | Use instead |
| --- | --- | --- |
| robust | Names a feeling, not a property | state the failure mode and bound |
| secure | Absolute; no threat model | "resists X under threat model Y" |
| safe | Same as secure, often for people | "prevents X; residual risk Y" |
| correct | No oracle or scope | "matches specification S under assumptions A" |
| complete | Almost never true | "covers A, B, C; excludes D" |
| guaranteed | No mechanism or bound | "enforced by M; tested by T" |
| verified | Ambiguous: by whom, what, when? | "model-checked to bound B" / "tested by T" |
| proven | Proof of what, under which assumptions? | "proven in model M; TCB is ..." |
| certified | Certification is scoped and dated | "certified against S by body B on date D" |
| compliant | A mapping is not an audit | "mapped to S; gaps listed in G" |
| obviously / clearly | Skips the argument | give the argument |
| simply / just | Hides complexity and failure modes | state the steps and constraints |
| easy | Relative to whom? | state prerequisites and effort |
| always / never | Absolute; find the exception | state the condition and bound |
| all tests pass | Which tests, where, against what? | exact counts, matrix, scope |
| production-ready | No definition | "meets release gate G; open risks R" |
| best practice | Appeal to authority | cite the source and the trade-off |
| industry standard | Ambiguous | name the standard and clause |
| zero trust | Architecture label, not evidence | name the specific control |
| end-to-end | Which ends? | name the entry and exit points |
| fully tested | No coverage definition | list claim families and tests |
| no known issues | Unknown unknowns are not evidence | "open issues: ...; search date ..." |
| works | Works under which conditions? | state the conditions and observed result |

## Russian

| Избегать | Почему скрывает заявление | Писать вместо |
| --- | --- | --- |
| надёжный | Ощущение, не свойство | режим отказа и граница |
| безопасный | Абсолют без модели угроз | «противостоит X в модели Y» |
| корректный | Нет оракула и области | «соответствует S при допущениях A» |
| полный | Почти никогда не верно | «покрывает A, B, C; не покрывает D» |
| гарантирует | Нет механизма и границы | «обеспечивается M; проверено T» |
| проверено | Кем, что, когда? | «model-checked до границы B» |
| доказано | Доказано что и при каких допущениях? | «доказано в модели M; TCB — ...» |
| сертифицирован | Сертификация имеет область и дату | «сертифицирован по S, орган B, дата D» |
| соответствует | Mapping — не аудит | «сопоставлено с S; пробелы в G» |
| очевидно / ясно | Пропускает аргумент | привести аргумент |
| просто / легко | Скрывает сложность и отказы | шаги и ограничения |
| всегда / никогда | Абсолют; исключение найдётся | условие и граница |
| все тесты проходят | Какие, где, против чего? | точные counts, matrix, scope |
| готов к продакшену | Нет определения | «проходит release gate G; риски R» |
| лучшая практика | Апелляция к авторитету | источник и trade-off |
| отраслевой стандарт | Неоднозначно | название стандарта и пункт |
| полностью протестировано | Нет определения покрытия | список claim families и тестов |
| известных проблем нет | Неизвестные неизвестны | «открытые проблемы: ...; дата поиска ...» |
| работает | При каких условиях? | условия и наблюдённый результат |

## Undefined introduced terms

A compound technical term used as if it were established is a claim about the
domain. It is allowed only when the first use defines it ("X — это", a
mechanism in parentheses or nearby) or the domain's vocabulary names it.
Otherwise define the term at first use or describe the mechanism next to it —
a term-label left undefined is naming, not explaining. See
`references/undefined-terms.md` for the decision card.

## Normative words

When the document defines requirements, use the RFC 2119/8174 keywords
deliberately and define their meaning once:

- **MUST / MUST NOT** — absolute requirement or prohibition.
- **SHOULD / SHOULD NOT** — recommended; the exception needs a reason.
- **MAY** — genuinely optional.

Do not write `must` in prose when you mean "we currently do". That is a
description, not a requirement. Do not use `should` when a reviewer could
fail the release for ignoring it; use `must` and name the check.

## Quantifiers

Replace vague quantifiers with a number, a bound, or a test:

- fast → p95 ≤ X ms under load Y
- many → up to N, tested at N and N+1
- recent → commit SHA and date
- most → N of M, with the excluded list
- rarely → frequency bound or "not observed in N runs"
- soon → date or release

## Final pass

1. Search for each word in this file.
2. For every hit, ask: "What evidence and scope make this true?"
3. If the answer is not adjacent, rewrite or delete.
4. Re-read the sentence with the loaded word removed. If it says the same
   thing, the word was decoration.
