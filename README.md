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
crosscheck/
  c02-row-model/
    Cargo.toml
    Cargo.lock
    TARGET
    README.md
    src/
      model.rs
      main.rs
schemas/
  claim-ledger.schema.json
  fuzz-run.schema.json
  fuzz-triage.schema.json
  invariant-catalog.schema.json
  run-record.schema.json
  proof-manifest.schema.json
  sarif-evidence.schema.json
  tool-output.schema.json
  README.md
tools/
  bounded_check.py
  cell_lint.py
  choke_points.py
  claim_lint.py
  coverage_report.py
  diff_coverage.py
  fuzz_run.py
  fuzz_triage.py
  invariant_catalog.py
  mutation_plan.py
  proof_plan.py
  sarif_evidence.py
  status_diff.py
  unroutable.py
styles/
  RussianAbsolutes/
    BannedAbsolutes.yml
  config/
    vocabularies/
      RussianAbsolutes/
        accept.txt
  README.md
.github/
  workflows/
    fuzz-nightly.yml
ci/
  cell-lint.yml
  claim-lint.yml
  diff-coverage.yml
  mutation-changed.yml
evals/
  evals.json
  README.md
  iteration-1/
    RESULTS.md
  iteration-2/
    evals.json
    RESULTS.md
  iteration-3/
    RESULTS.md
  iteration-4/
    RESULTS.md
  linter/
    run_evals.py
    cases/
  cell-lint/
    run_evals.py
    cases/
  status-diff/
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
  diff-coverage/
    run_evals.py
    cases/
  choke-points/
    run_evals.py
    cases/
  mutation-plan/
    run_evals.py
  invariant-catalog/
    run_evals.py
  sarif/
    run_evals.py
  bounded-check/
    run_evals.py
  proof-plan/
    run_evals.py
    mutation_selftest.py
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
    runs/claim-lint-2026-11-08-schedule.json
    triage/claim-lint-2026-11-07.yaml
  coverage/
    README.md
    2026-11-07-rbac-pg.json
    2026-11-07-craft-i18n.json
  diff-coverage/
    README.md
    2026-11-07-rbac-pg.json
    2026-11-07-craft-i18n.json
  choke-points/
    README.md
    rules.yaml
    2026-11-07-rbac-pg.json
    2026-11-07-craft-i18n.json
  invariants/
    README.md
    catalog.yaml
    2026-11-07-coverage.json
  sarif/
    README.md
    adapters.yaml
    fixtures/
    2026-11-07-report.json
  static-analysis/
    README.md
    rules/
      ci-supply-chain-2026-11-07.yml
    runs/
      ci-craft-i18n-2026-11-07.sarif
      ci-craft-i18n-2026-11-07.report.json
  proofs/
    README.md
    manifest.yaml
    c02-bound-2026-11-07.md
    runs/
      c02-crosscheck-2026-11-07.json
      c02-crosscheck-2026-11-07.log
      c02-mutants-2026-11-07.json
      c02-mutants-2026-11-07.log
  red-team/
    README.md
    run_drills.py
    2026-11-08-drills.json
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
двум пилотным реестрам вместе с их claim-леджерами, L1–L6 по леджерам, гейт
эскалации статусов и отчёт покрытия по двум пилотам. Пилоты ищутся по
`PILOT_ROOT` (по умолчанию `../rbac_pg`) и `PILOT2_ROOT`
(`../astraoffice/craft-i18n`); если цели нет, команда падает, а не пропускает
гейт.

Без соседних checkout'ов доступен `make verify-ci` — тот же набор без пилотных
гейтов; его гоняет CI на каждый push. Передача репозитория (окружение, ключи,
ритуал изменения, открытые дыры) — в [`docs/handover.md`](docs/handover.md).

В pull request замечания линтера можно получить аннотациями: `claim_lint --format github`
печатает `::error`/`::warning` с файлом и строкой (по умолчанию только ошибки,
`--annotations warning` добавляет предупреждения). Шаблон `ci/claim-lint.yml` вызывает
линтер в этом режиме, поэтому замечание встаёт на строку изменённого claim'а, а не
только в лог.

Diff-покрытие вынесено из `verify` так же, как mutation-прогоны: гейту нужен
base ref, а `verify` сравнивает рабочее дерево с последним коммитом этого
репозитория. `make diff-coverage` прогоняет DC1–DC5 по двум фиксированным
диапазонам, `make diff-coverage-record` пишет снимки в `spec/diff-coverage/`.
Скан choke points тоже вынесен: `make choke-points` печатает очередь ревью по
двум пилотам, `make choke-points-record` пишет снимки в `spec/choke-points/`;
порог CP1 не включён в `verify`, пока не измерен и не снижен шум правил.

