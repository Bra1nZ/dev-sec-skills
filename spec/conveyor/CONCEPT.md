# Конвейер верификации кода

> **Статус документа:** живой концепт. Большинство утверждений ниже — design
> intent и имеют статус `open`. Русская версия — источник истины;
> [`CONCEPT.en.md`](CONCEPT.en.md) — производный перевод.
>
> **Как читать.** Сначала раздел 0: реестр утверждений. Статус — по лестнице
> `evidence-first-docs`: `proven`, `model-checked`, `tested`,
> `static-refinement`, `reviewed`, `open`. `reviewed` означает «проверено
> чтением артефакта в этом репозитории»; `tested` — есть исполняемая проверка;
> `open` — намерение без evidence. Статус нельзя повысить без новой evidence:
> это правило проверяет `tools/status_diff.py`.

## 0. Реестр утверждений

| ID | Утверждение | Механизм | Evidence | Scope | Статус | Ограничения |
| --- | --- | --- | --- | --- | --- | --- |
| C-01 | Три скила задают единый контракт «claim → механизм → evidence → scope → status» | `SKILL.md` в трёх каталогах | `skills/*/SKILL.md`; `README.md` | Любой язык и агент | reviewed | Проверено чтением; автоматической проверки согласованности скилов нет |
| C-02 | `claim_lint.py` реализует проверки L1–L6 над реестром claim'ов | Схема + линтер + fallback-сканер прозы | `tools/claim_lint.py`; `schemas/claim-ledger.schema.json`; `evals/iteration-3/RESULTS.md`; команда `python3 evals/linter/run_evals.py` | JSON/YAML ledger; `.md`-проза | tested | L5-fallback имеет известный разрыв точности; проверка коммита fail-closed вне git-репозитория |
| C-03 | `status_diff.py` не даёт повысить статус без новой evidence | Сравнение ledger'ов, identity evidence по (kind, commit, artifact, command, tests, date) | `tools/status_diff.py` | Два файла или git-ref | reviewed | Нет адверсариального eval-набора; правило identity — design decision |
| C-04 | Скилы меняют ответ агента в нужную сторону | Пары `with_skill` / `without_skill` | `evals/iteration-1/RESULTS.md`; `evals/iteration-2/RESULTS.md`; `evals/README.md` | Девять синтетических задач | reviewed | Оценка качественная, по inspection; scored harness нет; размер выборки мал |
| C-05 | Линтер ловит подделанную трассировку, а runner не проходит вакуумно | Кейс `fake-test-id` + негативный контроль runner'а | `evals/linter/cases/fake-test-id.yaml`; `evals/iteration-3/RESULTS.md` | Синтетические fixtures | tested | 53/53 кейсов — контракт линтера, не чистота production-ledger'а |
| C-06 | Продукт продаёт пропускную способность верификации, а не тесты | Слои + маршрутизация + таблица покрытия | Нет | — | open | Нет ни одного измерения throughput, FP rate и задержки; следующий шаг — инструментировать baseline на пилоте |
| C-07 | L0: AST-дифф маршрутизирует PR в затронутые security-ячейки за секунды | Экстрактор AST + индекс «код → ячейка» | Нет | SQL/C на первом шаге | open | Экстрактор и индекс не построены; ложный negative в маршрутизации — риск; нужен замер precision/recall на пилоте rbac_pg против человеческой разметки |
| C-08 | L1: engine-agnostic ансамбль через SARIF-адаптеры покрывает ячейки за минуты | Адаптеры SVACE/PVS/Semgrep/CodeQL и др. | `spec/static-analysis/two-engine-2026-11-07.md`; Bandit 1.9.4 + Semgrep OSS 1.184.0 по `rbac_pg/setup` `d978609`; 249 находок, 2 движка в одном отчёте, 0 unmapped, 0 fixture, 0 cell_mapped, 10.018 с; триаж 2026-11-08: 249 `not-a-bug`, 0 cell | Два-три движка на первом шаге | open | Два движка (Bandit, Semgrep), SVACE/PVS не проверены; 249 находок триажены 2026-11-08 и все `not-a-bug`, ни одна не маршрутизирована, поэтому `covered`/`new` здесь не доказаны — реальный `new` есть только у само-пилота (C-40), `covered` — у cross-pilot маршрута craft-i18n; ни одна находка не получила cell: движковый `failure_class` (`invalid-or-injected-input`) не совпадает с `failure_class` инвариантных ячеек (`code-injection`, `input-validation`), поэтому маппинг только классовый; B602 не дал находок; Semgrep-правило — одно авторское текстовое MIT-правило, не benchmark; Bandit возвращает 1 при находках (в записи 2026-11-08 добавлен `--exit-zero`, поэтому exit 0); «SARIF» — формат, не evidence; два SARIF и отчёт замера 2026-11-07 не якорятся — якорятся per-engine записи 2026-11-08 (C-40/C-41) |
| C-09 | L2: регенерация среза формальной модели из неаннотированного кода работает как merge-gate | Ограниченная грамматика гвардов + bounded mc / VC + гейт полноты | Нет; границы языка — `guard-grammar.md` | Только ячейки, выразимые грамматикой | open | Экстрактор — TCB; риск vacuous-модели; грамматика покрывает authorization-срез, не конкурентность и не транзакции; разрыв модель↔код остаётся |
| C-10 | Само-мутация конвейера — условие его релиза | Внедрённые дефектные и чистые PR + внешний судья | Нет | Релизы конвейера | open | Судья не определён; held-out сюита не развёрнута; без внешнего судьи проверка циклическая |
| C-11 | Таксономия ограничена сотнями ячеек, уроки живут fixtures | Матрица «класс отказа × точка входа × режим отказа» | `spec/conveyor/cell-registry.schema.json`; `spec/conveyor/cells.seed.yaml`; `spec/pilots/rbac_pg/`; `spec/pilots/craft-i18n/` | Четыре таксономии | open | «~200» — design estimate; пилот на rbac_pg дал 29 ячеек на одно расширение (25 security, 2 correctness, 1 performance, 1 maintainability), из них 3 open; второй пилот на Rust-крейте дал 14 ячеек (2 security, 11 correctness, 1 maintainability) без новых классов; доля unroutable структурно 0 при текущей схеме и потому не измерена |
| C-12 | Время ревью среднего PR падает с ~45 до ~15 минут | Маршрутизация + растворение проверки в конвейере | Нет | — | open | Нет baseline-измерений; зависит от языка, домена и зрелости тестов; нужно распределение, а не точечная оценка |
| C-13 | Реестр вердиктов — hash-chain с внешним якорем | Хэш (commit + экстрактор + версии верификаторов + модель + результат), append-only | C-41: SSH-подпись над каноническими байтами записи; якорятся три evidence-канала — static-analysis (`dev-sec-skills-static-analysis`), run_record (`dev-sec-skills-run-record`) и sanitizer (`dev-sec-skills-sanitizer`), у каждого свой namespace; `tools/anchor_subject.py`; `tools/anchor_run.py --channel`; `spec/anchor/allowed_signers`. V2-39: append-only журнал вердиктов `spec/journal/verdicts.jsonl` (одна canonical JSON-строка на вердикт, `seq/date/ledger/claim/status/evidence/prev/hash`) и подписанная голова `spec/journal/head.json{,.sig}` (namespace `dev-sec-skills-verdict-journal`, хэш файла + точные байты каждого леджера); `tools/verdict_journal.py verify|append` (J1 цепь, J2 согласие с леджерами, J3 prefix против git-ref, J4 canonical head + подпись); `make journal` | Все вердикты | open | Журнал закрывает прошлое вердиктов: правка/удаление/усечение записи, смена статуса или evidence без append, подмена головы и чужой signer ловятся J1–J4, append отказывается продолжать битую цепь или голову. Покрыты только два in-repo леджера (12 вердиктов: 11 backfill 2026-11-08 + C-42, дата = день журналирования): внешний `../rbac_pg/docs/claims.yaml` намеренно вне журнала; proof- и review-записи не якорятся, поэтому правка внутри них не меняет identity evidence; key holder, замена `allowed_signers` и пере-подпись вместе с правкой истории git обходят всё (red-team drill `rewrite-journal-and-resign` записан как allowed); нет transparency log, timestamping и отзыва ключа. Реализованы три канала evidence (C-41): offline ed25519-подпись, ключ вне репозитория |
| C-14 | Кирпичи agent-guard и Цитадели переносятся на цепочку поставок кода | broker/default-deny, taint, одноразовые гранты, hash-chain audit | Нет указателей в этом репозитории | Внешние репозитории | open | Этот документ их не подтверждает; нужен указатель «репозиторий + путь/коммит» на каждый кирпич |
| C-15 | Никто не владеет связкой «provenance-taint + регенерация модели + само-мутация + throughput как продукт» | — | Предварительный обзор категорий, не систематический | Рынок и литература | open | Prior-art sweep не завершён; до внешней публикации утверждение нельзя выносить наружу |
| C-16 | Классификация low/medium/high в маршрутизации сама является поверхностью атаки | Правила под integrity-контролем + masquerade-тесты + аудит misroutes | Нет | Роутер | open | Правила и квоты не определены; без них «тесты и доки → auto-merge» обходится маскировкой |
| C-17 | `cell_lint.py` реализует проверки CL1–CL6 над реестром ячеек | Структура, покрытие, evidence, трассировка, таксономия, гейт эскалации + адверсариальный runner | `tools/cell_lint.py`; `evals/cell-lint/`; `evals/iteration-4/RESULTS.md`; команда `python3 evals/cell-lint/run_evals.py` | JSON/YAML реестр; опционально claim-леджер и базовый реестр | tested | 30/30 синтетических кейсов; production-реестра нет; identity evidence в CL6 — design decision; структурные проверки написаны вручную и могут разойтись со схемой |
| C-18 | Реестр ячеек разворачивается на реальном репозитории rbac_pg | 29 ячеек; каждая non-open ячейка ссылается на существующий suite или claim-леджер, open-ячейки — на записанные пробелы; артефакты резолвятся; CL1/CL3/CL4 без ошибок | `spec/pilots/rbac_pg/cells.yaml`; `spec/pilots/rbac_pg/README.md`; `spec/pilots/rbac_pg/mutations/`; команда `python3 tools/cell_lint.py --root /home/admini/projects/rbac_pg --ledger /home/admini/projects/rbac_pg/docs/claims.yaml spec/pilots/rbac_pg/cells.yaml` | Один репозиторий rbac_pg, HEAD `492f23c` | tested | Соответствие «ячейка ↔ смысл теста» проверено ревью, не машиной; 10 suite'ов перезапущены на свежем стенде 2026-11-06 (57/22/45/54/20/25/17/20/9 OK и 5 OK/2 GAP); 24/27 детекторов с mutation fixture и 3 с документированным `mutation_exemption`; 22/29 ячеек без claim; lint доказывает внутреннюю согласованность, не истинность свойств |
| C-19 | Реестр ячеек разворачивается на не-RBAC и не-БД репозитории craft-i18n | 14 ячеек; каждая non-open ячейка ссылается на существующий тест, open — на записанный пробел; артефакты резолвятся; CL1–CL5 без ошибок; 12/13 детекторов с mutation fixture, 1 exemption | `spec/pilots/craft-i18n/cells.yaml`; `spec/pilots/craft-i18n/claims.yaml`; `spec/pilots/craft-i18n/mutations/`; команда `python3 tools/cell_lint.py --root /home/admini/projects/astraoffice/craft-i18n --ledger /home/admini/projects/dev-sec-skills/spec/pilots/craft-i18n/claims.yaml spec/pilots/craft-i18n/cells.yaml` | Один Rust-крейт, commit `5c5c554` | tested | Леджер и реестр написаны в dev-sec-skills, а не в целевом репозитории; 14/14 привязка к claim'ам — by construction, не покрытие; охвачены правила чекера, не рендеринг приложений; 12/13 фикстур, 1 exemption |
| C-20 | Линтер обнаруживает пере-датировку и ссылку на неисполненный тест, когда evidence несёт run_record | L2 пересчитывает sha256 лога и артефакта, сверяет `finished_at` с датой evidence, exit code и счётчики с summary, требует каждый процитированный ID в логе | `evals/linter/cases/run-record-*.yaml`; `spec/pilots/craft-i18n/runs/`; `tools/claim_lint.py` | Синтетические cargo/pytest-фикстуры и один реальный прогон `craft-i18n` | tested | Без внешнего anchor (C-13) подделка record+log не обнаруживается; леджер `rbac_pg` без run_record даёт warning, а не проверку |
| C-21 | Линтер отвергает «посторонний коммит»: коммит резолвится, но не описывает текущие байты артефакта | L2 сравнивает артефакт с его блобом на процитированном коммите (`git cat-file -e <commit>:<path>`, `git diff --quiet <commit> -- <path>`); коммит, которого артефакт не было, и файл, изменённый после коммита, — ошибка | `evals/linter/cases/unrelated-commit.yaml`; `tools/claim_lint.py`; прогон на `craft-i18n` | Git-дерево пилота и синтетический git-backed кейс | tested | Вне git-дерева проверка пропускается (иначе синтетика без `.git` падала бы за отсутствие репозитория); «пустая модель» закрыта кейсом `empty-claims`, но леджер без claim’ов теперь просто ошибка L1, а не отдельная модель
| C-22 | Удаление claim’а или ячейки невозможно без надгробия с причиной | `retired: [{id, reason, date}]` в леджере/реестре; `status_diff` и CL6 падают, если base-ID исчез без надгробия, если надгробие называет живой ID и если более раннее надгробие удалено; L1/CL1 проверяют форму без base | `evals/linter/cases/retired-*.yaml`; `evals/cell-lint/cases/removed-without-retired.yaml`, `removed-with-retired.yaml`, `tombstone-dropped.yaml`, `retired-without-reason.yaml`; `evals/status-diff/run_evals.py`; `tools/status_diff.py`, `tools/cell_lint.py` | Синтетические леджеры и git-репозитории | tested | Форма проверяется без base, а факт удаления — только в диффе; дата надгробия опциональна, порядок надгробий не проверяется; retired-записи не входят в U и в подсчёт покрытия
| C-23 | Статус `model-checked` или `proven` требует вывода инструмента, а не существования артефакта | `evidence.tool_output` (`schemas/tool-output.schema.json`): `tool`, `command`, `output` + `output_sha256`, `exit_code`, `finished_at`, обязательный `status`; L1 проверяет форму и согласованность commit/command, L2 — хэш вывода, дату `finished_at`, `exit_code=0` и `status=completed` для не-open (V2-28), L4 — отсутствие `tool_output` для `model-checked`/`proven` и отсутствие `bound` для `model-checked` | `evals/linter/cases/tool-output-*.yaml`, `model-checked-without-tool-output.yaml`, `model-checked-without-bound.yaml`; `schemas/tool-output.schema.json`; `tools/claim_lint.py` | Синтетические леджеры с TLC-подобным выводом | tested | Семантика инструмента и корректность кодировки модели не проверяются; без внешнего anchor (C-13) согласованная подделка проходит; запись обязательна только для `model-checked`/`proven`, для остальных статусов поле не запрещено; `status` классифицирует супервизор, а не инструмент |
| C-24 | Детектор `runtime-enforcement` не принимается без негативного теста и объявленной точки принуждения | `kind: runtime-enforcement` требует `negative_test` (ID, резолвится через `--suite-glob`), а ячейка — `enforced_at`, `oracle`, `violation_response`; CL1 проверяет форму, CL3 резолвит ID, CL2 не даёт заявить статус выше `tested` | `spec/conveyor/cell-registry.schema.json`; `tools/cell_lint.py`; `evals/cell-lint/cases/runtime-enforcement-*.yaml`, `negative-test-*.yaml`; `spec/pilots/rbac_pg/cells.yaml` CELL-001; `spec/pilots/craft-i18n/cells.yaml` CELL-003 | Синтетические реестры и две реальные ячейки с записанными прогонами | tested | Разрешение ID проверяется только при переданном `--suite-glob` (иначе info); смысл `violation_response` автоматически не верифицируется; mutation fixture остаётся отдельным требованием CL2 |
| C-25 | Фаззинг-прогон воспроизводим и ограничен явным oracle и бюджетом | `tools/fuzz_run.py`: seed-корпус читается в отсортированном порядке, мутатор `random.Random(seed)`, `executions_digest` = SHA-256 от упорядоченных хэшей входов; oracle-правила `exit:N`, `exit-not-in:`, `stdout-contains:`, `stderr-contains:`, `timeout` объединяются по ИЛИ; запись по `schemas/fuzz-run.schema.json` хранит манифест корпуса, бюджет, seed и каждую находку с логом | `spec/fuzz/runs/claim-lint-2026-11-07.json`; `evals/fuzz/`; `make fuzz-claim-lint` | `claim_lint` как цель, 5 seed-леджеров, 150 мутаций, seed 20261107 | tested | Мутатор случайный, без coverage guidance; `clean` означает «oracle не сработал в этом бюджете», а не отсутствие багов; digest связывает входы, не поведение цели; replay не входит в `make verify` (≈1 минута) и запускается вручную |
| C-26 | Находка фаззера не исчезает: она становится cell + detector + fixture или отклоняется с причиной, и это проверяется гейтом | `tools/fuzz_triage.py`: T1 — форма записи триажа, T2 — ровно одна запись на находку (untriaged, duplicate и stale — ошибки), T3 — cell и detector резолвятся в реестре, названном в triage-файле, fixture ID — в mutations-файле, T4 — verdict записи согласован с `findings`; пустой триаж допустим только для чистого прогона | `schemas/fuzz-triage.schema.json`; `spec/fuzz/triage/claim-lint-2026-11-07.yaml`; `evals/fuzz-triage/`; `make check-fuzz-triage` | Синтетические записи; записанный прогон `claim_lint` без находок | tested | На реальной находке гейт ещё не прогонялся; выбор `covered` против `new` — суждение ревью, гейт проверяет только существование артефактов; инъекция находки в копию записи в `/tmp` даёт exit 1, сам артефакт репозитория не менялся |
| C-27 | Покрытие реестра измеряется, а не предполагается: висячие ссылки, несвязанные символы, stale claims и детекторы без fixture видны | `tools/coverage_report.py`: CV1 — процитированный claim'ом или детектором символ обязан существовать в suite (всегда error); CV2 — символы suite'а, не отображённые на артефакт, claim или `negative_test` (info, error только выше `--max-unmapped`); CV3 — non-open claim с датой старше `--max-age-days` (по умолчанию 90) или без даты; CV4 — non-open детектор `test`/`runtime-enforcement` без `mutation_fixture` и без `mutation_exemption`; маппинг файловый, извлечение — узкие паттерны `report("F3a")`, `def test_*`, `#[test] fn` | `tools/coverage_report.py`; `evals/coverage/`; `spec/coverage/README.md`; `make coverage` | `rbac_pg`: 80 символов, 67 mapped, 13 unmapped в двух файлах; `craft-i18n`: 26/26 mapped; 0 stale, 0 без fixture | tested | Файловый маппинг не доказывает, что детектор исполняет каждый тест в отображённом файле; сканер не AST; CV2–CV4 без порогов остаются отчётом, а не гейтом; stale считается по дате без внешнего anchor |
| C-28 | Изменённый choke point не исчезает из ревью: объявленный в `enforced_at` путь или символ обязан отображаться на non-open claim, иначе гейт падает | `tools/diff_coverage.py`: DC1 — изменённый объявленный путь без non-open claim, DC2 — изменённый объявленный символ без non-open claim, DC3 — `enforced_at` не локализуется в репозитории (нет ведущего `path:line`, путь отсутствует как blob на base и head, путь вне root) и это всегда error, DC4 — в диапазоне нет изменённых объявлений, DC5 — реестр не объявляет `enforced_at`; маппинг — cell `claim_ids` → non-open claim, либо `artifact` claim'а == путь, либо `tests`/`negative_test` == символ; `open` claim покрытием не считается; символы локализует `tools/choke_points.py`: Python `ast` (спан включает декораторы), Rust и SQL — структурные лексеры комментариев/строк, SQL-спан покрывает всё `CREATE ... FUNCTION ...;` вместе с dollar-quoted телом; token-fallback только если парсер не нашёл определение, по маскированным строкам | `tools/diff_coverage.py`; `tools/choke_points.py`; `evals/diff-coverage/`; `spec/diff-coverage/README.md`; `ci/diff-coverage.yml`; `make diff-coverage` | `rbac_pg` `v1.3.1..HEAD`: 110 файлов, 2/2 mapped; `craft-i18n` `f0dd77b^..f0dd77b`: 2/2 mapped; `--max-unmapped 0` | tested | Только ячейки с `enforced_at`: 100 % — это два объявления из 43 ячеек, реестр без объявлений получает DC5, а не покрытие; Rust-макросы/сгенерированный код и SQL `BEGIN ATOMIC`/quoted identifiers могут исказить спан; unknown-расширения по-прежнему дают false positives на комментариях; маппинг не проверяет свежесть claim'а; шаблон CI не прогонялся на реальном PR; порог агрегатный по путям и символам |
| C-29 | Обычный код даёт структурных кандидатов choke points, и каждый кандидат либо маппится на класс ячейки, либо явно `unclassified` | `tools/choke_points.py`: Python — `ast` (декораторы входят в спан); Rust и SQL — маскирующие лексеры комментариев, строк, raw/byte-строк, char-литералов и dollar-quote, затем `fn`/скобки и split по top-level `;`; SQL-спан — весь statement, поэтому правка тела видна. `spec/choke-points/rules.yaml`: `signals` решают, что считать кандидатом, `rules` упорядочены (первый матч выигрывает) и валидируются по enum'ам `cell-registry.schema.json`; `other` в правиле запрещён; кандидат без правила — `unclassified`, а не cell. CP1/CP2 — необязательные пороги unclassified и parse errors | `tools/choke_points.py`; `spec/choke-points/rules.yaml`; `spec/choke-points/README.md`; `evals/choke-points/`; `make choke-points` | `rbac_pg` 2026-11-07: 75 файлов, 1585 определений, 1413 кандидатов, 867 classified / 546 unclassified (38,6 %); `craft-i18n`: 9 файлов, 128 определений, 64 кандидата, 47 / 17 (26,6 %); оба — 914/1477 = 61,9 % classified | tested | Signals/rules — регулярные выражения по имени, вызовам, декораторам, пути и kind, без семантики и data flow; Rust/SQL — лексеры, не парсеры, макросы/сгенерированный код и `BEGIN ATOMIC`/quoted identifiers вне грамматики; `guard-call` путает sink (`read`, `write`, `execute`) с guard, отсюда измеренные 38 % unclassified; порог не включён в `make verify`; совпадение класса — гипотеза, не доказательство и не cell |

