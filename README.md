# Dev-Sec Skills: Evidence Before Claims

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Format: SKILL.md](https://img.shields.io/badge/format-SKILL.md-orange)](skills/negative-test-first/SKILL.md)
[![Languages: RU / EN](https://img.shields.io/badge/docs-RU%20%2F%20EN-2ea44f)](README.en.md)

Набор агентских скилов для команд, которым недостаточно зелёного теста и
уверенного текста. Здесь собран один рабочий принцип в трёх плоскостях:
**заявление существует только вместе с доказательством, областью действия и
честным статусом.**

Скилы не привязаны к языку программирования, фреймворку или конкретному
стандарту. Они описывают, как агенту думать и что проверять, а references
связывают эти правила с международными и российскими стандартами.

## Зачем это нужно

Агенты хорошо пишут позитивные тесты и убедительные README. Они проверяют,
что код делает то, о чём попросили, и почти никогда — что код отказывает
тому, о чём не просили. В результате появляется зелёный suite, который не
доказывает правило, и документ, который обещает больше, чем проверено.

Эти скилы переворачивают вопрос:

- не «фича работает?», а «какой тест попытался её нарушить?»;
- не «система безопасна?», а «кто именно не смог пройти и при какой модели
  угроз?»;
- не «всё протестировано?», а «какие claim'ы остались `open`, и кто это
  признал?».

## Три скила

| Скил | Когда применять | Главный результат |
| --- | --- | --- |
| [`negative-test-first`](skills/negative-test-first/SKILL.md) | Планирование тестов, проверка покрытия, решение «фича готова», релизный gate | Каждое требование связано с тестом, который пытается его нарушить |
| [`evidence-first-docs`](skills/evidence-first-docs/SKILL.md) | README, архитектура, ADR, API-контракты, security/compliance claims, release notes, audit pack | Claim ledger: механизм, evidence, scope, status, ограничения |
| [`invariant-first-code`](skills/invariant-first-code/SKILL.md) | Auth, права, данные, транзакции, миграции, конкурентность, API, секреты, supply chain | Инвариант, точка принуждения, fail-closed и негативная проверка |

Скилы дополняют друг друга:

1. `invariant-first-code` называет, что должно быть всегда истинно.
2. `negative-test-first` пытается это нарушить.
3. `evidence-first-docs` фиксирует, что именно доказано, где и с какими
   ограничениями.

## Общие принципы

- **Claim, а не настроение.** «Безопасно» и «корректно» — не утверждения.
  Утверждение должно быть фальсифицируемым.
- **Негатив первым.** Позитивный тест — дешёвая половина. Покрытие начинается
  с попытки нарушения.
- **Scope рядом с claim.** Версии, платформы, привилегированные акторы и
  исключения указываются там же, где обещание.
- **Статус, а не вера.** `proven`, `model-checked`, `tested`,
  `static-refinement`, `reviewed`, `open` — разные вещи.
- **Артефакт — не доказательство.** Наличие отчёта, теста или PDF не значит,
  что проверка что-то доказала. Нужен результат, область и воспроизводимость.
- **Стандарт-агностичность.** Ядро скилов не называет стандартов. Связь с
  ними — в отдельном crosswalk.

## Стандарты

Ядро опирается на инженерные практики, которые встречаются в NIST SSDF,
NIST SP 800-160, OWASP ASVS, ISO/IEC/IEEE 29148/42010/29119, ISO/IEC 25010,
CWE/SARIF, SLSA, SPDX/CycloneDX, RFC 2119/8174 и Diátaxis.

Российские требования — ФСТЭК 55, 76, 64 и ГОСТ Р 56939-2024 / 71207-2024 —
не растворяются в ядре. Они собраны в
[`references/standards-map.md`](references/standards-map.md) вместе с
международными аналогами. Это **crosswalk, а не сертификация и не аудит**:
соответствие стандарту нельзя объявлять по таблице.

Скачанные свободно доступные документы и ссылки на платные ISO — в
[`references/standards/SOURCES.md`](references/standards/SOURCES.md).

## Концепт: конвейер верификации

Каталог [`spec/`](spec/README.md) — знаниевый слой системы, которая собирает
эти скилы в конвейер: default deny на merge, provenance как taint, таксономия
ячеек вместо накопления уроков, реестр вердиктов и явная граница обещания L2.

- [`spec/conveyor/CONCEPT.md`](spec/conveyor/CONCEPT.md) — концепт с реестром
  утверждений C-01…C-26; английская версия —
  [`CONCEPT.en.md`](spec/conveyor/CONCEPT.en.md).
- [`spec/conveyor/cell-registry.schema.json`](spec/conveyor/cell-registry.schema.json)
  — машиночитаемая ячейка.
- [`spec/conveyor/cells.seed.yaml`](spec/conveyor/cells.seed.yaml) — 12
  сид-ячеек из шести категорий инвариантов, все `open`.
- [`spec/conveyor/guard-grammar.md`](spec/conveyor/guard-grammar.md) — что L2
  может и чего не может проверять; английская версия —
  [`guard-grammar.en.md`](spec/conveyor/guard-grammar.en.md).
- [`spec/conveyor/product-trials.md`](spec/conveyor/product-trials.md) — граница
  продуктовых испытаний: критерии входа, метрики и протокол замера; английская
  версия — [`product-trials.en.md`](spec/conveyor/product-trials.en.md).
  Пороги N = 87,5 % и U = 0,0 % зафиксированы с артефактами; испытания ещё не
  открыты — открытие требует baseline и чек-листа V2-33.
- [`schemas/run-record.schema.json`](schemas/run-record.schema.json) — запись
  одного исполненного прогона: commit, команда, exit code, хэши лога и
  артефакта, счётчики. Проверяется в L1/L2 (`claim_lint`).
- [`spec/pilots/rbac_pg/`](spec/pilots/rbac_pg/README.md) — пилотный реестр на
  29 ячеек: 26 non-open, 3 open, 0 ошибок CL1/CL3/CL4. Для 24 из 27 детекторов
  есть mutation fixture, ещё 3 — документированный `mutation_exemption`
  ([`mutations/`](spec/pilots/rbac_pg/mutations/README.md)).

Статус фазы 0: документ, схема, `cell_lint` и один пилотный реестр. Реестра
для production нет. Числа вроде «~200 ячеек» и «45 → 15 минут» помечены
`open` — это design intent, а не измерение; пилот дал 29 ячеек на одно
расширение.

## Структура

```text
skills/
  negative-test-first/
    SKILL.md
    README.md
    README.en.md
  evidence-first-docs/
    SKILL.md
    README.md
    README.en.md
    references/
      banned-words.md
      evidence-template.md
  invariant-first-code/
    SKILL.md
    README.md
    README.en.md
    references/
      invariant-template.md
      review-checklist.md
references/
  standards-map.md
  standards/
    SOURCES.md
    downloaded/
schemas/
  claim-ledger.schema.json
  README.md
tools/
  claim_lint.py
  cell_lint.py
  status_diff.py
styles/
  RussianAbsolutes/
    BannedAbsolutes.yml
  config/
    vocabularies/
      RussianAbsolutes/
        accept.txt
  README.md
ci/
  claim-lint.yml
  cell-lint.yml
evals/
  evals.json
  iteration-1/
    RESULTS.md
  iteration-2/
    evals.json
    RESULTS.md
  linter/
    run_evals.py
    cases/
  cell-lint/
    run_evals.py
    cases/
  fuzz/
    run_evals.py
    cases/
  fuzz-triage/
    run_evals.py
    cases/
  coverage/
    run_evals.py
    cases/
  iteration-3/
    RESULTS.md
  iteration-4/
    RESULTS.md
spec/
  README.md
  conveyor/
    CONCEPT.md
    CONCEPT.en.md
    cell-registry.schema.json
    cells.seed.yaml
    guard-grammar.md
    guard-grammar.en.md
    product-trials.md
    product-trials.en.md
  fuzz/
    README.md
    corpus/claim-lint/
    runs/claim-lint-2026-11-07.json
    triage/claim-lint-2026-11-07.yaml
  coverage/
    README.md
    2026-11-07-rbac-pg.json
    2026-11-07-craft-i18n.json
  pilots/
    rbac_pg/
      cells.yaml
      README.md
      mutations/
        mutations.yaml
        run_mutations.py
        README.md
```

## Установка

Скилы нейтральны к агенту: это каталоги с `SKILL.md`. Скопируйте нужный
каталог туда, где агент ищет скилы.

```bash
git clone <repo-url> dev-sec-skills
cp -r dev-sec-skills/skills/negative-test-first ~/.config/opencode/skills/
cp -r dev-sec-skills/skills/evidence-first-docs ~/.config/opencode/skills/
cp -r dev-sec-skills/skills/invariant-first-code ~/.config/opencode/skills/
```

Для другого агента положите `SKILL.md` и его `references/` в каталог скилов
этого агента. `README.md` рядом со скилом — для человека, не для загрузки в
контекст.

## Как пользоваться

- Перед релизом: прогоните `negative-test-first` по claim'ам и проверьте,
  какие из них не имеют нарушающего теста.
- Перед публикацией README или audit pack: прогоните `evidence-first-docs`,
  чтобы убрать неподтверждённые абсолюты и добавить scope.
- Перед merge security-чувствительного изменения: прогоните
  `invariant-first-code` по чеклисту и проверьте, что guard нельзя обойти и
  что тест падает при его удалении.
- При разборе инцидента: добавьте именованный урок в тест, а не только в
  комментарий.

## Проверки

Все статические гейты запускаются одной командой (V2-08):

```bash
make verify
```

Она прогоняет адверсариальные наборы (`evals/`), CL1–CL6 по сид-реестру и по
двум пилотным реестрам вместе с их claim-леджерами, L1–L5 по леджерам, гейт
эскалации статусов и отчёт покрытия по двум пилотам. Пилоты ищутся по
`PILOT_ROOT` (по умолчанию `../rbac_pg`) и `PILOT2_ROOT`
(`../astraoffice/craft-i18n`); если цели нет, команда падает, а не пропускает
гейт.

Mutation-прогоны вынесены: `make mutations` — `rbac_pg` на живом PostgreSQL;
`make mutations-i18n` — фикстуры `craft-i18n`, нужен только cargo;
`make mutations-all` — оба набора; `make verify-all` — verify плюс оба набора.

`make verify` доказывает внутреннюю согласованность реестров, леджеров и
evals, а не истинность свойств и не чистоту production-реестра. Один известный
пробел зафиксирован в `evals/status-diff` (пере-датировка).

## Языки

- `SKILL.md` — английский, чтобы скил работал в мультиязычных агентах.
- `README.md` — русский.
- `README.en.md` — английский.
- Внутри скилов нет языковых приложений: примеры и правила применимы к
  любому стеку.

## Статус

Это версия `0.1`: три скила, crosswalk, шаблоны evidence, три набора evals для
скилов, шесть наборов для линтеров и каталог `spec/` с концептом конвейера.
Результаты — в [`evals/iteration-1/RESULTS.md`](evals/iteration-1/RESULTS.md),
[`evals/iteration-2/RESULTS.md`](evals/iteration-2/RESULTS.md),
[`evals/iteration-3/RESULTS.md`](evals/iteration-3/RESULTS.md) и
[`evals/iteration-4/RESULTS.md`](evals/iteration-4/RESULTS.md).

Исполняемая часть: `tools/claim_lint.py` (L1–L5 над claim-леджером, Vale-first
для прозы, встроенный сканер как fallback; L2 проверяет run-record — хэши лога и
артефакта, exit code, дату, исполненные ID — и сверяет артефакт с его блобом на
процитированном коммите; tool-output для `model-checked`/`proven` — хэш вывода,
exit code, дату и bound), `tools/status_diff.py` (гейт эскалации статусов между
релизами: переход вверх требует новой evidence), `tools/unroutable.py` (доля
`unroutable` в таксономии) и `ci/claim-lint.yml` — шаблон GitHub Actions для
целевого репозитория.
Адверсариальные кейсы линтера — [`evals/linter/`](evals/linter/): 35/35
проходят, включая негативный контроль самого runner'а, кейсы для Rust
`#[test] fn`, 8 кейсов run-record (валидный, хэш артефакта, хэш лога,
неисполненный ID, ненулевой exit, отсутствие записи, несовпадение даты,
несовпадение счётчиков), два кейса V2-09: `unrelated-commit` (коммит
резолвится, но артефакт с тех пор изменился) и `empty-claims` (пустой леджер
обязан упасть, а не пройти вакуумно), и семь кейсов V2-10 `tool-output-*`
(валидная запись, хэш вывода, отсутствующий вывод, ненулевой exit, дата,
`model-checked` без вывода, `model-checked` без bound). Исторический прогон из
12 кейсов — `evals/iteration-3/RESULTS.md`.

Для реестра ячеек есть `tools/cell_lint.py` (CL1–CL6: структура, покрытие,
evidence, трассировка, таксономия, гейт эскалации статуса; детектор
`runtime-enforcement` требует негативный тест, а ячейка — `enforced_at`,
`oracle` и `violation_response`) и шаблон `ci/cell-lint.yml`. Его кейсы — [`evals/cell-lint/`](evals/cell-lint/): 40/40,
тоже с негативным контролем runner'а. Это синтетические fixtures, а не
доказательство чистоты production-реестра.

Фаззинг-адаптер `tools/fuzz_run.py` (V2-17) запускает цель по seed-корпусу и
случайным мутациям с фиксированным seed, проверяет каждый запуск по явным
oracle-правилам и пишет запись по `schemas/fuzz-run.schema.json`. Записанный
прогон — [`spec/fuzz/runs/claim-lint-2026-11-07.json`](spec/fuzz/runs/claim-lint-2026-11-07.json):
5 seed-леджеров, 150 мутаций, 155 исполнений, seed 20261107, verdict `clean`;
`make fuzz-claim-lint` повторяет прогон и сверяет `executions_digest`.
Кейсы адаптера — [`evals/fuzz/`](evals/fuzz/): 5/5. Мутатор случайный, без
coverage guidance: `clean` означает «этот oracle ничего не увидел в этом
бюджете», а не отсутствие багов в цели. Гейт триажа `tools/fuzz_triage.py`
(V2-18) требует, чтобы каждая находка стала ячейкой, детектором и mutation
fixture — или была отклонена с записанной причиной; stale-запись, неразрешённая
ячейка и fixture, а также verdict, расходящийся с `findings`, — ошибки. Его
кейсы — [`evals/fuzz-triage/`](evals/fuzz-triage/): 13/13.

Отчёт покрытия `tools/coverage_report.py` (V2-20) проверяет, что процитированный
символ существует (CV1, всегда ошибка), и измеряет символы suite'а, не
отображённые ни на артефакт, ни на claim, ни на негативный тест (CV2), stale
claims (CV3) и non-open детекторы без mutation fixture или exemption (CV4).
Пороги для CV2–CV4 опциональны: `make verify` падает только на висячей ссылке.
Записанное измерение 2026-11-07: `rbac_pg` — 80 символов, 67 mapped, 13
unmapped в двух файлах, которые никто не цитирует, 0 stale, 0 без fixture; `craft-i18n` — 26
из 26 mapped, 0 stale, 0 без fixture. Маппинг файловый, извлечение символов —
узкий сканер, а не AST: отчёт показывает, какие файлы никто не отобразил, но не
доказывает, что детектор исполняет каждый тест в отображённом файле. Кейсы —
[`evals/coverage/`](evals/coverage/): 14/14; снимки измерения — в
[`spec/coverage/`](spec/coverage/README.md).

Пилотный реестр на реальном репозитории — [`spec/pilots/rbac_pg/`](spec/pilots/rbac_pg/README.md):
29 ячеек, 26 non-open, 3 open, 0 ошибок CL1/CL3/CL4 при прогоне с claim-леджером.
Для 24 из 27 детекторов есть mutation fixture: названный suite падает ровно на
предсказанных тестах, когда механизм удалён; ещё 3 — документированный
`mutation_exemption`, потому что мутацией их не сломать. Claim-леджер rbac_pg
покрывает 7 из 29 ячеек. Чистый lint означает внутреннюю согласованность, а не
истинность свойств.

Второй пилот — [`spec/pilots/craft-i18n/`](spec/pilots/craft-i18n/README.md),
намеренно не-RBAC и не-БД: Rust-крейт, проверяющий каталоги переводов.
14 ячеек (13 tested, 1 open), 13 детекторов, 12 из 13 с mutation fixture и один
документированный exemption; claim-леджер из 8 claim'ов, 0 замечаний L1–L5.
Открытая CELL-002 — реальный пробел: Unicode Cf-символы (U+202E, U+200B,
U+2066) проходят проверку, а U+0007 и U+FEFF отклоняются.

Пока это дисциплина и документация, а не сертификат и не замена аудиту.

## Лицензия

MIT — см. [LICENSE](LICENSE). Сторонние стандарты сохраняют свои лицензии;
см. [`references/standards/SOURCES.md`](references/standards/SOURCES.md).