Mutation-прогоны вынесены: `make mutations` — `rbac_pg` на живом PostgreSQL;
`make mutations-i18n` — фикстуры `craft-i18n`, нужен только cargo;
`make mutations-all` — оба набора; `make verify-all` — verify плюс оба набора.

Concurrency-оракул вынесен туда же: `make concurrency-rbac` поднимает временную
БД на стенде `MUTATION_DSN` и выпускает 8 одновременных неудачных входов по
одной учётке; `make concurrency-rbac-mutants` ломает `register_auth_failure`
(stale read и снятая блокировка) и требует, чтобы оракул упал — 2/2 мутанта.
Инвариант: `failed_attempts == 4 + (инкременты, которые продукт сам записал в
журнал)`, поэтому поздняя сессия не делает проверку флаки.

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
скилов, тринадцать наборов для линтеров и каталог `spec/` с концептом конвейера.
Результаты — в [`evals/iteration-1/RESULTS.md`](evals/iteration-1/RESULTS.md),
[`evals/iteration-2/RESULTS.md`](evals/iteration-2/RESULTS.md),
[`evals/iteration-3/RESULTS.md`](evals/iteration-3/RESULTS.md) и
[`evals/iteration-4/RESULTS.md`](evals/iteration-4/RESULTS.md).

Исполняемая часть: `tools/claim_lint.py` (L1–L6 над claim-леджером, Vale-first
для прозы, встроенный сканер как fallback; L2 проверяет run-record — хэши лога и
артефакта, exit code, дату, исполненные ID — и сверяет артефакт с его блобом на
процитированном коммите; tool-output для `model-checked`/`proven` — хэш вывода,
exit code, дату, обязательный `status` и bound; L6 требует объявить общий тест
через `shared_tests` с причиной и оставляет non-open claim хотя бы один
собственный тест), `tools/status_diff.py` (гейт эскалации статусов между
релизами: переход вверх требует новой evidence), `tools/unroutable.py` (доля
`unroutable` в таксономии) и `ci/claim-lint.yml` — шаблон GitHub Actions для
целевого репозитория.
Адверсариальные кейсы линтера — [`evals/linter/`](evals/linter/): 70/70
проходят, включая негативный контроль самого runner'а, кейсы для Rust
`#[test] fn`, 8 кейсов run-record (валидный, хэш артефакта, хэш лога,
неисполненный ID, ненулевой exit, отсутствие записи, несовпадение даты,
несовпадение счётчиков), два кейса V2-09: `unrelated-commit` (коммит
резолвится, но артефакт с тех пор изменился) и `empty-claims` (пустой леджер
обязан упасть, а не пройти вакуумно), семь кейсов V2-10 `tool-output-*`
(валидная запись, хэш вывода, отсутствующий вывод, ненулевой exit, дата,
`model-checked` без вывода, `model-checked` без bound), пять кейсов V2-28
(`unverified` при exit 0, таймаут с обрезанным логом, `timed_out`,
противоречащий статусу, запись без `status`, open claim с честной
`unverified`-записью), шесть кейсов V2-34 `shared-*` (необъявленный общий
тест, объявленный sharing без собственного теста, sharing с собственным
тестом, id не из `tests`, пустая причина, open claim) и семь кейсов V2-35
`sanitizer-*` (валидная ASan-запись, clean-запись с finding-строкой в выводе,
failed-прогон, `unverified` у tested claim, запись без `status`, хэш вывода,
`sanitizer_runs` не на `kind=test`) и семнадцать кейсов V2-36
`static-analysis-*` (валидная запись с `covered`-маршрутизацией, реальная
находка как `out-of-scope`, запись не на `kind=static-analysis`, хэши правил и
SARIF, `unverified`, `unmapped`, authored fixture, дубль и пропуск в triage,
несуществующая ячейка, `not-a-bug`/`out-of-scope` без причины,
`static-refinement` без записи, engine, которого нет в отчёте, SARIF и отчёт
по URL). Исторический прогон из 12 кейсов — `evals/iteration-3/RESULTS.md`.