| C-30 | Изменённый участок кода запускает только свои mutation fixtures, а изменённая ячейка без fixture и exemption не проходит план | `tools/mutation_plan.py`: diff `base..head` через `git diff --name-status -M`; ячейка выбирается по `enforced_at` (путь из sentence), detector `artifact`, fixture `artifact` или изменению записи реестра (`--cells-base`); fixture выбирается по своей ячейке или artifact; `--require-fixtures` возвращает 1 для изменённой non-open ячейки без fixture и без `mutation_exemption`; runner'ы принимают `--plan` и `--only-cell`, пустой план — exit 0 без запуска стенда; `ci/mutation-changed.yml` резолвит merge base и пропускает job при нулевом плане | `tools/mutation_plan.py`; `evals/mutation-plan/`; `ci/mutation-changed.yml`; `Makefile` (`make mutation-plan`); оба `run_mutations.py` | 13/13 eval-кейсов; `rbac_pg` `v1.3.1..HEAD`: 110 файлов, 26 ячеек, 25/25 fixtures; `craft-i18n` `f0dd77b^..f0dd77b`: 3 файла, 6 ячеек, 7/12 fixtures; 0 uncovered | tested | Маппинг файловый: правка файла выбирает все ячейки, которые его называют, даже если изменённая строка не относится к инварианту; путь из `enforced_at` извлекается регулярным выражением, а не парсером; новый fixture без изменения artifact/ячейки не выбирается, пока не изменён `mutations.yaml` (полный прогон — `--all`); шаблон CI не прогонялся на реальном PR; `--require-fixtures` не доказывает, что фикстура чувствительна к конкретной правке |

| C-31 | Каталог инвариантов вне БД и ролей полон по пяти категориям и не оставляет seed-ячейку без ссылки или явного out_of_scope | `tools/invariant_catalog.py`: INV1 — ровно пять категорий, ≥2 инварианта в каждой; INV2 — обязательные поля, уникальные ID с префиксом категории, enum'ы из `cell-registry.schema.json`, запрет `other`, ≥2 bypasses; INV3 — категория, seed-ячейка, choke-point rule и out_of_scope-ячейка существуют, пересечение referenced/out_of_scope запрещено; INV4 — не-open инвариант обязан назвать существующий `evidence_path`; INV5 — каждая seed-ячейка referenced или out_of_scope, неиспользованные rules печатаются как info | `spec/invariants/catalog.yaml`; `spec/invariants/README.md`; `schemas/invariant-catalog.schema.json`; `tools/invariant_catalog.py`; `evals/invariant-catalog/`; `make invariants` | 15 eval-кейсов; 15 инвариантов, 5 категорий; 9/12 seed-ячеек referenced + 3 out_of_scope; 9/11 rules used; 0 errors | tested | Проверяется внутренняя согласованность и резолвинг ссылок, не истинность инварианта; `failure_class` — свободная строка, опечатка не ловится; все 15 инвариантов `open`, ни один negative test не исполнялся; seed-ячейки CELL-001/002 (БД-роли) и CELL-011 (supply chain) исключены по границе; `migration` и `sql-rls` не покрыты намеренно; выбор двух bypasses — минимум, не модель угроз |

| C-32 | Вывод SARIF-движка становится evidence через адаптер: неизвестный engine или rule виден как `unmapped`, а authored fixture не выдаётся за прогон движка | `tools/sarif_evidence.py`: engine резолвится по `tool.driver.name` (или id, регистронезависимо); rules упорядочены, первый regex-match по rule ID выигрывает; `taxonomy_class` и `failure_mode` проверяются по `cell-registry.schema.json` до чтения любого входа, `other` запрещён; `cell` опционален в форме `<registry>/<CELL-ID>`, обязан резолвиться и требует равенства `failure_class` правила и ячейки (ячейка без `failure_class` не называема), иначе exit 2; findings дедуплицируются по `(engine, partialFingerprints)` либо по `(rule, path, start, end, message)`, сортируются детерминированно и получают `F-NNN`; digest — sha256 упорядоченных нормализованных findings; причины `unmapped` — `unknown-engine`, `unmapped-rule`, `missing-rule-id`, `missing-location`; гейты `--max-unmapped`, `--require-engines`; provenance `properties.dev-sec-skills/fixture` и `--reject-fixtures`; exit 0/1/2 | `tools/sarif_evidence.py`; `spec/sarif/adapters.yaml`; `spec/sarif/fixtures/`; `spec/sarif/README.md`; `spec/sarif/2026-11-07-report.json`; `schemas/sarif-evidence.schema.json`; `evals/sarif/`; `Makefile` (`make sarif`, `make sarif-record`) | 20/20 eval-кейсов; 3 движка, 7 findings, 0 unmapped, 1 duplicate, 0 findings с cell (все 7 — только класс); digest `caf2a4f9fe24ba42`; входы — authored fixtures, `fixture_inputs: 3` | tested | Fixtures написаны вручную: реального прогона Semgrep/CodeQL/Bandit нет, доля маппинга на реальном выводе неизвестна; rule ID меняются между версиями движка; mapped finding не доказывает true positive и не доказывает, что участок не защищён; ни одно правило адаптера сейчас не называет cell, поэтому cell-путь проверен только синтетическими eval-кейсами; первый regex-match перекрывает последующие правила; дедупликация по `partialFingerprints` или точному кортежу может слить разные findings; `uriBaseId` (`%SRCROOT%`) не резолвится, путь только ребейзится от `--root`; SARIF-схема не валидируется; `make sarif` не входит в `make verify` |
| C-33 | Bounded-прогон внешнего инструмента записывает, как он закончился: таймаут даёт `unverified` и не поддерживает non-open claim | `tools/bounded_check.py`: `Popen(start_new_session=True)`, `killpg(SIGKILL)` по wall-clock bound, combined stdout/stderr без вставок супервизора, `status` из четырёх значений, exit 0/1/2/3; `schemas/tool-output.schema.json` требует `status` и описывает `timed_out`, `bound_seconds`, `elapsed_seconds`; L1 отвергает `timed_out`, противоречащий статусу, L2 — `status != completed` и `timed_out` для не-open claim | `tools/bounded_check.py`; `schemas/tool-output.schema.json`; `tools/claim_lint.py`; `evals/bounded-check/`; `evals/linter/cases/tool-output-{unverified-zero-exit,timed-out,status-contradiction,missing-status,open-unverified}.yaml`; `spec/conveyor/guard-grammar.md` §6.6 | Синтетические дочерние процессы (`python -c`) и синтетические леджеры; реальный движок не запускался | tested | Проверяется классификация собственного дочернего процесса, не корректность реального checker'а; child может родить процесс вне группы (double-fork/setsid) и пережить kill; bound не адаптивный; non-zero как вердикт требует адаптера; `verdict` не синтезируется супервизором; распределённые checker'ы и чекпоинты не покрыты |
| C-34 | `proven`-доказательство перепрогоняется по изменению своего объекта, а не каждый PR | Манифест зависимостей и планировщик по git-диапазону: `artifact`, `depends_on`, `model`, `encoding`, `tooling` сопоставляются с diff (rename — через old path); `manifest-changed`/`proof-added` сравнивают манифест с базовым; `record-not-completed` срабатывает на любой `status != completed`; свежесть — `finished_at` ≥ committer time последнего изменения объявленного пути; гейты `--require-fresh` и `--require-complete`, exit 2 на битый ввод | `tools/proof_plan.py`; `schemas/proof-manifest.schema.json`; `spec/proofs/`; `evals/proof-plan/` 36/36; `python3 evals/proof-plan/mutation_selftest.py` 8/8; demo-манифест на реальном диапазоне `a50fbda..HEAD` | git-диапазон `base..head`; JSON-запись с `status` и `finished_at`; пути внутри `--repo` или абсолютные | tested | Проверено на синтетических git-репозиториях и одном demo-манифесте; реального `proven` claim'а нет, ни одно настоящее доказательство не перепрогонялось; манифест задаёт scope, поэтому необъявленный общий helper невидим; свежесть — сравнение времени, а не проверка, с какого checkout'а снята запись; хэш записи проверяет `claim_lint`, семантику checker'а не проверяет никто; `--require-complete` видит только proof-расширения |
| C-35 | Атаки на реальные артефакты пилота блокируются гейтами, кроме одного записанного слепого пути (замена signer'а) | 20 drills: копия реального леджера, записанного лога и реестра, одна мутация на drill, реальный инструмент, сверка exit code и ожидаемого сообщения; `allowed`-drill падает, если гейт начнёт блокировать | `spec/red-team/run_drills.py`; `spec/red-team/2026-11-08-drills.json`; `make red-team` | Леджер craft-i18n (9 claims), его записанный cargo-лог и реестр ячеек; `claim_lint --no-vale`, `status_diff`, `cell_lint`, `proof_plan` | tested | Один пилот; L5 не упражняется; правки статические, скомпрометированные инструменты и CI вне scope; блокировка доказывает срабатывание конкретной проверки, а не отсутствие других обходов; остаются две записанные дыры — пере-датировка evidence с заменой `allowed_signers` и пере-подписью и пере-запись журнала с заменой `allowed_signers`, правкой истории git и пере-подписью головы (C-13), тогда как чистая пере-датировка блокируется якорем run_record, а удаление записи журнала — J3; заимствование evidence закрыто L6 (C-36); сокрытие finding-строки закрыто L2 (C-37), сокрытие static-finding — L2 (C-40), подделка подписанной записи — якорем (C-41), в том числе правка подписанного run_record — L2; журнал проверяется J1–J4, но drills идут на копии леджера craft-i18n, а не на живом журнале репозитория |
| C-36 | Тест, процитированный двумя claim'ами, объявлен shared с причиной, а non-open claim имеет хотя бы один собственный тест | L6 в `claim_lint`: карта test ID → claim'ы; правило 1 требует `evidence[].shared_tests: [{id, reason}]` у каждого цитирующего claim'а; правило 2 отвергает non-open claim, все тесты которого цитирует кто-то ещё, даже при объявленном sharing; L1 проверяет форму (id из `tests`, непустая причина, только `kind=test`), схема `claim-ledger.schema.json` описывает поле | `tools/claim_lint.py`; `schemas/claim-ledger.schema.json`; `evals/linter/cases/shared-*.yaml` (6 кейсов); `spec/pilots/craft-i18n/claims.yaml`; `spec/red-team/run_drills.py`; `make verify` | Леджеры craft-i18n (9 claims, 21 test ID, 1 общий тест) и rbac_pg (7 claims, 22 test ID, общих нет); синтетические кейсы; два red-team drill'а на реальном леджере | tested | Не проверяет, что утверждения теста соответствуют формулировке claim: правило 2 отсекает только полностью заимствованный набор, одна собственная, но нерелевантная цитата проходит; `open` освобождён от правила 2; связь ищется по точной строке test ID, поэтому переименование или перенос теста создаёт новую evidence-identity и требует ручного пересмотра |
| C-37 | Динамический санитайзер принимается как evidence-канал только вместе с выводом и способом завершения прогона | `schemas/sanitizer-run.schema.json`: `tool` (asan/ubsan/tsan/msan/lsan), `build_flags`, `command`, `output` + `output_sha256`, `exit_code`, `started_at`, `finished_at`, `status`, опционально `version`; `evidence[].sanitizer_runs` допускается только на `kind=test`; L1 проверяет форму, enum'ы инструмента и статуса, sha256 и ISO-даты; L2 сверяет хэш вывода, требует `finished_at` на дату evidence, `exit_code=0` и `status=completed` для non-open claim, а также отвергает запись «clean» (`completed` + exit 0), в выводе которой есть finding-строка (`ERROR`/`WARNING: …Sanitizer:`, `SUMMARY: …Sanitizer:`); recoverable UBSan `runtime error:` намеренно не считается найденной строкой | `schemas/sanitizer-run.schema.json`; `schemas/claim-ledger.schema.json`; `tools/claim_lint.py`; `evals/linter/cases/sanitizer-*.yaml` (7 кейсов); `spec/pilots/craft-i18n/claims.yaml` C-02; `spec/pilots/craft-i18n/runs/asan-test-2026-11-07.log`; `spec/pilots/craft-i18n/runs/asan-instrumentation-2026-11-07.md`; `spec/red-team/run_drills.py` (`sanitizer-findings-hidden`); `make verify` | craft-i18n, commit `5c5c55400e8f7f4ee4f64a64dc196335a6a1f256`, nightly `1.101.0-nightly`, `-Zsanitizer=address`, `--target` отделяет host-артефакты; 26/26 тестов, exit 0, 0 finding-строк; probe нашёл `__asan_init` и `__asan_report_load*/store*` в исполняемом бинаре | tested | Санитайзер может опровергнуть claim, но не доказать отсутствие дефекта: чистый прогон означает «в этом корпусе и этой инструментации не сработало»; std не инструментирован; L2 доверяет полю `build_flags` и не доказывает инструментацию (это делает только отдельный probe); recoverable UBSan намеренно не ловится; корпус не доказывает, что тесты исполняют именно claim; согласованная подделка записи и вывода и пере-датировка остаются (C-13) |
| C-38 | Независимая модель row-грамматики согласуется с `read_catalog` на объявленном ограниченном пространстве | `crosscheck/c02-row-model`: модель написана по `docs/catalog-format.md`, а не переведена из `catalog.rs`; генератор перечисляет 10×30×25 одиночных строк, арности 0–4, все пары из 19 rule-shaped строк и все тройки из 11, 7×7×3 plural-случаев и пять обёрток BOM/CRLF; сравнение — принятые строки `(line, context, source, translation)` и номера отвергнутых строк, не текст ошибки; бинарь падает при превышении 100 000 входов или 256 байт на вход | `crosscheck/c02-row-model/src/model.rs`; `crosscheck/c02-row-model/src/main.rs`; `spec/proofs/c02-bound-2026-11-07.md`; `spec/proofs/runs/c02-crosscheck-2026-11-07.json`; `spec/pilots/craft-i18n/claims.yaml` C-02; `make crosscheck-c02` | craft-i18n, commit `5c5c55400e8f7f4ee4f64a64dc196335a6a1f256`; 69 430 уникальных входов, 11 142 принятых строки, 63 364 входа с отвергнутой строкой, 0 расхождений; запись `completed`, exit 0 | tested | Согласие только внутри словаря: произвольный Unicode, длинные строки и каталоги больше трёх строк не исчерпаны; модель и реализация написаны одним автором, общее неверное прочтение формата невидимо; это differential check, не доказательство эквивалентности; `check_tree`, discovery и locale validation вне модели; `forms` ∈ {1,2,3}; дедупликация проверена на каталогах ≤3 строк; target пиннится `TARGET`, изменение target после пина ловит `claim_lint` L2, а не crosscheck |
| C-39 | Bounded-пространство чувствительно к каждому названному правилу модели: 22 мутанта ловятся | `--mutants` прогоняет всё пространство 22 раза, выключая по одному правилу (число колонок, пустые поля, duplicate key, escapes, reserved contexts, placeholders, `…`, template, plural, control chars, BOM, CR, `@id`, номера строк, комментарии); мутант без расхождения — exit 1 | `crosscheck/c02-row-model/src/model.rs` (`Ruleset`); `crosscheck/c02-row-model/src/main.rs`; `spec/proofs/c02-bound-2026-11-07.md`; `spec/proofs/runs/c02-mutants-2026-11-07.json`; `make crosscheck-c02-mutants` | Тот же пин и то же пространство 69 430 входов; 22/22 caught; запись `completed`, exit 0 | tested | Мутанты известны и написаны вручную; высокий счёт — чувствительность к этим правкам, не полнота; caught означает хотя бы одно расхождение, а не покрытие правила на всех входах; target-pin и авторские ограничения C-38 действуют |
| C-40 | Находка статического анализа не исчезает: запись прогона и triage связывают engine, правила, коммит, SARIF, отчёт и одно решение на находку | `schemas/static-analysis-run.schema.json`: `tool`, `command`, `rules{name,source,sha256}`, `target_commit`, `output` (SARIF) + `output_sha256`, `report` + `report_sha256`, `exit_code`, `started_at`, `finished_at`, `status`, опционально `cells`, `triage`, обязательный `anchor` (C-41); dispositions `covered`/`new` (обязательны cell, detector, fixture в форме `path#MUT-ID`), `not-a-bug`/`out-of-scope` (обязательна причина). L1 проверяет форму и словарь; L2 хэширует правила и оба выхода, требует `finished_at` на дату evidence, `exit_code=0` и `status=completed` для non-open claim, проверяет `report.format`, что `output_sha256` есть среди `report.inputs[].sha256`, что названный engine имеет `runs>0`, что `summary.unmapped` и `summary.fixture_inputs` равны 0, биекцию `report.findings[].id` ↔ `triage[].finding` и резолвинг cell/detector/fixture в реестре `cells`, а также пересчитывает канонические байты якоря и проверяет SSH-подпись против `allowed_signers` (C-41); L4 требует запись для `static-refinement` | `schemas/static-analysis-run.schema.json`; `schemas/claim-ledger.schema.json`; `tools/claim_lint.py`; `tools/sarif_evidence.py` (`aliases`, `--path-root`); `spec/sarif/adapters.yaml`; `spec/static-analysis/rules/ci-supply-chain-2026-11-07.yml`; `spec/static-analysis/rules/bandit-builtin-2026-11-08.yaml`; `spec/static-analysis/runs/`; `spec/static-analysis/README.md`; `spec/pilots/craft-i18n/claims.yaml` C-09; `spec/pilots/rbac_pg/analysis-claims.yaml` C-40; `spec/pilots/rbac_pg/triage_2026-11-08.py`; `spec/pilots/dev-sec-skills/` (C-01, CELL-001, D-PINNED-ACTIONS, MUT-001); `spec/anchor/` (C-41); `evals/linter/cases/static-analysis-*.yaml` (20 кейсов); `make verify` | Semgrep OSS 1.184.0, `5c5c554`, три авторских правила; 5 находок, 0 unmapped, 0 fixture, 0 дублей, exit 0, `completed`; правила `d05187db…`, SARIF `3e32c249…`, отчёт `6ed91da2…`; F-003/F-004 — `covered` через cross-pilot маршрут в реестр само-пилота (`spec/pilots/dev-sec-skills/cells.yaml`, CELL-001 / D-PINNED-ACTIONS / MUT-001), F-001/F-002/F-005 — `out-of-scope`, потому что таксономия пилота не владеет supply-chain классом; само-пилот по этому же каналу: пред-фикс прогон `d0c25c2` — 3 находки, все `new` → CELL-001, фикс `67d0aec`, пост-фикс прогон `67d0aec` — 0 находок; SARIF `2b09702b…` / `b8073caf…`, отчёты `f631739f…` / `6e6d746b…`; rbac_pg: два per-engine прогона 2026-11-08 (`d978609`) — Bandit 1.9.4, 63 находки, и Semgrep 1.184.0, 186 находок; SARIF `e59fa280…` / `a850a750…`, отчёты `8185cf35…` / `036733d7…`, digest `ad5199da…` / `5f1a53f6…`; все 249 записей `not-a-bug`, 0 cell; `spec/pilots/rbac_pg/analysis-claims.yaml`, якоря `rbac-pg-bandit-2026-11-08` / `rbac-pg-semgrep-2026-11-08` | tested | Один движок и один прогон; правила текстовые (`generic` + regex), без data flow, и не являются `p/ci` benchmark — другой набор правил даст другую очередь; `new` впервые пройден на реальном прогоне само-пилота (3 находки → CELL-001 → фикс `67d0aec`), `covered` впервые не синтетический: F-003/F-004 craft-i18n маршрутизированы в само-пилот, и D-PINNED-ACTIONS, запущенный read-only по каталогу workflow craft-i18n, падает на `ci.yml:17` и `sonarcloud.yml:20` при `5c5c554`; маршрут пересекает пилоты — детектор принадлежит само-пилоту и в CI craft-i18n не включён; `out-of-scope` — граница таксономии, а не вердикт о безвредности; правила Semgrep Registry не вендорятся из-за лицензии, поэтому URL-источник не хэшируется повторно; engine/правила могут меняться между версиями; первые два пилота остаются read-only, поэтому detector и fixture добавлены только в само-пилоте (`spec/pilots/dev-sec-skills/`); якорь C-41 ловит правку после подписи, но key holder, замена `allowed_signers` с пере-подписью и пере-датировка с новой подписью остаются (C-13); в rbac_pg ни одна из 249 находок не маршрутизирована, потому что реестр пилота не владеет классами `invalid-or-injected-input` и `exposed-secret-or-weak-crypto` — настоящая инъекция была бы `out-of-scope`, а `not-a-bug` говорит лишь о том, что в этом harness внешние данные не доходят до цитируемого оператора; причины триажа прочитаны по исходнику на `d978609` и не доказывают безопасность; ключ подписи 2026-11-07 потерян, записи 2026-11-08 подписаны новым ключом, что не доказывает дату записи (C-13) |
| C-41 | Каждая новая evidence-запись несёт внешний якорь своего канала: SSH-подпись над её каноническими байтами | `tools/anchor_subject.py` строит canonical JSON (sorted keys, compact separators, trailing newline) для трёх каналов: static-analysis — `tool`, `version`, `command`, `rules{name,source,sha256}`, `target_commit`, `output_sha256`, `report_sha256`, `exit_code`, `started_at`, `finished_at`, `status`, `cells` (реестр, против которого резолвится `covered`) и весь `triage` (finding, disposition, cell, detector, fixture, reason, date, note); run_record — `runner`, `command`, `commit`, `exit_code`, timestamps, `log_sha256`, `artifact_sha256`, `tests_run`, `tests_passed`; sanitizer — `tool`, `version`, `build_flags`, `command`, `exit_code`, timestamps, `output_sha256`, `status`; `tools/anchor_run.py keygen\|create\|verify --channel {static-analysis,run-record,sanitizer}` использует `ssh-keygen -Y sign/verify` (ed25519) с namespace канала; `anchor` обязателен в `static_analysis_runs[]`, `run_record` и `sanitizer_runs[]` (L1 проверяет поля, типы и namespace канала), L2 пересчитывает байты, хэширует subject/signature, проверяет subject == канонические байты записи и вызывает `ssh-keygen -Y verify` против закоммиченного `allowed_signers`; якорь проверяется до проверки output/log, поэтому URL в `output` не обходит проверку | `tools/anchor_subject.py`; `tools/anchor_run.py`; `schemas/static-analysis-run.schema.json`; `schemas/run-record.schema.json`; `schemas/sanitizer-run.schema.json`; `tools/claim_lint.py` (`check_anchor_shape`, `_check_anchor`); `spec/anchor/` (allowed_signers + 16 subject + 16 `.sig` + README о ротации ключа); `spec/pilots/dev-sec-skills/claims.yaml` C-01 static 0/1 + run_record 0, C-02 run_record 0; `spec/pilots/craft-i18n/claims.yaml` C-09 static 0, C-01…C-07 run_record (8) + C-02 sanitizer; `evals/linter/cases/static-analysis-anchor-{missing,tampered,bad-signature,unknown-signer}.yaml`, `evals/linter/cases/run-record-anchor-{missing,tampered}.yaml`, `evals/linter/cases/sanitizer-anchor-tampered.yaml`; `spec/red-team/run_drills.py` `forge-anchored-record`, `forge-anchored-test-record`; `make verify`; `make red-team` | 16 реальных якорей и 7 синтетических кейсов; `anchor verified` для всех 16 (5 static, 10 run_record, 1 sanitizer); правка `version`/`runner` после подписи — L2 error «anchor subject does not describe this record»; замена `.sig` — L2 error; отсутствие `anchor` — L1 error; чужая namespace — L1/L2 error; валидная подпись от signer'а вне `allowed_signers` — L2 error; два forge-drill blocked; `evals/linter` 77/77; `red-team` 18/18 (17 blocked, 1 allowed) | tested | Приватный ключ вне репозитория (`/tmp/opencode/dev-sec-skills-anchor-2026-11-08/key`; ключ 2026-11-07 потерян вместе с `/tmp/opencode`), поэтому запись нельзя подписать заново без него; но key holder может пере-подписать любую правку, а замена `allowed_signers` + новая подпись обходит всё; нет transparency log, timestamping и отзыва ключа; якорь покрывает хэши выходов, но не сами пути и не `rules.source`; proof- и review-записи не якорятся; без `ssh-keygen` non-open claim получает error, open — info; 10 из 16 записей (9 run_record + 1 sanitizer) подписаны задним числом 2026-11-08: подпись доказывает, что запись не менялась после подписи, а не что прогон действительно был в 2026-11-07; потеря ключа делает невозможной пере-подпись старых записей (остаются валидными), новые идут под новым signer'ом |


Правила реестра:

- Один claim — одна строка. Утверждение должно быть фальсифицируемым.
- `open` всегда несёт ограничения и следующий шаг. Пустой `open` — это риск,
  замаскированный под план.
- Утверждения о внешних кирпичах обязаны иметь указатель на артефакт
  (репозиторий + путь или коммит). Без указателя статус остаётся `open`.
- Повышение статуса требует новой evidence; повторный прогон с новой датой
  считается новой evidence только для freshness, не для силы доказательства.

## 1. Тезис

Генерация кода подешевела до нуля; узкое место разработки — ёмкость
верификации. Отдел из 10 000 джунов по PR в минуту не существует, а 10 000
агентов — уже да. Продукт продаёт не «тесты», а **пропускную способность
верификации**: верифицированных PR в единицу времени при ограниченном уровне
ложных срабатываний и ограниченной задержке.

«10 000 агентов — уже да» — тезис о предложении, не измерение. Числа
throughput, FP rate и задержки остаются `open` (C-06, C-12), пока не
инструментированы на пилоте.

## 2. Политика доверия

Origin-agnostic verification: артефакт недоверен независимо от происхождения.
Эквивалентность «джун = агент» верна как политика доверия (проверяй всё,
включая код сеньоров) и неполна как модель угроз:

- у агентного кода коррелированные ошибки — слепые пятна версии модели;
- инъецируемый генезис — код сформирован текстами, которых автор не писал;
- отсутствует петля обучения, которая у джуна есть;
- отсутствует субъект ответственности.

Отсюда: provenance обязателен, но доверия не даёт. Метка происхождения
маршрутизирует проверки, но не ослабляет их.

## 3. Принципы

1. **Default deny.** Merge и deploy закрыты, пока не собраны вердикты.
2. **Provenance как taint.** У каждого PR есть метка происхождения: модель,
   контекст, входы, формировавшие код. Метка маршрутизирует проверки, но не
   ослабляет их.
3. **Verify the verifier.** Конвейер мутационно тестируется сам: внедрённый
   дефектный PR обязан быть пойман, внедрённый чистый — пройти. Это
   распространяется на экстракторы, классификаторы риска и судью релиза, а не
   только на движки.
4. **Evidence-first.** Каждый вердикт — строка реестра
   {механизм, доказательство, скоуп, статус}; реестр — hash-chain с внешним
   якорем.
5. **Таксономия прежде истории.** Объект аудита — ограниченная матрица
   классов отказов, а не растущая куча уроков.
6. **Lessons compound, folklore evaporates.** Каждое человеческое суждение
   компилируется в артефакт: детектор, контрастивную пару, спецификацию.
   Ревью — это компилятор суждений в артефакты, а не поток проверок.

## 4. Слои верификации

| Слой | Триггер и стоимость | Содержание |
| --- | --- | --- |
| **L0** | каждый PR, секунды | AST-дифф (`libpg_query`/`pglast` для SQL, `libclang`/`tree-sitter` для C) → затронуты ли security-релевантные функции → регресс негативных тестов и детекторов затронутых ячеек |
| **L1** | каждый PR, минуты | Engine-agnostic ансамбль через SARIF-адаптеры (SVACE, PVS-Studio, Semgrep, CodeQL, clang-tidy, Infer, Bandit/ruff/gosec, SpotBugs, SCA/SLSA); находки маршрутизируются в ячейки; детектор коррелированных отказов по потоку PR; сканирование входов, формировавших код |
| **L2** | merge-gate для продуктов с формальной моделью, минуты–десятки минут | Регенерация **среза** формальной модели из изменённых функций через ограниченную грамматику гвардов; bounded mc (`probcli`) или VC по C-слою (`SeaHorn` / `Frama-C`+`WP` → Z3); цели стабильны (из реестра требований), проверяется их выживание на новой модели |
| **L3** | nightly / release, часы | Полная регенерация модели + полный mc + Rodin round-trip; фаззинг парсеров и состояний; пен-тест-симуляция / BAS; само-мутация конвейера как условие релиза |

### 4.1 Конфигурации

Конфигурация — это бандл слоёв + матрица покрытия ячеек + границы mc.

- «Быстрая» — L0+L1 с урезанным ансамблем.
- «Сбалансированная» — плюс L2.
- «Максимальная» — L0–L3.
- «Без формальной модели» — L0+L1+фаззинг.

Цена конфигурации — её **таблица покрытия**: «ячейка → чем покрыта → что
осталось open». Клиент покупает не скорость, а конкретный список закрытых
ячеек и конкретный список дырок. Формальная модель, SVACE-адаптер, фаззинг,
BAS — модули магазина.

### 4.2 Границы L2

L2 — самый амбициозный слой и самый узкий по применимости. Ограниченная
грамматика гвардов выражает authorization-срез: роли, уровни, равенства,
существование атрибута, TTL. Полная спецификация — в
[`guard-grammar.md`](guard-grammar.md).

Что из этого следует:

- **L2 нельзя продавать как покрытие всех ячеек.** Конкурентность, частичная
  запись, транзакции, supply chain грамматикой не выражаются. Для них L2
  обязан возвращать `unroutable`, а не «проверено».
- **Гейт полноты извлечения** (`события кода ⊆ события модели`) работает
  только при доверии к экстрактору. Экстрактор — TCB. Поэтому он входит в
  verify-the-verifier: мутационный набор «внеси гвард в код — экстрактор обязан
  его увидеть; убери гвард — обязан увидеть изменение».
- **Vacuity check.** Пустое или тривиальное множество событий модели делает
  гейт бессмысленным. Пустой срез — это провал, а не успех.
- **Корзина unroutable.** Гвард вне грамматики не отбрасывается молча: merge
  закрыт до решения человека, случай учитывается в статистике.
- **Разрыв модель↔код** остаётся: модель проверяет предикаты, а не
  криптографию, сеть и хранилище. Это записывается в scope каждого вердикта.

### 4.3 Цена = таблица покрытия

Одна и та же ячейка может быть закрыта разными слоями. Таблица покрытия
показывает не «сколько всего прогнали», а «какая ячейка чем закрыта и что
осталось open». Это же интерфейс к клиенту и к аудитору.

## 5. Таксономия и детекторы

### 5.1 Ячейка

Скелет — фиксированная матрица: **класс отказа × класс точки входа × режим
отказа**. Несколько таксономий: безопасность, корректность, сопровождаемость,
производительность. Порядок величин — сотни ячеек, не миллионы уроков.

Ячейка = `{класс, набор детекторов, статус покрытия, остаточный риск,
владелец}`. Машиночитаемая форма — в
[`cell-registry.schema.json`](cell-registry.schema.json); сид-набор из шести
категорий инвариантов — в [`cells.seed.yaml`](cells.seed.yaml). Все сид-ячейки
`open`: они фиксируют форму таксономии, а не покрытие.

### 5.2 Детектор

Детектор — это тест, правило анализа или формальный инвариант. Каждый детектор
мутационно тестируется своим fixture: детектор без fixture не проверен, даже
если он зелёный. Это применение принципа 3 на уровне ячейки.

### 5.3 Поверхность аудита

Одна-две пары сеньорских рук в квартал:

- квартальный пересмотр таксономии;
- статистическая выборка журнала маршрутизации;
- triage корзины `unroutable` с квотой.

Пустая корзина означает полноту таксономии на наблюдаемом потоке.
Наполняющаяся — сигнал неизвестного неизвестного. Расширение таксономии
решают люди по данным, не агент.

### 5.4 Схлопывание масштаба

10 000 уроков = 10 000 fixtures при сотнях ячеек. База знаний аудируется через
ячейки, а не через историю. Число «~200» — design estimate (C-11); пилот на
rbac_pg дал 29 ячеек на одно расширение, но порядок для многокомпонентной
платформы ещё не подтверждён.

## 6. Уроки и бизнес-правила

### 6.1 Объект урока

`{id, таксономия, ячейка_или_кандидат, example_bad, example_good, reasons[],
measurable, detector_id?, status, owner, last_seen}`.

- Измеримые причины становятся детекторами сразу.
- Неизмеримые — контрастивной парой для in-context ИИ-ревью и fixture для
  будущего детектора.
- Повторяющиеся причины дистиллируются в новую ячейку с человеческой
  приёмкой.

### 6.2 Канал обучения

Код, похожий на `example_bad`, в момент написания получает пару
плохой/хороший и причину — в контекст автора и в промпт ИИ-ревьюера. Сеньор
учит только новые случаи; всё остальное учит извлечённый артефакт.

### 6.3 Лестница формализации бизнес-правил

Проза → таблица решений / property / BDD → правило DSL или политика
(OPA/Rego, собственные DSL) → исполняемая спецификация → fixtures.

Правило = claim в реестре `{id, prose, spec_kind, spec, evidence, status,
owner, domain_expert}`. Людям остаются два ограниченных шага: извлечение
правила из головы владельца домена и приёмка формализации. Неформализуемое
живёт в видимом бэклоге открытых правил с квотой.

## 7. Вердикты, маршрутизация и роль человека

### 7.1 Реестр вердиктов

Запись вердикта: хэш коммита + хэш экстрактора + версии верификаторов + хэш
модели + результат. Журнал append-only, hash-chain, внешний якорь.

Варианты полного якоря (выбор — C-13, открыт):

- transparency log: Rekor / SCITT;
- in-toto layout + Sigstore attestations;
- отдельный append-only репозиторий, на который ссылается CI.

Узкий вариант уже реализован для записей статического анализа (C-41): offline
SSH-подпись над каноническими байтами записи, публичный ключ — в
`spec/anchor/allowed_signers`, приватный — вне репозитория.
Он не закрывает C-13: key holder может пере-подписать, а замена
`allowed_signers` + новая подпись обходит проверку.

Якорь нужен, чтобы переписывание журнала было видно. Без внешнего якоря
hash-chain защищает только от случайной порчи, не от целенаправленной подмены.

### 7.2 Risk-based routing

После вердиктов:

- low-risk (доки, конфиги, тесты) — auto-merge при зелёном;
- medium (бизнес-логика, стиль) — лёгкое ревью;
- high (архитектура, влияние) — глубокое ревью.

Классификация — атакуемая поверхность (C-16): код, маскирующийся под тест или
конфиг, получает лёгкий путь. Поэтому правила классификации:

- живут под тем же integrity-контролем, что и конфиг конвейера;
- версионируются и проходят собственные негативные тесты (masquerade-кейсы);
- попадают в выборочный аудит misroutes с квотой.

Auto-merge разрешён только при зелёных вердиктах; классификация не заменяет
вердикты.

### 7.3 Три роли ревью

- **Проверка** растворяется в конвейере.
- **Обучение** становится retrieval контрастивных пар.
- **Законотворчество** остаётся человеку: новые ячейки, приёмка формализаций,
  расширение таксономии.

Экономика («45 → 15 минут») — C-12, `open`. До измерения это гипотеза, а не
обещание. Следующий шаг: инструментировать baseline на пилоте и публиковать
распределение, а не точечную оценку.

## 8. Безопасность самого конвейера

### 8.1 Что атакуют

Конвейер — TCB и цель атаки. Поверхности: оракул, ревьюер-агент (инъекция),
генератор модели (подмена), конфиг (tamper), журнал вердиктов (перезапись),
классификатор риска (маскировка).

### 8.2 Меры

- Верификаторы и наборы правил пинированы.
- Pin-наборы ключей издателей задаются доверенной стороной при bootstrap.
- Конфиг конвейера под integrity-контролем (паттерн config-tamper).
- Вердикты — append-only hash-chain с внешним якорем.
- Проверка, обучение и аудит — разные каналы: сбой логирования не отключает
  проверку.

### 8.3 Verify the verifier: кого именно проверяем

Мутационному тестированию подлежат:

1. **Движки и правила** — внедрённый дефект обязан быть найден.
2. **Экстрактор модели** — внесённый гвард обязан попасть в модель; удалённый —
   обязан изменить модель.
3. **Классификатор риска** — masquerade-кейсы (код под видом теста/конфига)
   обязаны маршрутизироваться в high или попадать в аудит.
4. **Судья релиза конвейера** — см. 8.4.

### 8.4 Само-мутация и внешний судья

Само-мутация конвейера — условие релиза (C-10). Но судья не может быть самим
конвейером: это циклическая проверка. Минимальная конструкция:

- held-out негативная сюита вне репозитория конвейера;
- фиксированные seeds и версии;
- независимая приёмка результата: второй прогон другим составом движков или
  человеческое решение по заранее записанному критерию.

Без названного судьи утверждение «конвейер проверяет себя» остаётся `open`.

### 8.5 Goodhart

Код эволюционирует под гейт, а не под корректность. Меры:

- ротируемые held-out негативные сюиты вне репозитория;
- статистический человеческий аудит выборки, который аудирует **конвейер**, а
  не код;
- периодическая замена части детекторов, чтобы фиксированный гейт не стал
  целевой функцией.

## 9. Потолок (честный скоуп)

**Не ловится:**

- архитектурный долг с временным лагом (код корректен сейчас, проблема через
  N спринтов);
- ошибки бизнес-логики при неверной спецификации;
- масштабируемость без нагрузочного тестирования;
- emergent behavior композиций;
- UX.

Теоретически: halting problem, теорема Райса, разрыв модель↔код.

**Ловится частично:**

- формализованные архитектурные антипаттерны как ячейки (циклические
  зависимости, нарушения слоёв);
- performance-регрессии через A/B-базлайны в CI;
- security debt через SCA.

**Комплементарные процессы вне системы:** architecture review, нагрузочное
тестирование, доменная приёмка, интеграционные тесты, chaos. Система не
отменяет их — она снимает с них рутину и отдаёт им артефакты.

## 10. Кирпичи, которые уже в руках

| Кирпич | Что переносится | Статус в этом документе |
| --- | --- | --- |
| agent-guard | broker/default-deny, taint/provenance, egress + approval с одноразовыми грантами, hash-chain audit, mutation-матрицы, формат BEFORE/AFTER | open (C-14): нужен указатель «репозиторий + путь/коммит» |
| Цитадель / MODEL.md | ручная трассировка код→события как спецификация экстрактора; грамматика гвардов (роли, уровни, равенства, TTL); пайплайн «реестр требований → цели → инварианты»; опыт `probcli` и контрпримеров | open (C-14): нужен указатель |
| Скилы | `invariant-first-code` — содержание ячеек; `negative-test-first` — fixtures и самопроверка; `evidence-first-docs` — реестр и лестница статусов | reviewed (C-01) |
| Дисциплина финмодели | реестр источников для каждого числа | reviewed как практика; к throughput-числам пока не применена |

Этот документ не подтверждает внешние кирпичи. Он фиксирует, что они нужны и
как встроятся, но evidence обязан прийти из их репозиториев.

## 11. Зазор новизны

Предварительный обзор: движки разрознены, дашборды консолидированы, замкнутый
контур ничей. Предки закрыли по куску:

- Tricorder / Error Prone — урок → детектор, фидбек ревьюера;
- Springfield — фаззинг как сервис в CI;
- AWS Automated Reasoning — формальные проверки в CI для узких доменов;
- SLSA / in-toto — provenance сборок;
- Letta / MemGPT — иерархическая память;
- assurance-case tooling (GSN/SACM) — структура аргумента, но не исполняемый
  merge-gate.

Заявленная связка: **provenance-taint уровня PR + регенерация модели из
неаннотированного кода как merge-gate с гейтом полноты извлечения +
само-мутация конвейера как условие релиза + top-down база знаний с
ограниченной поверхностью аудита + верификационная пропускная способность как
единица продукта**.

Статус — `open` (C-15). Перед внешней публикацией нужен систематический
prior-art sweep, а не этот абзац.

## 12. Дорожная карта

**Фаза 0 — знаниевый слой (этот каталог).**

- Концепт с реестром утверждений.
- Схема реестра ячеек и сид-набор.
- Спецификация грамматики гвардов и её границ.
- `cell_lint` и адверсариальные кейсы: CL1–CL6, 40/40 (C-17).
- Пилотный реестр rbac_pg: 29 ячеек, 26 non-open, 3 open, 0 ошибок
  CL1/CL3/CL4 (C-18).
- Второй пилот `craft-i18n` (Rust, не-RBAC, не-БД): 14 ячеек, 13 non-open,
  1 open, 0 ошибок CL1–CL5, 12/13 детекторов с mutation fixture и один
  документированный exemption; claim-леджер из 9 claim'ов (C-09 —
  `static-refinement` с записанным static-analysis прогоном).