Bounded-прогон `tools/bounded_check.py` (V2-28) запускает внешний инструмент
в отдельной группе процессов и убивает её по wall-clock bound. Запись
`tool_output` получает обязательный `status`: `completed` (процесс завершился
до bound), `unverified` (bound истёк, группа убита), `failed` (non-zero exit)
или `error` (супервизор не смог стартовать). `timed_out`, `bound_seconds` и
`elapsed_seconds` записываются явно; L1 отвергает `timed_out`, противоречащий
статусу, L2 не даёт `status != completed` поддерживать non-open claim.
Открытый claim может честно хранить `unverified`-попытку. Кейсы —
[`evals/bounded-check/`](evals/bounded-check/): 10/10, включая выживание
внучереннего процесса после `killpg` и два интеграционных прогона
`claim_lint`. Супервизор классифицирует собственный дочерний процесс и не
доказывает семантику реального checker'а; ребёнок, ушедший из группы через
double-fork, может пережить kill.

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

Ночной replay записанного прогона (V2-19) живёт в
[`.github/workflows/fuzz-nightly.yml`](.github/workflows/fuzz-nightly.yml): cron
`30 2 * * *` и `workflow_dispatch`, без `push`/`pull_request`, поэтому красный
прогон не блокирует merge. Workflow реплеит `make fuzz-claim-lint`, падает на
расхождении `executions_digest` и выгружает артефакт `fuzz-record-<run_id>` на 90
дней. Первый прогон — [42394278295](https://github.com/Bra1nZ/dev-sec-skills/actions/runs/42394278295):
success, commit `3110214`, digest `93e1af3183658aa6…`, seed 20261107, 155
исполнений, 0 находок. Ночной schedule сработал впервые 2026-11-08:
[42466635404](https://github.com/Bra1nZ/dev-sec-skills/actions/runs/42466635404),
event `schedule`, commit `7bf8192`, старт `09:18:42Z` при объявленном cron `02:30Z`,
digest совпал, 0 находок; скачанный артефакт закоммичен как
[`spec/fuzz/runs/claim-lint-2026-11-08-schedule.json`](spec/fuzz/runs/claim-lint-2026-11-08-schedule.json).
Это доказательство детерминизма и целостности входов, а не поиск новых багов;
задержанный или пропущенный запуск никто не отслеживает.

Event-driven `proven` (V2-29) — `tools/proof_plan.py` и
[`spec/proofs/manifest.yaml`](spec/proofs/manifest.yaml): каждая доказанная
claim объявляет код, модель, encoding и tooling, от которых зависит, а diff
решает, какие доказательства обязаны перепрогнаться. Манифест объявляет два
bounded-проверки, P-01 (согласие) и P-02 (mutation control), для `tested`
claim'ов C-38/C-39: согласие внутри объявленного словаря не доказывает
универсальное утверждение, поэтому статус не поднимается.
[`crosscheck/c02-row-model/`](crosscheck/c02-row-model/) — независимая модель
row-грамматики craft-i18n: 69 430 входов, 0 расхождений, 22/22 мутанта пойманы;
target пиннится `TARGET` и не модифицируется. `make proof-plan` берёт merge
base `origin/main..HEAD`; на `a3293ec..4f3e25c` — 2 fresh / 0 rerun, на
docs-only `02be7ab~1..02be7ab` — 0 rerun. Кейсы —
[`evals/proof-plan/`](evals/proof-plan/): 36/36; восемь мутаций самого
планировщика проверяет `make proof-plan-selftest` (вне `verify`, ~80 с).
Планировщик не проверяет хэш записи (это делает `claim_lint`) и не доказывает,
что модель соответствует коду; свежесть — сравнение времени, поэтому запись,
снятая со stale checkout, выглядит свежей. Изменение target после пина не
видно планировщику: `claim_lint` L2 сверяет процитированный артефакт с блобом
на коммите.

Силу гейтов измерили на реальных артефактах (C-35):
[`spec/red-team/run_drills.py`](spec/red-team/run_drills.py) берёт леджер
craft-i18n, его записанный cargo-лог и реестр ячеек, применяет по одной атаке на
drill и требует ожидаемый exit code и сообщение. 17 из 18 атак блокируются; одна
проходит молча и записана как пробел: пере-датировка прогона вместе с заменой
`allowed_signers` и пере-подписью (C-13). Чистая пере-датировка больше не
проходит: якорь run_record покрывает `started_at`/`finished_at`, и правка падает
на L2.
Заимствование реальных тестов другой claim (V2-34) теперь блокирует L6:
открытая C-08, получившая тесты C-01, падает, даже если sharing объявлен, потому
что у неё нет собственного теста. Drill с ожиданием `allowed` падает, если гейт
начнёт блокировать, поэтому запись не устареет молча. Результат — [`spec/red-team/2026-11-08-drills.json`](spec/red-team/2026-11-08-drills.json);
drill'ы требуют checkout craft-i18n и в `make verify` не входят.

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

Diff-покрытие `tools/diff_coverage.py` (V2-07) проверяет только choke points,
объявленные в `enforced_at`: изменённый путь или символ без non-open claim —
DC1/DC2, нераспознанное объявление — всегда ошибка DC3, пустой диапазон и
реестр без объявлений — явные info DC4/DC5. `open` claim покрытием не
считается. Символы локализует `tools/choke_points.py`: Python — `ast`
(декораторы входят в спан), Rust и SQL — структурные лексеры комментариев и
строк, SQL-спан покрывает всё `CREATE ... FUNCTION ...;` вместе с
dollar-quoted телом. Поэтому правка тела SQL-функции, декоратора или `}` в
блочном комментарии Rust видна; token-fallback по маскированным строкам
остаётся только там, где парсер не нашёл определение.
Записанное измерение 2026-11-07: `rbac_pg` `v1.3.1..HEAD` — 110 изменённых
файлов, 1 объявленный путь и 1 символ, 2 из 2 mapped; `craft-i18n`
`f0dd77b^..f0dd77b` — 3 файла, 2 из 2 mapped. 100 % — это два объявления
(CELL-001 и CELL-003), а не 43 ячейки: реестр без `enforced_at` получает DC5,
а не покрытие. Кейсы — [`evals/diff-coverage/`](evals/diff-coverage/): 19/19;
метод и границы — в [`spec/diff-coverage/`](spec/diff-coverage/README.md);
шаблон PR-гейта — [`ci/diff-coverage.yml`](ci/diff-coverage.yml).

Извлечение choke points `tools/choke_points.py` (V2-22) ищет структурных
кандидатов в обычном коде и маппит их на классы ячеек по
[`spec/choke-points/rules.yaml`](spec/choke-points/rules.yaml): signals решают,
что считать кандидатом, rules упорядочены и валидируются по enum'ам
`cell-registry.schema.json`; кандидат без правила — `unclassified`, а не
`other`, и это видимый пробел правил, а не класс таксономии. Измерено
2026-11-07: `rbac_pg` — 75 файлов, 1585 определений, 1413 кандидатов, 867
classified / 546 unclassified (38,6 %); `craft-i18n` — 9 файлов, 128
определений, 64 кандидата, 47 / 17 (26,6 %); вместе 914/1477 = 61,9 %
classified. Кейсы — [`evals/choke-points/`](evals/choke-points/): 14/14; метод,
замер и границы — в [`spec/choke-points/`](spec/choke-points/README.md);
targets — `make choke-points` и `make choke-points-record`. Порог CP1 не
включён в `make verify`, пока шум не снижен; совпадение класса — гипотеза, не
доказательство и не cell.

Статический анализ становится evidence только с записью и triage (V2-36):
`schemas/static-analysis-run.schema.json` фиксирует engine, команду, набор
правил и его хэш, коммит цели, сырой SARIF, нормализованный отчёт и ровно одно
решение на каждую находку. `covered`/`new` разрешаются в ячейку, детектор и
mutation fixture; `not-a-bug`/`out-of-scope` требуют причины. `claim_lint` L1
проверяет форму, L2 — хэши правил и обоих выходов, наличие engine в отчёте,
нулевые `unmapped` и `fixture_inputs`, биекцию triage с отчётом, L4 требует
запись для `static-refinement`. Записанный прогон
[`spec/static-analysis/`](spec/static-analysis/README.md) — Semgrep с тремя
правилами, написанными здесь; пять находок, все `out-of-scope`, потому что
таксономия пилота не владеет supply-chain классом. Правила авторские, а не
vendored: Semgrep Registry Rules License v1.0 запрещает распространение, и
попытка с `p/ci` в репозиторий не попала. Кейсы канала —
[`evals/linter/`](evals/linter/): 17 новых; адаптерные — 17.

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
документированный exemption; claim-леджер из 9 claim'ов (C-09 —
`static-refinement` с записанным static-analysis прогоном), 0 замечаний L1–L6.
Открытая CELL-002 — реальный пробел: Unicode Cf-символы (U+202E, U+200B,
U+2066) проходят проверку, а U+0007 и U+FEFF отклоняются.

Пока это дисциплина и документация, а не сертификат и не замена аудиту.

## Лицензия

MIT — см. [LICENSE](LICENSE). Сторонние стандарты сохраняют свои лицензии;
см. [`references/standards/SOURCES.md`](references/standards/SOURCES.md).