- Run-record в evidence (V2-01/V2-02): схема, проверки L1/L2, 8 eval-кейсов;
  все 7 test-claim'ов `craft-i18n` несут хэши лога и артефакта, дату, exit
  code и исполненные ID. Пере-датировка и неисполненная ссылка ловятся L2.
- Tool-output в evidence (V2-10): `model-checked` и `proven` несут вывод инструмента
  (`tool`, `command`, `output` + хэш, `exit_code`, `finished_at`), а не только
  артефакт; L4 отвергает такой статус без записи, `model-checked` — без `bound`.
  7 eval-кейсов `tool-output-*`.
- Runtime-enforcement evidence (V2-15/V2-16): детектор `runtime-enforcement` требует
  `negative_test` (ID резолвится через `--suite-glob`), ячейка — `enforced_at`,
  `oracle` и `violation_response`; первые реальные ячейки — rbac_pg CELL-001
  (отказ 42501) и craft-i18n CELL-003 (Problem с номером строки).
- Фаззинг (V2-17): `tools/fuzz_run.py` — seed-корпус, случайные мутации с фиксированным
  seed, oracle-правила по ИЛИ, бюджет и запись по `schemas/fuzz-run.schema.json`;
  записанный прогон `claim_lint` (155 исполнений, seed 20261107) — `clean`, digest
  воспроизводится через `make fuzz-claim-lint`. 5 eval-кейсов.
- Триаж находок (V2-18): `tools/fuzz_triage.py` требует ровно одну запись на находку —
  `covered` / `new` с cell, detector и fixture или `not-a-bug` с причиной; cell и detector
  резолвятся в реестре, fixture — в mutations-файле. 13 eval-кейсов; записанный прогон
  без находок, поэтому триаж пуст и это единственный допустимый пустой случай.
- Покрытие (V2-20): `tools/coverage_report.py` — CV1 висячая ссылка (всегда error),
  CV2 несвязанные символы, CV3 stale claims, CV4 детекторы без fixture; маппинг
  файловый, извлечение символов узкое. 14 eval-кейсов, `make coverage` в `make verify`,
  снимки — `spec/coverage/`: `rbac_pg` 67/80 mapped, `craft-i18n` 26/26, 0 stale и
  0 детекторов без fixture.
- Diff-покрытие (V2-07): `tools/diff_coverage.py` проверяет только choke points из
  `enforced_at`; DC1/DC2 — изменённый путь или символ без non-open claim, DC3 —
  нелокализуемое объявление (всегда error), DC4/DC5 — явные info о пустом диапазоне
  и реестре без объявлений. 19 eval-кейсов, снимки — `spec/diff-coverage/`:
  `rbac_pg` `v1.3.1..HEAD` 2/2 mapped, `craft-i18n` `f0dd77b^..f0dd77b` 2/2 mapped.
  Гейт вынесен из `make verify`: ему нужен base ref; шаблон PR-гейта —
  `ci/diff-coverage.yml`, targets — `make diff-coverage` и `make diff-coverage-record`.
- Извлечение choke points (V2-22): `tools/choke_points.py` ищет структурных
  кандидатов в обычном коде (Python `ast`; Rust/SQL — маскирующие лексеры
  комментариев, строк и dollar-quote) и маппит их на классы ячеек по
  `spec/choke-points/rules.yaml`. Правила упорядочены, первый матч выигрывает;
  кандидат без правила — `unclassified`, а не `other`. Измерено 2026-11-07:
  `rbac_pg` 1585 определений → 1413 кандидатов, 867 classified / 546
  unclassified (38,6 %); `craft-i18n` 128 → 64, 47 / 17 (26,6 %); оба —
  914/1477 = 61,9 % classified. 14 eval-кейсов; снимки — `spec/choke-points/`;
  targets — `make choke-points` и `make choke-points-record`. Порог CP1 не в
  `make verify`, пока шум не снижен.
- Escape hatch `other` + `routing_note` и измерение U (V2-25): 0/43 = 0,0 %;
  гейт `--max-share 0` в `make verify`. Пороги N = 87,5 % и U = 0,0 %
  зафиксированы артефактами 2026-11-07 (V2-32).
- Калибровка таксономии и production-реестр — не входят в фазу 0.

**Фаза 1.** L0+L1 на собственных репозиториях: AST-экстрактор, SARIF-адаптеры
двух-трёх движков, таксономия безопасности из категорий `invariant-first`,
реестр вердиктов.

**Фаза 2.** Грамматика гвардов + срезовая регенерация на пилоте (L2), гейт
полноты извлечения, мутационный набор экстрактора, роутер базы знаний с
корзиной `unroutable`.

**Фаза 3.** Само-мутация конвейера с внешним судьёй, held-out сюиты, канал
обучения (retrieval контрастивных пар в момент написания).

**Фаза 4.** Конфигурации как продукт с матрицей покрытия вместо прайса;
сертификационный модуль для КИИ; VC-путь по C-слою (SeaHorn/Frama-C).

### 12.1 Бэклог v0.2 (задачи)

Не обязательства и не статус: задача закрывается только evidence.

**P0 — целостность evidence**

- [x] V2-01. Схема run-record: commit, artifact_sha256, log_sha256, runner, command, exit_code, tests_run, tests_passed, timestamps (`schemas/run-record.schema.json`, `$ref` из `schemas/claim-ledger.schema.json`).
- [x] V2-02. `claim_lint`: проверять run-record вместо строкового evidence — L1 проверяет форму и согласованность commit/command, L2 — хэши лога и артефакта, дату `finished_at`, exit code, счётчики из summary и наличие каждого процитированного ID в логе. 8 eval-кейсов (`run-record-*`), 7 test-claim'ов `craft-i18n` с записанным логом (`spec/pilots/craft-i18n/runs/`); у леджера `rbac_pg` записи нет, поэтому 7 L2-warning — видимый долг.
- [x] V2-03. `status_diff`: отсутствующий или неизвестный base-ref → error; исключение только `--first-release`.
- [x] V2-04. `cell_lint`: отсутствующий base registry → error через `--require-base`, а не запуск без гейта.
- [x] V2-05. Удалённый claim или cell → error либо обязательное `retired:` с причиной: `retired: [{id, reason, date}]` в схеме леджера и реестра, L1/CL1 проверяют форму (причина, дубликат, живой ID), `status_diff` и CL6 падают на удалении без надгробия и на исчезнувшем надгробии. 3 кейса linter, 4 кейса cell-lint, 5 сценариев status-diff.
- [x] V2-06. CL2: отсутствие mutation_fixture → error для классов security и correctness — для остальных классов warning, документированный `mutation_exemption` остаётся info (`tools/cell_lint.py`, `evals/cell-lint/cases/mutation-required-*.yaml`).
- [x] V2-07. Diff-покрытие: изменённые choke-point пути и символы обязаны отображаться на claim: `tools/diff_coverage.py` (DC1 путь, DC2 символ, DC3 нелокализуемое объявление — всегда error, DC4 пустой диапазон, DC5 реестр без объявлений), 19 eval-кейсов, `ci/diff-coverage.yml`. Измерено 2026-11-07: `rbac_pg` `v1.3.1..HEAD` — 110 файлов, 1 путь и 1 символ, 2/2 mapped; `craft-i18n` `f0dd77b^..f0dd77b` — 2/2 mapped. Гейт не в `make verify`: ему нужен base ref; `make diff-coverage` и `make diff-coverage-record` — отдельные targets.
- [x] V2-08. `make verify` — единая локальная точка запуска всех статических гейтов: evals, сид-реестр, оба пилотных реестра с claim-леджерами, леджеры, status-diff (`Makefile`). Mutation-прогоны вынесены: `make mutations` (стенд PostgreSQL), `make mutations-i18n` (cargo), `make mutations-all`.
- [x] V2-34. Связь evidence с claim: L6 в `claim_lint` требует `shared_tests: [{id, reason}]` для теста, цитируемого двумя claim'ами, и отвергает non-open claim, у которого все тесты заимствованы, даже если sharing объявлен; L1 проверяет форму поля, схема обновлена. 6 eval-кейсов (`shared-*`), общий тест `each_bad_row_is_one_problem` объявлен в C-02 и C-03; red-team drill `borrow-another-claims-evidence` переведён в blocked, добавлен `borrow-and-declare-sharing` — тоже blocked. Остаток: соответствие утверждений теста формулировке claim не проверяется; одна собственная нерелевантная цитата проходит. Пере-датировка остаётся дырой C-13.
- [x] V2-09. Негативные контроли в `evals/linter`: заглушка (`fake-test-id`), пере-датировка (`run-record-date-mismatch`, `run-record-log-hash`), посторонний коммит (`unrelated-commit`: коммит резолвится, но артефакт изменён после него — L2 сравнивает артефакт с блобом на коммите) и пустая модель (`empty-claims`: пустой леджер — L1 error, а не вакуумный pass). 25/25 кейсов.
- [x] V2-10. `model-checked` и `proven` требуют вывод инструмента, а не существование артефакта: схема `schemas/tool-output.schema.json` (`tool`, `command`, `output` + `output_sha256`, `exit_code`, `finished_at`; опционально `version`, `commit`, `verdict`, `bound`), L1 проверяет форму и согласованность commit/command, L2 — хэш вывода, дату `finished_at` и `exit_code=0` для не-open, L4 — отсутствие `tool_output` для `model-checked`/`proven` и отсутствие `bound` для `model-checked`. 7 eval-кейсов; пилоты не затронуты (в них нет этих статусов).

**P1 — принуждение**

- [x] V2-11. `run_mutations.py` в CI для изменённых cell'ов: `tools/mutation_plan.py` отображает diff целевого репозитория на ячейки через `enforced_at`, `artifact` детектора, `artifact` фикстуры и изменённый реестр, пишет JSON-план; оба runner'а принимают `--plan` (пустой план — no-op, exit 0) и `--only-cell`; `--require-fixtures` падает, если изменённая ячейка без fixture и без `mutation_exemption`; 13 eval-кейсов, `ci/mutation-changed.yml`, `make mutation-plan`. Измерено 2026-11-07: `rbac_pg` `v1.3.1..HEAD` — 25/25 fixtures, 0 uncovered; `craft-i18n` `f0dd77b^..f0dd77b` — 7/12 fixtures, 0 uncovered; шаблон CI на реальном runner'е не прогонялся.
- [x] V2-12. Проверять, что упали именно предсказанные ID, а не любой тест: оба runner'а сравнивают множество упавших тестов с `expect_failures` точно (`spec/pilots/rbac_pg/mutations/run_mutations.py`, `spec/pilots/craft-i18n/mutations/run_mutations.py`).
- [x] V2-13. Negative control для `tested` в security: записанный прогон с отключённым guard'ом — закрыт mutation fixtures: у каждого tested security-детектора есть предсказанный падающий прогон или exemption (`spec/pilots/rbac_pg/mutations/README.md`).
- [x] V2-14. Mutation fixtures для оставшихся детекторов пилота — 25 фикстур, 24 детектора с фикстурой и 3 с `mutation_exemption`; все 25 совпали (`spec/pilots/rbac_pg/mutations/README.md`).
- [x] V2-15. Поля `enforced_at`, `oracle`, `violation_response` в ячейке: обязательны, когда детектор имеет `kind: runtime-enforcement`; CL1 проверяет форму. Первые ячейки — `rbac_pg` CELL-001 и `craft-i18n` CELL-003.
- [x] V2-16. Evidence-kind `runtime-enforcement` с обязательным негативным тестом: `negative_test` в детекторе, CL1 требует непустой ID, CL3 резолвит его через `--suite-glob` (6 eval-кейсов, включая unresolved и unchecked), CL2 ограничивает статус ячейки уровнем `tested`.

**P2 — непрерывный контур**

- [x] V2-17. Фаззинг-адаптер: oracle, seed-корпус, бюджет, фиксированный seed, артефакт прогона: `tools/fuzz_run.py`, схема `schemas/fuzz-run.schema.json`, правила `exit:N`, `exit-not-in:`, `stdout-contains:`, `stderr-contains:`, `timeout`; `executions_digest` воспроизводится при том же корпусе и seed. Записанный прогон `claim_lint` — 5 seed-леджеров, 150 мутаций, 155 исполнений, seed 20261107, `clean`; 5 eval-кейсов, `make fuzz-claim-lint` сверяет digest.
- [x] V2-18. Триаж находок фаззера → cell + detector + fixture: `tools/fuzz_triage.py` (T1–T4), схема `schemas/fuzz-triage.schema.json`, 13 eval-кейсов; `make check-fuzz-triage` в `make verify`. Записанный прогон чист, поэтому триаж пуст; инъекция находки в копию записи даёт exit 1.
- [x] V2-19. Scheduled-запуск фаззера, не блокирующий merge: `.github/workflows/fuzz-nightly.yml` — cron `30 2 * * *` и `workflow_dispatch`, без `push`/`pull_request`; реплеит `spec/fuzz/runs/claim-lint-2026-11-07.json` через `make fuzz-claim-lint`, падает на расхождении `executions_digest`; артефакт `fuzz-record-<run_id>` с записью и findings, 90 дней. Первый прогон: [42394278295](https://github.com/Bra1nZ/dev-sec-skills/actions/runs/42394278295), 2026-11-07, commit `3110214`, success, digest `93e1af3183658aa6…`, seed 20261107, 155 исполнений, 0 находок; скачанный артефакт сверен локально. Повторный dispatch на `4dd83be`: [42414910152](https://github.com/Bra1nZ/dev-sec-skills/actions/runs/42414910152), 2026-11-07T21:14Z, success, записанный и воспроизведённый digest совпали (`93e1af3183658aa6`), 155 исполнений, 0 находок. Ночной schedule сработал впервые: [42466635404](https://github.com/Bra1nZ/dev-sec-skills/actions/runs/42466635404), event `schedule`, 2026-11-08T09:18:42Z→09:19:01Z, commit `7bf8192`, success, recorded и replay digest совпали (`93e1af3183658aa6`), seed 20261107, 155 исполнений, 0 находок; скачанный артефакт закоммичен как `spec/fuzz/runs/claim-lint-2026-11-08-schedule.json` (sha256 `8ca3fcb9…`). Ограничения: cron объявлен на `02:30Z`, а прогон стартовал в `09:18:42Z` — GitHub задерживает schedule-запуски на часы, поэтому «ночной» прогон не гарантирует время, и задержанный или пропущенный запуск никто не отслеживает; закоммиченный артефакт — это скачанный вывод CI, а не локальный прогон, и он не якорится (C-41 покрывает три evidence-канала, fuzz-запись — нет); replay доказывает детерминизм и целостность входов, а не поиск новых багов; артефакт в GitHub живёт 90 дней и не является внешним anchor (C-13); красный прогон не блокирует merge и никого не уведомляет.
- [x] V2-20. Отчёт покрытия: unmapped symbols, stale claims, cells без fixture: `tools/coverage_report.py` (CV1–CV4), 14 eval-кейсов, `make coverage` в `make verify`, записанные снимки `spec/coverage/`. Измерено 2026-11-07: `rbac_pg` — 80 символов, 67 mapped, 13 unmapped в двух suite-файлах, которые никто не цитирует; `craft-i18n` — 26/26; 0 stale claims и 0 детекторов без fixture в обоих.

**Трек general-code — выход за пределы RBAC**

- [x] V2-21. Каталог инвариантов вне БД и ролей: input validation, authn/session, secrets, lifecycle, transactions — `spec/invariants/catalog.yaml` (5 категорий × 3 инварианта; statement, enforcement, failure mode, entry points, choke-point rule, seed cells, oracle, violation response, evidence kind, negative test, ≥2 bypasses, limitations), `schemas/invariant-catalog.schema.json`, `tools/invariant_catalog.py` (INV1–INV5: категории, форма, ссылки, evidence, покрытие seed-ячеек), 15 eval-кейсов, `make invariants` в `make verify`, снимок `spec/invariants/2026-11-07-coverage.json`. Измерено 2026-11-07: 15 инвариантов, 5 категорий, 9/12 seed-ячеек referenced + 3 out_of_scope, 9/11 choke-point rules used (unused: `sql-rls`, `migration`), 0 errors; все 15 инвариантов `open` — детекторов нет, negative tests остаются спецификацией.
- [x] V2-22. AST-экстрактор choke points для обычного кода и маппинг на классы ячеек: `tools/choke_points.py` (Python `ast`, декораторы входят в спан; Rust/SQL — структурные маскирующие лексеры; SQL-спан покрывает dollar-quoted тело), `spec/choke-points/rules.yaml` (signals + упорядоченные rules, `other` запрещён, unclassified — gap правил, не cell), 14 eval-кейсов и интеграция в `tools/diff_coverage.py` (19/19 кейсов). Измерено 2026-11-07: `rbac_pg` 1585 определений, 1413 кандидатов, 867 classified / 546 unclassified (38,6 %); `craft-i18n` 128, 64, 47 / 17 (26,6 %); оба 61,9 % classified. CP1 не в `make verify`; `make choke-points` и `make choke-points-record` — отдельные targets, снимки в `spec/choke-points/`.
- [x] V2-23. SARIF-адаптеры двух-трёх движков как источники evidence: `tools/sarif_evidence.py` нормализует SARIF 2.1.0, резолвит engine по `tool.driver.name` и маппит каждый result по rule ID через `spec/sarif/adapters.yaml` (упорядоченные правила, первый match выигрывает); `unmapped` с причиной вместо `other`; `cell` опционален, но обязан резолвиться и совпадать по `failure_class` с ячейкой; дедупликация и стабильный digest; `--max-unmapped`, `--require-engines`, `--reject-fixtures`; `schemas/sarif-evidence.schema.json`; 20 eval-кейсов; `make sarif` / `make sarif-record`. Измерено 2026-11-07 на authored fixtures (перегенерировано 2026-11-08 после удаления mismatch cell-маппингов): 3 движка, 7 findings, 0 unmapped, 1 duplicate, 0 с cell, digest `caf2a4f9fe24ba42`; на момент V2-23 реальных прогонов движков не было, fixtures помечены `properties.dev-sec-skills/fixture = true`; позже Bandit 1.9.4 + Semgrep 1.184.0 дали реальный двухдвижковый отчёт (C-08).
- [x] V2-24. Второй пилот на не-RBAC кодовой базе (веб-сервис или CLI): `craft-i18n`, Rust-крейт проверки каталогов переводов, 14 ячеек, 13 tested / 1 open, CL1–CL6 без ошибок, 12/13 детекторов с mutation fixture, 8 claim'ов (`spec/pilots/craft-i18n/`).
- [x] V2-25. Таксономия проверена на не-RBAC пилоте; `unroutable` измеряется через escape hatch: `taxonomy_class` или `failure_mode` = `other` с обязательным `routing_note`, `tools/unroutable.py`, гейт `--max-share 0` в `make verify`. Измерено 0/43 = 0,0 %; до escape hatch 0 было структурным (`product-trials.md` §2.1).
- [x] V2-26. Критерий выхода выполнен: два пилота (`rbac_pg`, `craft-i18n`), U измерен (0/43), N и U зафиксированы до первого продуктового прогона, 21/24 security-детекторов с fixture.

**Граница формальной модели**

- [x] V2-27. Зафиксировать в `guard-grammar.md`: L2 — это model-diff и проверка выживания стабильных целей; синтез теорем из кода не заявляется.
- [x] V2-28. Bounded fallback для проверки выживания целей: `tools/bounded_check.py` запускает инструмент в отдельной группе процессов и убивает её по `--timeout`; запись `tool_output` обязана нести `status` (`completed`/`unverified`/`failed`/`error`), `timed_out`, `bound_seconds`, `elapsed_seconds`; L1 отвергает противоречие `timed_out` со статусом, L2 не даёт `status != completed` поддерживать non-open claim; `evals/bounded-check/` 10/10 и 5 новых linter-кейсов (linter 40/40); правила — guard-grammar §6.6.
- [x] V2-29. Доказательства (`proven`) — event-driven: триггер — изменение choke point или модели, не каждый PR: `tools/proof_plan.py` читает манифест зависимостей (`schemas/proof-manifest.schema.json`), сопоставляет его с `base..head` и печатает `rerun`/`fresh` с причиной; гейты `--require-fresh` (перепрогон не выполнен) и `--require-complete` (изменённый proof-материал не объявлен), exit 2 на битый манифест. `spec/proofs/manifest.yaml` пуст: ни одна claim здесь не `proven`, и планировщик прямо говорит, что пустой манифест делает `--require-fresh` вакуумным. Кейсы — `evals/proof-plan/`: 36/36; `evals/proof-plan/mutation_selftest.py` — 8/8 мутаций планировщика пойманы кейсом, названным по поведению (`make proof-plan-selftest`, вне `verify`). Ограничения: синтетические репозитории и demo на реальном диапазоне `a50fbda..HEAD`, настоящих доказательств не перепрогонялось; манифест — это scope, а не полнота; свежесть — сравнение `finished_at` с временем коммита, а не проверка, с какого checkout'а снята запись; хэш и семантику записи проверяет `claim_lint` и никто соответственно.
- [x] V2-30. Бюджет синхронизации среза измерен как RERUN, а не как обещание: манифест объявляет 2 записи (P-01 согласие, P-02 мутации), 4 `depends_on`-пути и 3 пути `model`/`encoding`/`tooling`; полный перепрогон среза на тёплом кэше — 0,953 с + 7,412 с = 8,365 с. Измерено 2026-11-07: диапазон `a3293ec..4f3e25c` (9 изменённых файлов, включая модель) — 2 fresh / 0 rerun по правилу `record-covers-change`; docs-only диапазон `02be7ab~1..02be7ab` (5 файлов) — 0 rerun / 2 fresh; `--require-fresh` exit 0. PR, меняющий `crosscheck/c02-row-model/src/**`, `Cargo.toml`, `Cargo.lock` или `TARGET`, требует 2 перепрогона; изменение target после пина не видно планировщику и ловится только `claim_lint` L2. Остаток: ручная правка модели при изменении формата не измерена; холодная сборка (~38 с) зависит от машины; метрика фиксирует стоимость перепрогона, а не качество синхронизации.

**Граница продуктовых испытаний**

- [x] V2-31. Зафиксировать границу в `spec/conveyor/product-trials.md`: критерии входа и протокол замера; числа — только после измерений.
- [x] V2-32. Данные для порогов измерены и зафиксированы в `product-trials.md` §2.1 с артефактами: N = 87,5 % (21/24), U = 0,0 % (0/43), дата 2026-11-07.
- [x] V2-35. Санитайзер как evidence-канал: `schemas/sanitizer-run.schema.json` и `evidence[].sanitizer_runs` только на `kind=test`; L1 проверяет форму (инструмент, флаги, команда, вывод, хэш, exit code, ISO-даты, статус), L2 — хэш вывода, дату `finished_at`, `status=completed`/`exit_code=0` для non-open и противоречие «clean-запись + finding-строка». 7 eval-кейсов (`sanitizer-*`); боевой ASan-прогон craft-i18n на nightly 1.101.0: 26/26 тестов, exit 0, 0 finding-строк, лог `spec/pilots/craft-i18n/runs/asan-test-2026-11-07.log`, probe `asan-instrumentation-2026-11-07.md` (`__asan_init` найден); red-team drill `sanitizer-findings-hidden` — blocked. C-02 остаётся `tested`: санитайзер усиливает evidence, но не поднимает статус. Остаток: чистый прогон не доказывает отсутствие дефекта; std не инструментирован; L2 проверяет запись, а не бинарь; recoverable UBSan не ловится; пере-датировка и согласованная подделка остаются (C-13).
- [x] V2-36. Статический анализ как evidence-канал со встроенным triage: `schemas/static-analysis-run.schema.json` и `evidence[].static_analysis_runs` только на `kind=static-analysis`; L1 проверяет форму и четыре disposition, L2 — хэши правил/SARIF/отчёта, `finished_at`, `completed`+exit 0, `report.format`, наличие `output_sha256` среди входов отчёта, engine с `runs>0`, нулевые `unmapped`/`fixture_inputs`, биекцию triage с находками и резолвинг cell/detector/fixture, L4 требует запись для `static-refinement`. 17 eval-кейсов (`static-analysis-*`), 20 вместе с якорными кейсами C-41; боевой прогон Semgrep OSS 1.184.0 на craft-i18n `5c5c554` с тремя авторскими MIT-правилами: 5 находок, 0 unmapped, 0 fixture, exit 0, F-003/F-004 — реальный `covered` через само-пилот, F-001/F-002/F-005 — `out-of-scope` (C-09); правила `d05187db…`, SARIF `3e32c249…`, отчёт `6ed91da2…`. Semgrep Registry `p/ci` не вендорится из-за Rules License v1.0. Red-team drill `static-findings-hidden` — blocked. Остаток: один движок и один прогон, `new` реальный только в само-пилоте, `covered` реальный только через cross-pilot маршрут F-003/F-004 (детектор принадлежит само-пилоту и не включён в CI craft-i18n), правила текстовые и не benchmark, URL-источник правил не хэшируется повторно, согласованная подделка и пере-датировка остаются (C-13).
- [x] V2-37. Внешний якорь evidence-записи (C-41): `tools/anchor_subject.py` задаёт канонические байты трёх каналов (static-analysis: engine, command, хэши правил и обоих выходов, commit, exit code, timestamps, status, `cells`, весь triage; run_record: runner, command, commit, exit code, timestamps, хэши лога и артефакта, счётчики; sanitizer: tool, version, build_flags, command, exit code, timestamps, хэш вывода, status), `tools/anchor_run.py keygen|create|verify --channel` подписывает и проверяет их через `ssh-keygen -Y sign/verify` (ed25519) с namespace канала; `anchor` обязателен в `static_analysis_runs[]`, `run_record` и `sanitizer_runs[]`, L2 пересчитывает байты, хэширует subject/signature и сверяет подпись с закоммиченным `spec/anchor/allowed_signers`. Приватный ключ вне репозитория. 13 якорей: 3 static (C-01 runs 0/1, C-09 run 0), 9 run_record (craft-i18n C-01…C-07, включая два у C-02, и само-пилот C-01) и 1 sanitizer (craft-i18n C-02 ASan); 10 из них — backfill 2026-11-08 над записями 2026-11-07, поэтому подпись доказывает неизменность после подписи, а не дату прогона. 2026-11-08 `cells` добавлен в подписываемые поля, поэтому C-01/0 и C-09/0 пере-подписаны, а static C-01/1 не изменился (нет `cells`). 7 негативных linter-кейсов (`static-analysis-anchor-{missing,tampered,bad-signature}`, `run-record-anchor-{missing,tampered}`, `sanitizer-anchor-tampered`, `static-analysis-anchor-unknown-signer`), README о ротации ключа в `spec/anchor/`, red-team drills `forge-anchored-record` и `forge-anchored-test-record` — blocked (18/18). Каталог якорей перенесён из `spec/static-analysis/anchor/` в `spec/anchor/`: subject не содержит пути, поэтому подписи остались валидными. Остаток: key holder может пере-подписать, замена `allowed_signers` + новая подпись обходит проверку, нет transparency log/timestamping/отзыва, proof/review не якорятся (C-13 остаётся open).

- [x] V2-38. Bootstrap-путь для чужого репозитория: `tools/bootstrap.py` — детерминированный идемпотентный планировщик/генератор (`--target`, `--name`, `--suite-glob`, `--ledger`, `--registry`, `--with-ci`, `--with-anchor`, `--source`, `--signer`, `--anchor-dir`, `--allowed-signers`, `--force`, `--dry-run`); вендорит `tools/{claim_lint,cell_lint,status_diff,anchor_subject,anchor_run}.py`, `styles/` и `schemas/` без README, `spec/conveyor/cell-registry.schema.json` и пишет `tools/dev-sec-skills.VERSION` (source commit, dirty, sha256 каждого файла); создаёт `open`-шаблоны реестра и леджера (один claim с `evidence: []`, один cell без детекторов), рендерит `.github/workflows/{claim,cell}-lint.yml` из `ci/` с `FIRST_RELEASE=1` и создаёт/переиспользует ed25519-ключ вне target, коммитя только `allowed_signers`. `--force` обновляет вендоренные файлы и CI, но никогда не перезаписывает реестр и леджер. Самопроверка: `evals/bootstrap/run_evals.py` (4/4: создание и хэши VERSION, идемпотентность, дрейф и восстановление, зелёные open-гейты, путь до `tested` с якорем, запрет перезаписи леджера, падение на правке подписанного поля, `status_diff` без нового evidence, отказы на target внутри source и ключ внутри target), детектор `D-BOOTSTRAP` в self-pilot (C-02) и записанный лог/якорь в `spec/pilots/dev-sec-skills/runs/`; документация `docs/onboarding.md`/`docs/onboarding.en.md`. Остаток: eval синтетический (один временный git-репозиторий, stdlib-раннер, Linux); CI-шаблоны сохраняют изменяемые `actions/checkout@v4`/`setup-python@v5` и требуют пина перед включением; путь проверен на одном типе раннера; C-13 (пере-подпись держателем ключа, замена `allowed_signers`, отсутствие transparency log/timestamping/отзыва) остаётся; bootstrap не проверяет, что тест относится к формулировке claim.


- [x] V2-39. Append-only журнал вердиктов (C-13): `tools/verdict_journal.py verify|append` — `spec/journal/verdicts.jsonl` (одна canonical JSON-строка на вердикт: `seq`, `date`, `ledger`, `claim`, `status`, `evidence` = отсортированные sha256 identity `(kind, commit, artifact, command, tests, date)`, `prev`, `hash`) и голова `spec/journal/head.json` + `.sig` (namespace `dev-sec-skills-verdict-journal`; поля `seq`, `head`, `journal_sha256`, `generated`, `signer`, `namespace`, `ledgers` с точными байтами каждого леджера). Гейт J1 — цепь (`seq` 1..N, `prev`, пересчёт `hash`, словарь статусов); J2 — последнее слово журнала совпадает с леджером (статус, набор evidence, tombstone `retired`, неизвестный леджер); J3 — журнал на `--git-ref` является байтовым префиксом рабочего файла (удаление, усечение, перезапись); J4 — голова canonical, называет последнюю запись и хэш файла, называет текущие байты каждого леджера и проверяется `ssh-keygen -Y verify` против `spec/anchor/allowed_signers`. Append атомарен (tmp + `os.replace`, подпись временной головы до замены) и отказывается при битой цепи, голове или истории; signer обязан быть в `allowed_signers` с тем же ключом. Backfill: 11 записей (2 само-пилота + 9 craft-i18n), голова seq 11; 12-я запись — сам C-42, итого seq 12, signer `dev-sec-skills-anchor-2026-11-08`. `evals/journal/run_evals.py` — 14 кейсов (append/verify, идемпотентность, статус и evidence без записи, правка прозы с пере-подписью головы, retired, правка/удаление записи, усечённая история, не-canonical и пере-записанная голова, чужой signer, отказы append); детектор `D-JOURNAL` в self-pilot; `make journal`, `make journal-append`; README `spec/journal/README.md` с моделью угроз; red-team drills `drop-a-journal-entry` (blocked) и `rewrite-journal-and-resign` (allowed, записанная дыра), 20/20. Остаток: внешний `../rbac_pg/docs/claims.yaml` вне журнала; proof/review-записи не якорятся; key holder, замена `allowed_signers` с пере-подписью и правка истории git обходят всё; нет transparency log, timestamping и отзыва ключа; дата записи — день журналирования, backfill не доказывает прошлое; bootstrap не вендорит журнал.

## 13. Открытые вопросы и следующий evidence

1. **Пилот.** Выбран rbac_pg; пилотный реестр собран (C-18): 29 ячеек,
   0 ошибок CL1/CL3/CL4. Все десять suite'ов перезапущены на свежем стенде
   2026-11-06; 24 из 27 детекторов имеют mutation fixture, ещё 3 —
   документированный `mutation_exemption`, CL2 без предупреждений. Второй
   пилот `craft-i18n` (Rust, не-RBAC, не-БД) собран 2026-11-06: 14 ячеек,
   12/13 детекторов с фикстурой, 9 claim'ов (C-09 — `static-refinement`), 0 ошибок; его открытая CELL-002
   фиксирует реальный пробел с Unicode Cf-символами. Остаётся решить,
   покрывает ли claim-леджер не только FSTEC-матрицу. Без этого C-07…C-12
   остаются гипотезами.
2. **Якорь вердиктов.** Append-only журнал с подписанной головой
   реализован (V2-39) и закрывает молчаливую правку прошлого в пределах
   одного держателя ключа. Остаётся выбрать внешнюю опору: Rekor/SCITT,
   in-toto+Sigstore, transparency log или timestamping — иначе key holder и
   замена `allowed_signers` с пере-подписью остаются вне модели угроз.
3. **Судья само-мутации.** Кто и по какому критерию принимает, что дефектный PR
   пойман.
4. **Калибровка таксономии.** Сколько ячеек реально используется, какова доля
   `unroutable`, сколько времени занимает квартальный пересмотр.
5. **Экономика.** Baseline времени ревью, FP rate, latency. Публиковать
   распределение, не среднее.
6. **Prior-art sweep.** Систематический обзор до внешней публикации C-15.
7. **Квалификация экстрактора.** Мутационный набор, vacuity check, границы
   применимости.
8. **Классификатор риска.** Masquerade-кейсы и квоты аудита misroutes.

## Приложение A. Связь с артефактами репозитория

| Артефакт | Роль в концепте |
| --- | --- |
| `skills/invariant-first-code/` | Содержание ячеек: категории инвариантов, точки принуждения, fail-closed |
| `skills/negative-test-first/` | Fixtures детекторов и самопроверка верификаторов |
| `skills/evidence-first-docs/` | Формат вердикта и лестница статусов |
| `schemas/claim-ledger.schema.json` | Прототип реестра вердиктов |
| `tools/claim_lint.py` | Проверки L1–L6, которые переиспользует `cell_lint` |
| `tools/cell_lint.py` | Проверки CL1–CL6 реестра ячеек |
| `tools/status_diff.py` | Запрет эскалации статуса без новой evidence |
| `tools/coverage_report.py` | CV1–CV4: висячие ссылки, несвязанные символы, stale claims, детекторы без fixture |
| `tools/invariant_catalog.py` | INV1–INV5: полнота пяти категорий, форма, ссылки, evidence и покрытие seed-ячеек |
| `spec/invariants/` | Каталог инвариантов вне БД и ролей: 15 записей, 5 категорий, out_of_scope и снимок покрытия |
| `tools/bounded_check.py` | V2-28: bounded-прогон внешнего инструмента; таймаут убивает группу процессов и даёт `unverified` |
| `schemas/tool-output.schema.json` | Машиночитаемая запись прогона: `status`, `timed_out`, `bound_seconds`, хэш вывода |
| `schemas/sanitizer-run.schema.json` | V2-35: запись санитайзер-прогона: инструмент, флаги инструментации, команда, вывод и его хэш, exit code, статус |
| `spec/pilots/craft-i18n/runs/asan-test-2026-11-07.log` | Записанный ASan-прогон craft-i18n: 26/26 тестов, exit 0, находок нет |
| `evals/bounded-check/` | Адверсариальный набор для супервизора: 10 кейсов, включая выживание группы процессов и связку с `claim_lint` |
| `tools/sarif_evidence.py` | V2-23: SARIF 2.1.0 → нормализованные findings с классом, режимом отказа и опциональной ячейкой; `unmapped` с причиной |
| `spec/sarif/` | Адаптеры трёх движков, authored fixtures с явной provenance и снимок отчёта |
| `tools/anchor_subject.py`, `tools/anchor_run.py` | C-41: канонические байты трёх evidence-каналов и команды `keygen`/`create`/`verify --channel` для SSH-якоря |
| `spec/anchor/` | C-41: закоммиченный `allowed_signers`, пары subject/signature 13 записей трёх каналов и README о добавлении, отзыве, ротации и потере ключа; приватный ключ вне репозитория |
| `tools/mutation_plan.py` | V2-11: diff → изменённые ячейки → выбранные mutation fixtures |
| `tools/proof_plan.py` | V2-29: diff → доказательства, которые обязаны перепрогнаться; `--require-fresh` и `--require-complete` |
| `spec/proofs/` | Манифест зависимостей (P-01/P-02), объявленный bound и правила свежести: C-38/C-39 |
| `crosscheck/c02-row-model/` | Независимая модель row-грамматики craft-i18n и mutation harness: 22 named edits, path-зависимость на target |
| `spec/red-team/` | 18 атак на реальные артефакты пилота: 17 блокируются, 1 записанный слепой путь (пере-датировка с заменой signer'а); заимствование evidence закрыто L6, сокрытие finding-строки — L2 (C-37), подделка подписанной записи — якорем (C-41), в том числе правка подписанного run_record — L2 |
| `ci/mutation-changed.yml` | Шаблон CI: план по merge base, запуск только выбранных fixtures, skip при пустом плане |
| `.github/workflows/fuzz-nightly.yml` | V2-19: ночной replay записанного fuzz-прогона; cron + dispatch, без push/PR, артефакт на 90 дней |
| `tools/diff_coverage.py` | DC1–DC5: изменённый choke point обязан отображаться на non-open claim |
| `evals/linter/` | Образец адверсариального набора для детекторов |
| `evals/cell-lint/` | Адверсариальный набор для `cell_lint` |
| `spec/conveyor/cell-registry.schema.json` | Машиночитаемая ячейка |
| `spec/pilots/rbac_pg/` | Пилотный реестр: 29 ячеек на реальном репозитории |
| `spec/pilots/craft-i18n/` | Второй пилот: 14 ячеек на Rust-крейте, не-RBAC и не-БД |
| `spec/coverage/` | CV1–CV4: метод, измеренные числа, границы, снимки 2026-11-07 |
| `spec/diff-coverage/` | DC1–DC5: объявления, экстрактор, измеренные числа, границы, снимки 2026-11-07 |
| `spec/conveyor/guard-grammar.md` | Границы L2 |
| `spec/conveyor/product-trials.md` | Граница продуктовых испытаний: критерии входа, метрики и протокол замера (draft) |
| `Makefile` | `make verify` — единая точка запуска статических гейтов (V2-08); `make mutations` (стенд PostgreSQL), `make mutations-i18n` (cargo) и `make mutations-all` — mutation-прогоны |

Этот документ — не сертификация, не аудит и не обещание покрытия. Он фиксирует
намерение, границы и следующий evidence.
